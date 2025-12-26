"""Call graph analyzer for extracting function/method calls."""

import tree_sitter
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Call:
    """Represents a function/method call."""
    method_name: str
    receiver: Optional[str] = None  # Object/class name for method calls
    arguments: List[str] = None
    line_number: int = 0
    end_line: int = 0
    start_column: int = 0
    end_column: int = 0
    is_async: bool = False
    is_static: bool = False
    
    def __post_init__(self):
        if self.arguments is None:
            self.arguments = []


class CSharpCallAnalyzer:
    """Analyzes C# code to extract function calls."""
    
    def extract_calls(
        self,
        method_node: tree_sitter.Node,
        code: str
    ) -> List[Call]:
        """
        Detect function calls in C# code block.
        
        Handles:
        - Direct calls: DoSomething()
        - Instance method calls: service.GetUser(id)
        - Static calls: UserService.GetUser(id)
        - Extension methods: list.Where(x => x.Active)
        - LINQ methods: from u in users select u
        - Async calls: await service.GetUserAsync(id)
        - Constructor calls: new UserService()
        
        Args:
            method_node: Tree-sitter node (method, field, property, etc.)
            code: Source code
            
        Returns:
            List of Call objects
        """
        calls = []
        
        def traverse(node: tree_sitter.Node):
            """Recursively traverse AST looking for invocations."""
            if node.type == 'invocation_expression':
                call = self._parse_invocation(node, code)
                if call:
                    calls.append(call)
            elif node.type == 'object_creation_expression':
                call = self._parse_object_creation(node, code)
                if call:
                    calls.append(call)
            elif node.type == 'constructor_declaration':
                 # Don't traverse into constructor declaration again if we are already in one
                 # But we might be passed one.
                 pass
            
            # Recursively check children
            for child in node.children:
                traverse(child)
        
        # Determine nodes to traverse based on input node type
        nodes_to_traverse = []
        
        if method_node.type in ['method_declaration', 'local_function_statement', 'constructor_declaration']:
            # For methods/constructors, analyze the body
            body = self._find_method_body(method_node)
            if body:
                nodes_to_traverse.append(body)
                
            # For constructors, also analyze the initializer (base/this call)
            # constructor_declaration -> constructor_initializer?
            for child in method_node.children:
                if child.type == 'constructor_initializer':
                    nodes_to_traverse.append(child)
                    
        elif method_node.type in ['field_declaration', 'property_declaration', 'variable_declarator']:
            # For fields/properties, analyze the whole node (includes initializers)
            nodes_to_traverse.append(method_node)
        else:
            # Fallback: traverse the node itself
            nodes_to_traverse.append(method_node)
            
        for node in nodes_to_traverse:
            traverse(node)
        
        return calls

    def extract_usages(
        self,
        method_node: tree_sitter.Node,
        code: str
    ) -> List[Call]:
        """
        Detect variable/property usages in C# code block.
        
        Args:
            method_node: Tree-sitter node
            code: Source code
            
        Returns:
            List of Call objects (representing usages)
        """
        usages = []
        
        def traverse(node: tree_sitter.Node):
            """Recursively traverse AST looking for usages."""
            # Check for identifier usages
            if node.type == 'identifier':
                # Skip if it's a declaration (only if it's the name being declared)
                if node.parent.type == 'variable_declarator':
                    if node.parent.child_by_field_name('name') == node:
                        return
                        
                # Skip other declarations unconditionally
                if node.parent.type in ['parameter', 'method_declaration', 'class_declaration', 'namespace_declaration']:
                    return
                
                # Skip if it's part of a call (method name)
                if node.parent.type == 'invocation_expression':
                    # Check if it's the method name being called
                    # invocation_expression -> identifier (method name)
                    if node.parent.child_by_field_name('function') == node:
                        return
                
                receiver = None
                
                # Handle member access (e.g., user.Name)
                if node.parent.type == 'member_access_expression':
                    # Check if it's part of a method call
                    if node.parent.parent and node.parent.parent.type == 'invocation_expression':
                        if node.parent.parent.child_by_field_name('function') == node.parent:
                            # Only skip if it's the method name (right side)
                            if node.parent.child_by_field_name('name') == node:
                                return
                    
                    # If we are the name (right side), get the expression (left side) as receiver
                    if node.parent.child_by_field_name('name') == node:
                        expression_node = node.parent.child_by_field_name('expression')
                        if expression_node:
                            receiver = self._get_node_text(expression_node, code)
                
                # It's a usage!
                name = self._get_node_text(node, code)
                usages.append(Call(
                    method_name=name, # Reuse field for variable name
                    receiver=receiver, # Capture receiver (e.g., "user" in "user.Name")
                    line_number=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    start_column=node.start_point[1] + 1,
                    end_column=node.end_point[1] + 1
                ))

            # Handle Constructor Parameter Types as USES (Dependency Injection)
            if node.type == 'parameter' and method_node.type == 'constructor_declaration':
                # Extract type annotation
                type_node = node.child_by_field_name('type')
                if type_node:
                    type_name = self._get_node_text(type_node, code)
                    # Create usage for the type
                    usages.append(Call(
                        method_name=type_name, 
                        receiver=None, # It's a type usage
                        line_number=type_node.start_point[0] + 1,
                        end_line=type_node.end_point[0] + 1,
                        start_column=type_node.start_point[1] + 1,
                        end_column=type_node.end_point[1] + 1,
                        is_static=True # Treat types as static
                    ))
            
            # Recursively check children
            for child in node.children:
                traverse(child)
        
        # Determine nodes to traverse based on input node type
        nodes_to_traverse = []
        
        if method_node.type in ['method_declaration', 'local_function_statement']:
             body = self._find_method_body(method_node)
             if body: nodes_to_traverse.append(body)
             
        elif method_node.type == 'constructor_declaration':
             # For constructors, analyze parameters AND body
             # Parameters
             params = method_node.child_by_field_name('parameters')
             if params: nodes_to_traverse.append(params)
             
             # Body
             body = self._find_method_body(method_node)
             if body: nodes_to_traverse.append(body)
             
             # Initializer (: base())
             for child in method_node.children:
                if child.type == 'constructor_initializer':
                    nodes_to_traverse.append(child)

        elif method_node.type in ['field_declaration', 'property_declaration', 'variable_declarator']:
            nodes_to_traverse.append(method_node)
        else:
             nodes_to_traverse.append(method_node)
             
        for node in nodes_to_traverse:
            traverse(node)
        
        return usages
    
    def _find_method_body(self, method_node: tree_sitter.Node) -> Optional[tree_sitter.Node]:
        """Find the method body node."""
        for child in method_node.children:
            if child.type == 'block':
                return child
        return None
    
    def _parse_object_creation(self, node: tree_sitter.Node, code: str) -> Optional[Call]:
        """
        Parse object_creation_expression (constructor call).
        
        Structure:
        object_creation_expression
          - new_keyword
          - type: identifier or generic_name
          - argument_list
        """
        try:
            type_node = None
            for child in node.children:
                if child.type in ['identifier', 'generic_name', 'qualified_name']:
                    type_node = child
                    break
            
            if not type_node:
                return None
            
            class_name = self._get_node_text(type_node, code)
            
            # For generics like List<string>, extract just List
            if '<' in class_name:
                class_name = class_name.split('<')[0]
            
            return Call(
                method_name=class_name, # Constructor name is class name
                receiver=None, # Constructor is static-like
                line_number=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                is_async=False,
                is_static=True # Treat as static for resolution purposes
            )
        except Exception as e:
            logger.debug(f"Failed to parse object creation: {str(e)}")
            return None

    def _parse_invocation(self, node: tree_sitter.Node, code: str) -> Optional[Call]:
        """
        Parse an invocation_expression node.
        
        Structure:
        invocation_expression
          - member_access_expression (optional)
            - identifier/member_access_expression (receiver)
            - identifier (method_name)
          - identifier (for direct calls)
          - argument_list
        """
        try:
            method_name = None
            receiver = None
            is_async = False
            
            # Check if this is an await expression
            parent = node.parent
            if parent and parent.type == 'await_expression':
                is_async = True
            
            # Find the method being called
            for child in node.children:
                if child.type == 'member_access_expression':
                    # obj.Method() or Class.Method()
                    parts = self._parse_member_access(child, code)
                    if parts and len(parts) >= 2:
                        receiver = '.'.join(parts[:-1])
                        method_name = parts[-1]
                elif child.type == 'identifier':
                    # Direct call: Method()
                    method_name = self._get_node_text(child, code)
                elif child.type == 'generic_name':
                    # Generic call: Method<T>()
                    method_name = self._get_node_text(child, code).split('<')[0]
                elif child.type == 'argument_list':
                    # Skip argument parsing for now (can be added later)
                    pass
            
            if not method_name:
                return None
            
            return Call(
                method_name=method_name,
                receiver=receiver,
                line_number=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                is_async=is_async,
                is_static=self._is_static_call(receiver)
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse invocation: {str(e)}")
            return None
    
    def _parse_member_access(self, node: tree_sitter.Node, code: str) -> List[str]:
        """
        Parse member access expression into parts.
        
        Example: user.profile.GetName() -> ['user', 'profile', 'GetName']
        """
        parts = []
        
        def extract_parts(n: tree_sitter.Node):
            if n.type == 'member_access_expression':
                # Recursively handle nested member access
                for child in n.children:
                    if child.type != '.':  # Skip the dot token
                        extract_parts(child)
            elif n.type == 'identifier':
                parts.append(self._get_node_text(n, code))
            elif n.type == 'generic_name':
                # Handle generic methods in chains: service.Get<T>()
                text = self._get_node_text(n, code)
                parts.append(text.split('<')[0])
            elif n.type == 'this_expression':
                parts.append('this')
        
        extract_parts(node)
        return parts
    
    def _is_static_call(self, receiver: Optional[str]) -> bool:
        """Heuristic to determine if call is static (based on Pascal case)."""
        if not receiver:
            return False
        
        # If receiver starts with uppercase, likely a class name (static call)
        first_part = receiver.split('.')[0]
        return first_part[0].isupper() if first_part else False
    
    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        """Get text content of a node."""
        if not node:
            return ""
        # Tree-sitter uses byte offsets, so we must slice bytes
        return code.encode('utf-8')[node.start_byte:node.end_byte].decode('utf-8')


class JavaScriptCallAnalyzer:
    """Analyzes JavaScript/TypeScript code to extract function calls."""
    
    def extract_calls(
        self,
        function_node: tree_sitter.Node,
        code: str
    ) -> List[Call]:
        """
        Detect function calls in JavaScript/TypeScript.
        
        Handles:
        - Function calls: myFunc()
        - Method calls: obj.method()
        - Arrow functions: arr.map(x => x * 2)
        - Async/await: await fetchData()
        - Chained calls: api.get().then().catch()
        - Constructor calls: new MyClass()
        
        Args:
            function_node: Tree-sitter node for function
            code: Source code
            
        Returns:
            List of Call objects
        """
        calls = []
        
        def traverse(node: tree_sitter.Node):
            """Recursively traverse AST looking for calls."""
            if node.type == 'call_expression':
                call = self._parse_call_expression(node, code)
                if call:
                    calls.append(call)
            elif node.type == 'new_expression':
                call = self._parse_new_expression(node, code)
                if call:
                    calls.append(call)
            
            # Recursively check children
            for child in node.children:
                traverse(child)
        
        # Start traversal from function body
        body = self._find_function_body(function_node)
        if body:
            traverse(body)
        
        return calls
    
    def _find_function_body(self, function_node: tree_sitter.Node) -> Optional[tree_sitter.Node]:
        """Find the function body node."""
        for child in function_node.children:
            if child.type in ['statement_block', 'expression']:
                return child
        return None
    
    def _parse_new_expression(self, node: tree_sitter.Node, code: str) -> Optional[Call]:
        """
        Parse new_expression (constructor call).
        
        Structure:
        new_expression
          - new
          - constructor: identifier
          - arguments
        """
        try:
            constructor_node = None
            for child in node.children:
                if child.type == 'identifier':
                    constructor_node = child
                    break
            
            if not constructor_node:
                return None
            
            class_name = self._get_node_text(constructor_node, code)
            
            return Call(
                method_name=class_name,
                receiver=None,
                line_number=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                is_async=False,
                is_static=True
            )
        except Exception as e:
            logger.debug(f"Failed to parse new expression: {str(e)}")
            return None
    
    def _parse_call_expression(self, node: tree_sitter.Node, code: str) -> Optional[Call]:
        """
        Parse a call_expression node.
        
        Structure:
        call_expression
          - member_expression (optional): obj.method
          - identifier: functionName
          - arguments
        """
        try:
            method_name = None
            receiver = None
            is_async = False
            
            # Check if this is an await expression
            parent = node.parent
            if parent and parent.type == 'await_expression':
                is_async = True
            
            # Find what's being called
            for child in node.children:
                if child.type == 'member_expression':
                    # obj.method() or module.function()
                    parts = self._parse_member_expression(child, code)
                    if parts and len(parts) >= 2:
                        receiver = '.'.join(parts[:-1])
                        method_name = parts[-1]
                elif child.type == 'identifier':
                    # Direct call: function()
                    method_name = self._get_node_text(child, code)
                elif child.type == 'arguments':
                    # Skip argument parsing for now
                    pass
            
            if not method_name:
                return None
            
            return Call(
                method_name=method_name,
                receiver=receiver,
                line_number=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                is_async=is_async
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse call expression: {str(e)}")
            return None
    
    def _parse_member_expression(self, node: tree_sitter.Node, code: str) -> List[str]:
        """
        Parse member expression into parts.
        
        Example: user.profile.GetName() -> ['user', 'profile', 'GetName']
        """
        parts = []
        
        def extract_parts(n: tree_sitter.Node):
            if n.type == 'member_expression':
                # Recursively handle nested member access
                for child in n.children:
                    if child.type != '.':  # Skip the dot token
                        extract_parts(child)
            elif n.type in ['identifier', 'property_identifier']:
                parts.append(self._get_node_text(n, code))
            elif n.type == 'this':
                parts.append('this')
        
        extract_parts(node)
        return parts
    
    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        """Get text content of a node."""
        if not node:
            return ""
        return code[node.start_byte:node.end_byte]
