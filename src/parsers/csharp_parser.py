import tree_sitter
import tree_sitter_c_sharp
import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum, AccessModifierEnum
from src.parsers.tree_sitter_parser import TreeSitterParser
from src.parsers.base_parser import ParsedSymbol
from src.extractors.lambda_analyzer import LambdaAnalyzer
from src.extractors.di_analyzer import DIAnalyzer
from src.extractors.routing_analyzer import RoutingAnalyzer

class CSharpParser(TreeSitterParser):
    """C# language parser using Tree-sitter."""
    
    def __init__(self):
        super().__init__(LanguageEnum.CSHARP, tree_sitter_c_sharp)
        self.lambda_analyzer = LambdaAnalyzer()
        self.di_analyzer = DIAnalyzer()
        self.routing_analyzer = RoutingAnalyzer()

    def _calculate_complexity(self, node: tree_sitter.Node, code: str) -> int:
        """
        Calculate cyclomatic complexity (McCabe) for a node.
        Start with 1, add 1 for each branching construct.
        """
        complexity = 1
        
        # Tree-sitter cursor traversal for node types
        cursor = node.walk()
        while True:
            if cursor.node.type in ['if_statement', 'for_statement', 'foreach_statement', 'while_statement', 'do_statement', 'case_switch_label', 'catch_clause', 'conditional_expression']:
                 complexity += 1
            elif cursor.node.type == 'binary_expression':
                 # Check for && and ||
                 # operator is usually the second child
                 children = cursor.node.children
                 if len(children) > 1:
                     # Check all children for operator text (safer than index)
                     for child in children:
                         if child.type not in ['identifier', 'literal', 'binary_expression', 'parenthesized_expression']:
                             op_text = self._get_node_text(child, code)
                             if op_text == '&&' or op_text == '||':
                                 complexity += 1
                                 break  # Only count once per binary_expression node
            
            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue
            
            # Retract
            while True:
                if not cursor.goto_parent():
                    return complexity
                if cursor.goto_next_sibling():
                    break
        
        return complexity
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a C# file."""
        return file_path.suffix.lower() == '.cs'
    
    def _extract_symbols(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        """Extract C# symbols from AST."""
        symbols = []
        
        def traverse(n: tree_sitter.Node, parent_name: Optional[str] = None):
            # Classes
            if n.type == 'class_declaration':
                symbol = self._parse_class(n, code, parent_name)
                symbols.append(symbol)
                # Update parent for nested symbols
                parent_name = symbol.fully_qualified_name
            
            # Interfaces
            elif n.type == 'interface_declaration':
                symbol = self._parse_interface(n, code, parent_name)
                symbols.append(symbol)
                parent_name = symbol.fully_qualified_name
            
            # Structs
            elif n.type == 'struct_declaration':
                symbol = self._parse_struct(n, code, parent_name)
                symbols.append(symbol)
                parent_name = symbol.fully_qualified_name
            
            # Enums
            elif n.type == 'enum_declaration':
                symbols.append(self._parse_enum(n, code, parent_name))
            
            # Methods
            elif n.type == 'method_declaration':
                symbols.append(self._parse_method(n, code, parent_name))
            
            # Properties
            elif n.type == 'property_declaration':
                symbols.append(self._parse_property(n, code, parent_name))
            
            # Fields
            elif n.type == 'field_declaration':
                symbols.extend(self._parse_fields(n, code, parent_name))
            
            # Namespaces
            elif n.type == 'namespace_declaration':
                name_node = self._find_child_by_type(n, 'qualified_name') or self._find_child_by_type(n, 'identifier')
                namespace_name = self._get_node_text(name_node, code) if name_node else ""
                
                new_parent = f"{parent_name}.{namespace_name}" if parent_name else namespace_name
                
                for child in n.children:
                    traverse(child, new_parent)
                return

            # Recursively traverse children
            for child in n.children:
                traverse(child, parent_name)
        
        traverse(node)
        
        # Second pass: Detect Minimal API endpoints (app.MapGet, app.MapPost, etc.)
        minimal_api_endpoints = self._extract_minimal_api_endpoints(node, code)
        symbols.extend(minimal_api_endpoints)
        
        # Third pass: Detect DI registrations (Phase 3)
        registrations = self.di_analyzer.analyze(node, code)
        if registrations:
             for reg in registrations:
                 # Create reference dicts
                 refs = []
                 # Service Type
                 refs.append({
                     'name': reg.service_type,
                     'type': 'di_registration',
                     'line': reg.line,
                     'column': reg.column
                 })
                 # Implementation Type (if different)
                 if reg.implementation_type and reg.implementation_type != reg.service_type:
                     refs.append({
                         'name': reg.implementation_type,
                         'type': 'di_registration',
                         'line': reg.line,
                         'column': reg.column
                     })
                 
                 # Attach to enclosing Class symbol
                 
                 # Attach to enclosing Class symbol (Innermost only)
                 # Find all classes that contain this registration line
                 candidate_classes = [
                     s for s in symbols 
                     if s.kind == SymbolKindEnum.CLASS and s.start_line <= reg.line <= s.end_line
                 ]
                 
                 if candidate_classes:
                     # Sort by start_line descending to find the innermost class (closest start line before reg)
                     innermost_class = max(candidate_classes, key=lambda s: (s.start_line, -s.end_line))
                     
                     if innermost_class.references is None:
                         innermost_class.references = []
                     # Use copy to ensure we don't accidentally share reference lists if logic changes
                     innermost_class.references.extend([r.copy() for r in refs])
        
        return symbols

    def _extract_references(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        """
        Extract type references from a node.
        
        Traverses the node to find:
        - Type identifiers in variable declarations
        - Object creation types (new Foo())
        - Generic type arguments
        - Static member access (Foo.Bar)
        - Method parameters and return types
        - Property types
        - Attribute usages
        """
        references = []
        
        def traverse_debug(n: tree_sitter.Node):
            # Positional heuristic helper
            def get_first_type_child(node: tree_sitter.Node) -> Optional[tree_sitter.Node]:
                for child in node.children:
                    if child.type in ['attribute_list', 'attribute', 'modifier', 'accessibility_modifier', 'comment', 'preproc_directive']:
                        continue
                    # The first significant node is likely the type
                    return child
                return None

            type_node = None
            
            # Object creation: new User()
            if n.type == 'object_creation_expression':
                type_node = n.child_by_field_name('type') or self._find_child_by_type(n, 'type') or self._find_child_by_type(n, 'identifier') or self._find_child_by_type(n, 'qualified_name') or self._find_child_by_type(n, 'generic_name')
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    references.append({
                        'name': type_name,
                        'type': 'instantiation',
                        'line': type_node.start_point[0] + 1,
                        'column': type_node.start_point[1]
                    })
            
            # Variable declaration: User user;
            elif n.type in ['variable_declaration', 'local_variable_declaration']:
                type_node = n.child_by_field_name('type')
                if not type_node:
                    # Fallback to positional: first child is type
                    type_node = get_first_type_child(n)
                
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    # Exclude 'var'
                    if type_name != 'var':
                        references.append({
                            'name': type_name,
                            'type': 'type_reference',
                            'line': type_node.start_point[0] + 1,
                            'column': type_node.start_point[1]
                        })

            # Property declaration: public User User { get; set; }
            elif n.type in ['property_declaration', 'property_definition']:
                type_node = n.child_by_field_name('type')
                if not type_node:
                    type_node = get_first_type_child(n)
                
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    references.append({
                        'name': type_name,
                        'type': 'type_reference',
                        'line': type_node.start_point[0] + 1,
                        'column': type_node.start_point[1]
                    })

            # Method declaration (Return Type)
            elif n.type in ['method_declaration', 'method_definition']:
                type_node = n.child_by_field_name('type') or n.child_by_field_name('return_type')
                if not type_node:
                    type_node = get_first_type_child(n)
                
                # Check if it's not void (void_keyword)
                if type_node and type_node.type != 'void_keyword':
                    type_name = self._get_node_text(type_node, code)
                    if type_name != 'void':
                        references.append({
                            'name': type_name,
                            'type': 'type_reference',
                            'line': type_node.start_point[0] + 1,
                            'column': type_node.start_point[1]
                        })

            # Parameter: (User user)
            elif n.type in ['parameter', 'parameter_declaration']:
                type_node = n.child_by_field_name('type')
                if not type_node:
                     type_node = get_first_type_child(n)
                
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    # Ensure we picked a type-like thing, not the parameter name itself 
                    # (if type implies var/omitted? No, C# requires type generally, or 'var')
                    references.append({
                        'name': type_name,
                        'type': 'type_reference',
                        'line': type_node.start_point[0] + 1,
                        'column': type_node.start_point[1]
                    })

            # Attribute Usage: [ApiController]
            elif n.type == 'attribute':
                 name_node = n.child_by_field_name('name')
                 if not name_node:
                     name_node = self._find_child_by_type(n, 'identifier') or self._find_child_by_type(n, 'qualified_name') or self._find_child_by_type(n, 'type_identifier')
                 
                 if name_node:
                     attr_name = self._get_node_text(name_node, code)
                     references.append({
                         'name': attr_name,
                         'type': 'attribute_usage', # Attributes are type references
                         'line': name_node.start_point[0] + 1,
                         'column': name_node.start_point[1]
                     })
            
            # Generic names: List<User>
            elif n.type == 'generic_name':
                type_args = self._find_child_by_type(n, 'type_argument_list')
                if type_args:
                    for child in type_args.children:
                        if child.type in ['identifier', 'qualified_name', 'type', 'generic_name']:
                            type_name = self._get_node_text(child, code)
                            references.append({
                                'name': type_name,
                                'type': 'type_argument',
                                'line': child.start_point[0] + 1,
                                'column': child.start_point[1]
                            })

            # Cast expression: (User)obj
            elif n.type == 'cast_expression':
                type_node = n.child_by_field_name('type')
                if not type_node:
                    type_node = self._find_child_by_type(n, 'type') or self._find_child_by_type(n, 'identifier') or self._find_child_by_type(n, 'qualified_name') or self._find_child_by_type(n, 'generic_name')
                
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    references.append({
                        'name': type_name,
                        'type': 'cast',
                        'line': type_node.start_point[0] + 1,
                        'column': type_node.start_point[1]
                    })
            
            # Recurse
            for child in n.children:
                traverse_debug(child)
                
        traverse_debug(node)
        return references

    def _parse_class(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        # Parse a class declaration.
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownClass"
        
        # Top-level classes default to INTERNAL, nested classes default to PRIVATE
        default_access = AccessModifierEnum.INTERNAL if parent_name is None else AccessModifierEnum.PRIVATE
        access_modifier = self._extract_access_modifier(node, code, default_access)
        fqn = f"{parent_name}.{name}" if parent_name else name
        
        # Extract XML documentation
        xml_docs = self._find_xml_documentation(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Extract attributes
        attributes = self._extract_attributes(node, code)
        
        # Check for partial modifier (Phase 2.1)
        is_partial = self._has_partial_modifier(node, code)
        
        # Extract generics (Phase 2.3)
        generic_params = self._extract_generic_parameters(node, code)
        constraints = self._extract_constraints(node, code)
        
        # Store attributes and partial flag in structured_docs
        if xml_docs is None:
            xml_docs = {}
        if attributes:
            xml_docs['attributes'] = attributes
        if is_partial:
            xml_docs['is_partial'] = True
        
        # Extract modifiers (Phase 2.4)
        modifiers = self._extract_modifiers(node, code)
        if modifiers:
            if xml_docs is None: xml_docs = {}
            xml_docs.update(modifiers)
        
        # Extract references
        references = self._extract_references(node, code)

        return ParsedSymbol(
            kind=SymbolKindEnum.CLASS,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_node_text(node, code).split('{')[0].strip() if '{' in self._get_node_text(node, code) else self._get_node_text(node, code)[:200],
            documentation=plain_doc,
            structured_docs=xml_docs if xml_docs else None,
            access_modifier=access_modifier,
            parent_name=parent_name,
            fully_qualified_name=fqn,
            generic_parameters=generic_params,
            constraints=constraints,
            references=references
        )
    
    def _parse_interface(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        # Parse an interface declaration.
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownInterface"
        
        # Top-level interfaces default to INTERNAL, nested interfaces default to PRIVATE
        default_access = AccessModifierEnum.INTERNAL if parent_name is None else AccessModifierEnum.PRIVATE
        
        # Extract XML documentation
        xml_docs = self._find_xml_documentation(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Check for partial modifier (Phase 2.1)
        is_partial = self._has_partial_modifier(node, code)
        
        # Extract generics (Phase 2.3)
        generic_params = self._extract_generic_parameters(node, code)
        constraints = self._extract_constraints(node, code)
        
        if xml_docs is None:
            xml_docs = {}
        if is_partial:
            xml_docs['is_partial'] = True
        
        # Extract references
        references = self._extract_references(node, code)

        return ParsedSymbol(
            kind=SymbolKindEnum.INTERFACE,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_node_text(node, code).split('{')[0].strip() if '{' in self._get_node_text(node, code) else self._get_node_text(node, code)[:200],
            documentation=plain_doc,
            structured_docs=xml_docs if xml_docs else None,
            access_modifier=self._extract_access_modifier(node, code, default_access),
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name,
            generic_parameters=generic_params,
            constraints=constraints,
            references=references
        )
    
    def _parse_struct(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        # Parse a struct declaration.
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownStruct"
        
        # Top-level structs default to INTERNAL, nested structs default to PRIVATE
        default_access = AccessModifierEnum.INTERNAL if parent_name is None else AccessModifierEnum.PRIVATE
        
        # Extract XML documentation
        xml_docs = self._find_xml_documentation(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Check for partial modifier (Phase 2.1)
        is_partial = self._has_partial_modifier(node, code)
        
        # Extract generics (Phase 2.3)
        generic_params = self._extract_generic_parameters(node, code)
        constraints = self._extract_constraints(node, code)
        
        if xml_docs is None:
            xml_docs = {}
        if is_partial:
            xml_docs['is_partial'] = True
        
        # Extract references
        references = self._extract_references(node, code)

        return ParsedSymbol(
            kind=SymbolKindEnum.STRUCT,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_node_text(node, code).split('{')[0].strip() if '{' in self._get_node_text(node, code) else self._get_node_text(node, code)[:200],
            documentation=plain_doc,
            structured_docs=xml_docs if xml_docs else None,
            access_modifier=self._extract_access_modifier(node, code, default_access),
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name,
            generic_parameters=generic_params,
            constraints=constraints,
            references=references
        )
    

    
    def _parse_enum(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        # Parse an enum declaration.
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownEnum"
        
        # Top-level enums default to INTERNAL, nested enums default to PRIVATE
        default_access = AccessModifierEnum.INTERNAL if parent_name is None else AccessModifierEnum.PRIVATE
        
        return ParsedSymbol(
            kind=SymbolKindEnum.ENUM,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            access_modifier=self._extract_access_modifier(node, code, default_access),
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _parse_method(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        # Parse a method declaration.
        # Find name: usually the identifier before parameter_list or type_parameter_list
        name_node = None
        param_list = self._find_child_by_type(node, 'parameter_list')
        
        if param_list:
            # Look backwards from param_list
            curr = param_list.prev_sibling
            while curr:
                if curr.type == 'type_parameter_list':
                    curr = curr.prev_sibling
                    continue
                if curr.type == 'identifier':
                    name_node = curr
                    break
                # If we hit a type or modifier, we went too far (or name is missing)
                # Note: explicit interface implementation might have qualified_name
                if curr.type == 'qualified_name':
                    name_node = curr
                    break
                if curr.type in ('predefined_type', 'type', 'void_keyword', 'modifier', 'generic_name'):
                    break
                curr = curr.prev_sibling
        
        if not name_node:
             # Fallback to finding first identifier (might be return type, but better than nothing)
             name_node = self._find_child_by_type(node, 'identifier')
             
        name = self._get_node_text(name_node, code) if name_node else "UnknownMethod"
        
        # Extract parameters
        parameters = []
        if param_list:
            for param in param_list.children:
                if param.type == 'parameter':
                    # Try different type node names
                    param_type_node = (self._find_child_by_type(param, 'type') or
                                      self._find_child_by_type(param, 'predefined_type') or
                                      self._find_child_by_type(param, 'array_type') or
                                      self._find_child_by_type(param, 'nullable_type') or
                                      self._find_child_by_type(param, 'generic_name'))
                    param_name_node = self._find_child_by_type(param, 'identifier')
                    if param_type_node and param_name_node:
                        parameters.append({
                            'name': self._get_node_text(param_name_node, code),
                            'type': self._get_node_text(param_type_node, code)
                        })
        
        # Extract return type - check multiple possible type node names
        return_type = None
        type_node = (self._find_child_by_type(node, 'type') or
                    self._find_child_by_type(node, 'predefined_type') or
                    self._find_child_by_type(node, 'array_type') or
                    self._find_child_by_type(node, 'nullable_type') or
                    self._find_child_by_type(node, 'generic_name') or
                    self._find_child_by_type(node, 'type_identifier') or  # Added type_identifier
                    self._find_child_by_type(node, 'identifier') or       # Added identifier
                    self._find_child_by_type(node, 'qualified_name') or   # Added qualified_name
                    self._find_child_by_type(node, 'void_keyword'))
        if type_node:
            return_type = self._get_node_text(type_node, code)
        
        node_text = self._get_node_text(node, code)
        signature = node_text.split('{')[0].strip() if '{' in node_text else node_text[:200]
        
        # Extract XML documentation
        xml_docs = self._find_xml_documentation(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Extract generics (Phase 2.3)
        generic_params = self._extract_generic_parameters(node, code)
        constraints = self._extract_constraints(node, code)
        
        # Extract attributes (Phase 3.3)
        attributes = self._extract_attributes(node, code)
        if attributes:
            if xml_docs is None: xml_docs = {}
            xml_docs['attributes'] = attributes
        
        # Extract modifiers (Phase 2.4)
        modifiers = self._extract_modifiers(node, code)
        if modifiers:
            if xml_docs is None: xml_docs = {}
            xml_docs.update(modifiers)

        method_symbol = ParsedSymbol(
            kind=SymbolKindEnum.METHOD,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            return_type=return_type,
            parameters=parameters,
            signature=signature,
            documentation=plain_doc,
            structured_docs=xml_docs,
            access_modifier=self._extract_access_modifier(node, code),
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name,
            generic_parameters=generic_params,
            constraints=constraints,
            references=self._extract_references(node, code),
            complexity=self._calculate_complexity(node, code)
        )
        
        # Analyze lambdas within this method (Phase 3.1)
        # Analyze lambdas within this method (Phase 3.1)
        lambdas = self.lambda_analyzer.extract_lambdas(node, code, method_symbol.name, parent_name or "")
        if lambdas:
            # Convert LambdaExpression objects to dictionaries for JSON serialization
            if not method_symbol.structured_docs:
                method_symbol.structured_docs = {}
            
            method_symbol.structured_docs['lambdas'] = [
                {
                    'name': lam.name.split('.')[-1], # Just "lambda_N"
                    # parent_name is the class FQN. lam.name is "MethodName.lambda_N". 
                    # So FQN = Class.Method.lambda_N
                    'fully_qualified_name': f"{parent_name}.{lam.name}" if parent_name else lam.name,
                    'start_line': lam.start_line,
                    'end_line': lam.end_line,
                    'signature': lam.signature,
                    'parameters': lam.parameters,
                    'closure_variables': lam.closure_variables,
                    'linq_pattern': lam.linq_pattern,
                }
                for lam in lambdas
            ]

        # Phase 3 Task 10: Analyze Routing
        # We need the class node. In tree-sitter, method is child of class body, which is child of class declaration.
        # node.parent -> class_body, node.parent.parent -> class_declaration
        # Verify parent types to be safe.
        if node.parent and node.parent.parent and node.parent.parent.type == 'class_declaration':
            class_node = node.parent.parent
            route_info = self.routing_analyzer.analyze(class_node, node, code)
            if route_info:
                if not method_symbol.structured_docs:
                    method_symbol.structured_docs = {}
                method_symbol.structured_docs['api_endpoint'] = {
                    'method': route_info.http_method,
                    'route': route_info.route_template,
                    'parameters': route_info.parameters
                }
            
        return method_symbol

    def _parse_property(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse a property declaration."""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownProperty"
        
        type_node = self._find_child_by_type(node, 'type')
        prop_type = self._get_node_text(type_node, code) if type_node else None
        
        # Extract XML documentation
        xml_docs = self._find_xml_documentation(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Extract attributes (Phase 3.3)
        attributes = self._extract_attributes(node, code)
        if attributes:
            if xml_docs is None: xml_docs = {}
            xml_docs['attributes'] = attributes
        
        # Extract modifiers (Phase 2.4)
        modifiers = self._extract_modifiers(node, code)
        if modifiers:
            if xml_docs is None: xml_docs = {}
            xml_docs.update(modifiers)
            
        return ParsedSymbol(
            kind=SymbolKindEnum.PROPERTY,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            return_type=prop_type,
            access_modifier=self._extract_access_modifier(node, code),
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name,
            documentation=plain_doc,
            structured_docs=xml_docs,
            references=self._extract_references(node, code)
        )
    
    def _parse_fields(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> List[ParsedSymbol]:
        """Parse field declarations (can declare multiple variables)."""
        fields = []
        variable_declaration = self._find_child_by_type(node, 'variable_declaration')
        
        if variable_declaration:
            type_node = self._find_child_by_type(variable_declaration, 'type')
            field_type = self._get_node_text(type_node, code) if type_node else None
            
            # Find all variable declarators
            for child in variable_declaration.children:
                if child.type == 'variable_declarator':
                    name_node = self._find_child_by_type(child, 'identifier')
                    if name_node:
                        name = self._get_node_text(name_node, code)
                        fields.append(ParsedSymbol(
                            kind=SymbolKindEnum.VARIABLE,
                            name=name,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_column=node.start_point[1],
                            end_column=node.end_point[1],
                            return_type=field_type,
                            access_modifier=self._extract_access_modifier(node, code),
                            parent_name=parent_name,
                            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name,
                            references=self._extract_references(node, code)
                        ))
        
        return fields
    
    def _extract_access_modifier(self, node: tree_sitter.Node, code: str, default: AccessModifierEnum = AccessModifierEnum.PRIVATE) -> AccessModifierEnum:
        """
        Extract access modifier from node.
        
        Args:
            node: AST node to extract from
            code: Source code
            default: Default access modifier if none specified
        
        Returns:
            Access modifier enum
        """
        # Look for modifier nodes in node children
        modifiers = []
        for child in node.children:
            if child.type == 'modifier':
                text = self._get_node_text(child, code).lower()
                modifiers.append(text)
        
        # Check for combined modifiers
        if 'protected' in modifiers and 'internal' in modifiers:
            return AccessModifierEnum.PROTECTED_INTERNAL
        elif 'public' in modifiers:
            return AccessModifierEnum.PUBLIC
        elif 'private' in modifiers:
            return AccessModifierEnum.PRIVATE
        elif 'protected' in modifiers:
            return AccessModifierEnum.PROTECTED
        elif 'internal' in modifiers:
            return AccessModifierEnum.INTERNAL
        
        # Return the provided default
        return default
    
    def _extract_modifiers(self, node: tree_sitter.Node, code: str) -> Dict[str, bool]:
        """
        Extract boolean modifiers from node.
        
        Args:
            node: AST node
            code: Source code
            
        Returns:
            Dictionary of boolean flags (is_static, is_virtual, etc.)
        """
        modifiers = {
            'is_static': False,
            'is_virtual': False,
            'is_abstract': False,
            'is_override': False,
            'is_sealed': False,
            'is_async': False,
            'is_readonly': False
        }
        
        # Look for modifier nodes in node children
        for child in node.children:
            if child.type == 'modifier':
                text = self._get_node_text(child, code).lower()
                if text == 'static': modifiers['is_static'] = True
                elif text == 'virtual': modifiers['is_virtual'] = True
                elif text == 'abstract': modifiers['is_abstract'] = True
                elif text == 'override': modifiers['is_override'] = True
                elif text == 'sealed': modifiers['is_sealed'] = True
                elif text == 'async': modifiers['is_async'] = True
                elif text == 'readonly': modifiers['is_readonly'] = True
        
        return modifiers
    
    def _find_xml_documentation(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        # Extract XML documentation comments before a symbol.
        # Parses XML documentation tags like:
        # /// <summary>Description</summary>
        # /// <param name="x">Parameter info</param>
        # /// <returns>Return value description</returns>
        # /// <example>Code example</example>
        # /// <remarks>Additional remarks</remarks>
        # Args:
        #     node: AST node to find documentation for
        #     code: Source code
        # Returns:
        #     Dictionary with structured documentation or None if not found
        # End of XML documentation parsing
        # Get the lines before this node
        start_line = node.start_point[0]
        if start_line == 0:
            return None
        
        lines = code.split('\n')
        doc_lines = []
        
        # Look backwards from the node's start line
        for i in range(start_line - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith('///'):
                # Remove /// prefix and add to doc lines (prepend to maintain order)
                doc_lines.insert(0, line[3:].strip())
            elif line.startswith('//') or line == '':
                # Regular comment or empty line, continue
                continue
            else:
                # Hit non-comment line, stop
                break
        
        if not doc_lines:
            return None
        
        # Parse XML tags from documentation
        doc_text = ' '.join(doc_lines)
        structured_docs = {}
        
        # Extract summary
        summary_match = re.search(r'<summary>\s*(.*?)\s*</summary>', doc_text, re.DOTALL)
        if summary_match:
            structured_docs['summary'] = summary_match.group(1).strip()
        
        # Extract parameters
        param_matches = re.findall(r'<param\s+name="([^"]+)"\s*>\s*(.*?)\s*</param>', doc_text, re.DOTALL)
        if param_matches:
            structured_docs['params'] = [
                {'name': name, 'description': desc.strip()} 
                for name, desc in param_matches
            ]
        
        # Extract returns
        returns_match = re.search(r'<returns>\s*(.*?)\s*</returns>', doc_text, re.DOTALL)
        if returns_match:
            structured_docs['returns'] = returns_match.group(1).strip()
        
        # Extract example
        example_match = re.search(r'<example>\s*(.*?)\s*</example>', doc_text, re.DOTALL)
        if example_match:
            structured_docs['example'] = example_match.group(1).strip()
        
        # Extract remarks
        remarks_match = re.search(r'<remarks>\s*(.*?)\s*</remarks>', doc_text, re.DOTALL)
        if remarks_match:
            structured_docs['remarks'] = remarks_match.group(1).strip()
        
        # Extract exceptions
        exception_matches = re.findall(r'<exception\s+cref="([^"]+)"\s*>\s*(.*?)\s*</exception>', doc_text, re.DOTALL)
        if exception_matches:
            structured_docs['exceptions'] = [
                {'type': exc_type, 'description': desc.strip()} 
                for exc_type, desc in exception_matches
            ]
        
        # Extract see/seealso references
        see_matches = re.findall(r'<see\s+cref="([^"]+)"\s*/>', doc_text)
        if see_matches:
            structured_docs['see_also'] = see_matches
        
        return structured_docs if structured_docs else None
    
    def _extract_attributes(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        # Extract C# attributes from a node.
        # Parses attributes like:
        # [ApiController]
        # [Route("api/[controller]")]
        # [HttpGet("{id}")]
        # [Authorize(Roles = "Admin")]
        # Args:
        #     node: AST node to extract attributes from
        #     code: Source code
        # Returns:
        #     List of attribute dictionaries with name and arguments
        attributes = []
        
        # Look for attribute_list nodes that are siblings/children of this node
        for child in node.children:
            if child.type == 'attribute_list':
                # Each attribute_list can contain multiple attributes
                for attr_child in child.children:
                    if attr_child.type == 'attribute':
                        attr_info = self._parse_attribute(attr_child, code)
                        if attr_info:
                            attributes.append(attr_info)
        
        return attributes
    
    def _parse_attribute(self, attr_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        # Parse a single attribute node.
        # Find the attribute name
        name_node = None
        for child in attr_node.children:
            if child.type in ['identifier', 'qualified_name']:
                name_node = child
                break
        
        if not name_node:
            return None
        
        attr_name = self._get_node_text(name_node, code)
        
        # Extract arguments if present (now returns dict with positional/named)
        arguments = {'positional': [], 'named': {}}
        for child in attr_node.children:
            if child.type == 'attribute_argument_list':
                arguments = self._extract_attribute_arguments(child, code)
                break
        
        return {
            'name': attr_name,
            'arguments': arguments
        }

    
    def _extract_attribute_arguments(self, arg_list_node: tree_sitter.Node, code: str) -> Dict[str, Any]:
        # Extract arguments from attribute argument list.
        # Parses both positional and named arguments:
        # - Positional: [HttpGet("{id}")]
        # - Named: [Route(Name = "GetUser", Template = "users/{id}")]
        # - Mixed: [ProducesResponseType(typeof(UserDto), StatusCodes.Status200OK)]
        # Returns:
        #     Dictionary with 'positional' (list) and 'named' (dict) arguments
        positional_args = []
        named_args = {}
        
        for child in arg_list_node.children:
            if child.type == 'attribute_argument':
                # Check if this is a named argument (has name_equals or name_colon or assignment_expression)
                is_named = False
                arg_name = None
                arg_value = None
                
                for arg_child in child.children:
                    if arg_child.type == 'assignment_expression':
                        # Named parameter: Name = "value" (tree-sitter-c-sharp specific)
                        is_named = True
                        # Left side is identifier, right side is value
                        identifier = self._find_child_by_type(arg_child, 'identifier')
                        if identifier:
                            arg_name = self._get_node_text(identifier, code)
                        
                        # Find value (not identifier or =)
                        for assign_child in arg_child.children:
                            if assign_child.type != 'identifier' and assign_child.type != '=':
                                arg_value = self._extract_attribute_value(assign_child, code)
                                if arg_value is not None:
                                    break

                    elif arg_child.type == 'name_equals':
                        # Named parameter: Name = "value"
                        is_named = True
                        # Find the identifier (parameter name)
                        for name_child in arg_child.children:
                            if name_child.type == 'identifier':
                                arg_name = self._get_node_text(name_child, code)
                                break
                    elif arg_child.type == 'name_colon':
                        # Named parameter: Name: "value" (alternative syntax)
                        is_named = True
                        for name_child in arg_child.children:
                            if name_child.type == 'identifier':
                                arg_name = self._get_node_text(name_child, code)
                                break
                    elif arg_child.type not in ['name_equals', 'name_colon', 'assignment_expression', ',', '(', ')']:
                        # This is the value expression (only if not already handled by assignment)
                        if not is_named:
                            arg_value = self._extract_attribute_value(arg_child, code)
                
                # If no explicit value found, use the entire argument text
                if arg_value is None and not is_named:
                    arg_value = self._get_node_text(child, code).strip()
                
                if is_named and arg_name:
                    named_args[arg_name] = arg_value
                elif not is_named:
                    positional_args.append(arg_value)
        
        return {
            'positional': positional_args,
            'named': named_args
        }
    
    def _extract_attribute_value(self, value_node: tree_sitter.Node, code: str) -> Any:
        # Extract value from an attribute argument node.
        # Handles various C# expressions:
        # - String literals: "api/users"
        # - Numbers: 200, 10.5
        # - typeof expressions: typeof(UserDto)
        # - Array initializers: new[] { "GET", "POST" }
        # - Member access: StatusCodes.Status200OK
        # - Boolean: true, false
        # - null
        # Returns:
        #     Parsed value (preserves type where possible)
        node_type = value_node.type
        
        # String literal
        if node_type in ['string_literal', 'verbatim_string_literal', 'interpolated_string_expression']:
            text = self._get_node_text(value_node, code)
            # Remove quotes
            if text.startswith('@"') and text.endswith('"'):
                return text[2:-1]  # Verbatim string
            elif text.startswith('"') and text.endswith('"'):
                return text[1:-1]  # Regular string
            return text
        
        # Number literal
        elif node_type in ['integer_literal', 'real_literal']:
            text = self._get_node_text(value_node, code)
            try:
                if '.' in text:
                    return float(text)
                else:
                    return int(text)
            except ValueError:
                return text
        
        # Boolean literal
        elif node_type == 'boolean_literal':
            text = self._get_node_text(value_node, code)
            return text.lower() == 'true'
        
        # Null literal
        elif node_type == 'null_literal':
            return None
        
        # typeof expression: typeof(SomeType)
        elif node_type == 'typeof_expression':
            text = self._get_node_text(value_node, code)
            return {
                'type': 'typeof',
                'value': text
            }
        
        # Array/collection initializer: new[] { "GET", "POST" }
        elif node_type in ['array_creation_expression', 'implicit_array_creation_expression', 'collection_expression']:
            items = []
            for child in value_node.children:
                if child.type == 'initializer_expression':
                    for init_child in child.children:
                        if init_child.type not in ['{', '}', ',']:
                            items.append(self._extract_attribute_value(init_child, code))
            return items
        
        # Member access: StatusCodes.Status200OK, SomeEnum.Value
        elif node_type in ['member_access_expression', 'qualified_name']:
            text = self._get_node_text(value_node, code)
            return {
                'type': 'member_access',
                'value': text
            }
        
        # Default: return text representation
        else:
            return self._get_node_text(value_node, code).strip()

    
    def extract_imports(self, node: tree_sitter.Node, code: str) -> List[str]:
        # Extract using statements.
        imports = []
        
        def traverse(n: tree_sitter.Node):
            if n.type == 'using_directive':
                # Extract namespace being imported
                for child in n.children:
                    if child.type in ['qualified_name', 'identifier']:
                        imports.append(self._get_node_text(child, code))
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return imports

    def _extract_minimal_api_endpoints(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        # Extract C# Minimal API endpoints like app.MapGet("/path", ...).
        endpoints = []
        http_methods = ['MapGet', 'MapPost', 'MapPut', 'MapDelete', 'MapPatch']
        
        def traverse(n: tree_sitter.Node):
            if n.type == 'invocation_expression':
                # Check if this is a minimal API call
                member_access = self._find_child_by_type(n, 'member_access_expression')
                if member_access:
                    # Get the method name (e.g., MapGet, MapPost)
                    method_name_node = None
                    for child in member_access.children:
                        if child.type == 'identifier' and child != member_access.children[0]:
                            method_name_node = child
                            break
                    
                    if method_name_node:
                        method_name = self._get_node_text(method_name_node, code)
                        
                        if method_name in http_methods:
                            # Extract the route path from first argument
                            arg_list = self._find_child_by_type(n, 'argument_list')
                            if arg_list and arg_list.children:
                                # Find first argument (skip '(' token)
                                first_arg = None
                                for child in arg_list.children:
                                    if child.type == 'argument':
                                        first_arg = child
                                        break
                                
                                if first_arg:
                                    # Extract string literal
                                    string_lit = self._find_child_by_type(first_arg, 'string_literal')
                                    if string_lit:
                                        # Get the path (extract content between quotes)
                                        path_text = self._get_node_text(string_lit, code).strip('"')
                                        
                                        # Convert MapGet -> GET
                                        http_method = method_name.replace('Map', '').upper()
                                        
                                        endpoint = ParsedSymbol(
                                            kind=SymbolKindEnum.ENDPOINT,
                                            name=f"{http_method} {path_text}",
                                            start_line=n.start_point[0] + 1,
                                            end_line=n.end_point[0] + 1,
                                            start_column=n.start_point[1],
                                            end_column=n.end_point[1],
                                            signature=self._get_node_text(member_access, code),
                                            documentation=f"Minimal API {http_method} endpoint",
                                            structured_docs={
                                                'type': 'minimal_api',
                                                'method': http_method,
                                                'path': path_text
                                            },
                                            fully_qualified_name=f"{http_method}_{path_text}"
                                        )
                                        endpoints.append(endpoint)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return endpoints


    
    def _has_partial_modifier(self, node: tree_sitter.Node, code: str) -> bool:
        # Check if a class/interface/struct has the 'partial' modifier.
        # Look for modifier nodes in node children
        for child in node.children:
            if child.type == 'modifier':
                text = self._get_node_text(child, code).lower()
                if text == 'partial':
                    return True
        return False

    def _extract_generic_parameters(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        # Extract generic type parameters.
        params = []
        type_param_list = self._find_child_by_type(node, 'type_parameter_list')
        if type_param_list:
            for child in type_param_list.children:
                if child.type == 'type_parameter':
                    # Handle variance (in/out) for interfaces/delegates
                    variance = None
                    name_node = None
                    
                    for sub in child.children:
                        if sub.type == 'modifier':
                            mod_text = self._get_node_text(sub, code)
                            if mod_text in ('in', 'out'):
                                variance = mod_text
                        elif sub.type in ('in', 'out'):
                            variance = sub.type
                        elif sub.type == 'identifier':
                            name_node = sub
                    
                    # If no children (simple identifier), the node itself is the identifier text?
                    # Tree-sitter C# grammar: type_parameter: (attribute_list)? (modifier)? identifier
                    if not name_node:
                        # Try finding identifier child
                        name_node = self._find_child_by_type(child, 'identifier')
                    
                    name = self._get_node_text(name_node, code) if name_node else self._get_node_text(child, code)
                    
                    params.append({'name': name, 'variance': variance})
        return params

    def _extract_constraints(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        # Extract generic constraints.
        constraints = []
        for child in node.children:
            if child.type == 'type_parameter_constraints_clause':
                # where T : class, new()
                target_node = self._find_child_by_type(child, 'identifier') or self._find_child_by_type(child, 'type_identifier')
                target = self._get_node_text(target_node, code) if target_node else "Unknown"
                
                cons_list = []
                for cons_child in child.children:
                    # Skip 'where', ':', target, comma
                    if cons_child.type in ('where', ':', 'identifier', 'type_identifier', ','):
                        continue
                        
                    # Handle constraint wrapper
                    actual_constraint = cons_child
                    if cons_child.type == 'type_parameter_constraint':
                        # Unwrap
                        if cons_child.child_count > 0:
                            actual_constraint = cons_child.children[0]
                    
                    if actual_constraint.type in ('type_constraint', 'base_class_constraint', 'identifier', 'generic_name'):
                        cons_list.append(self._get_node_text(actual_constraint, code))
                    elif actual_constraint.type == 'class_constraint':
                        cons_list.append("class")
                    elif actual_constraint.type == 'struct_constraint':
                        cons_list.append("struct")
                    elif actual_constraint.type == 'new_constraint':
                        cons_list.append("new()")
                    elif actual_constraint.type == 'constructor_constraint':
                         cons_list.append("new()")
                    elif actual_constraint.type == 'primary_constraint': 
                        cons_list.append(self._get_node_text(actual_constraint, code))
                
                constraints.append({'parameter': target, 'constraints': cons_list})
        return constraints
