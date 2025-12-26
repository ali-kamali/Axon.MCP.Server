"""
Lambda and LINQ analyzer for C# code.
"""

from typing import List, Dict, Any, Optional, Set
import tree_sitter
from dataclasses import dataclass, field
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class LambdaExpression:
    """Represents a lambda expression or anonymous function."""
    name: str  # Generated name like "MethodName.lambda_1"
    start_line: int
    end_line: int
    signature: str  # (x, y) => ...
    parameters: List[str]
    closure_variables: List[str]  # Variables captured from outer scope
    is_async: bool = False
    linq_pattern: Optional[str] = None  # "Select", "Where", etc. if applicable
    body_text: str = ""

class LambdaAnalyzer:
    """Analyzes C# code to extract lambda expressions and LINQ usage."""
    
    def __init__(self):
        self.lambda_count = 0
        
    def extract_lambdas(
        self, 
        method_node: tree_sitter.Node, 
        code: str,
        method_name: str,
        parent_name: str
    ) -> List[LambdaExpression]:
        """
        Extract all lambda expressions from a method body.
        
        Args:
            method_node: Tree-sitter node for the method
            code: Source code string
            method_name: Name of the containing method
            parent_name: Name of the containing class
            
        Returns:
            List of extracted LambdaExpression objects
        """
        self.lambda_count = 0
        lambdas = []
        
        # Local variables defined in the method (to distinguish from closures)
        local_vars = self._extract_local_variables(method_node, code)
        
        # Method parameters
        params = self._extract_method_parameters(method_node, code)
        local_vars.update(params)
        
        def traverse(node: tree_sitter.Node):
            if node.type in ['lambda_expression', 'simple_lambda_expression', 'parenthesized_lambda_expression']:
                try:
                    lambda_obj = self._parse_lambda(node, code, method_name, local_vars)
                    if lambda_obj:
                        lambdas.append(lambda_obj)
                except Exception as e:
                    logger.error(
                        f"Error parsing lambda in {parent_name}.{method_name} at line {node.start_point[0] + 1}: {e}"
                    )
            
            for child in node.children:
                traverse(child)
                
        # Find method body
        body = self._find_method_body(method_node)
        if body:
            traverse(body)
            
        return lambdas

    def _find_method_body(self, method_node: tree_sitter.Node) -> Optional[tree_sitter.Node]:
        """Find the block node containing the method body."""
        for child in method_node.children:
            if child.type == 'block':
                return child
            if child.type == 'arrow_expression_clause': # Expression-bodied member
                return child
        return None

    def _extract_local_variables(self, method_node: tree_sitter.Node, code: str) -> Set[str]:
        """Identify variables defined within the method scope."""
        locals_set = set()
        
        def traverse_locals(node: tree_sitter.Node):
            # Variable declaration: var x = ...
            if node.type == 'variable_declarator':
                name_node = node.child_by_field_name('name')
                if name_node:
                    locals_set.add(self._get_node_text(name_node, code))
            
            # For loops: for (int i = 0; ...)
            elif node.type == 'for_statement':
                for child in node.children:
                    if child.type == 'variable_declaration':
                        for grandchild in child.children:
                            if grandchild.type == 'variable_declarator':
                                name_node = grandchild.child_by_field_name('name')
                                if name_node:
                                    locals_set.add(self._get_node_text(name_node, code))

            # Foreach: foreach (var x in ...)
            elif node.type == 'foreach_statement':
                # foreach (var x in collection) -> Look for identifier in 'left' child inside parens
                # Structure: foreach ( (type? name) in ... )
                # We can iterate children and take the first identifier (variable name)
                found_var = False
                for child in node.children:
                    if child.type == 'identifier':
                        if not found_var:
                            locals_set.add(self._get_node_text(child, code))
                            found_var = True
                    elif child.type == 'variable_declaration': # foreach(var x in ...)
                         for grandchild in child.children:
                             if grandchild.type == 'variable_declarator':
                                 name_node = grandchild.child_by_field_name('name')
                                 if name_node:
                                     locals_set.add(self._get_node_text(name_node, code))
                                     found_var = True
                    if found_var: 
                        break
                
            for child in node.children:
                traverse_locals(child)
                
        traverse_locals(method_node)
        return locals_set

    def _extract_method_parameters(self, method_node: tree_sitter.Node, code: str) -> Set[str]:
        """Extract method parameter names."""
        params = set()
        param_list = method_node.child_by_field_name('parameters')
        if param_list:
            for child in param_list.children:
                if child.type == 'parameter':
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        params.add(self._get_node_text(name_node, code))
        return params

    def _parse_lambda(
        self, 
        node: tree_sitter.Node, 
        code: str, 
        method_name: str,
        outer_locals: Set[str]
    ) -> Optional[LambdaExpression]:
        self.lambda_count += 1
        name = f"{method_name}.lambda_{self.lambda_count}"
        
        # 1. Parameters
        parameters = []
        if node.type == 'simple_lambda_expression':
            # x => ... or (x) => ...
            for child in node.children:
                if child.type == '=>':
                    break
                if child.type == 'parameter':
                     name_node = child.child_by_field_name('name')
                     if name_node:
                         parameters.append(self._get_node_text(name_node, code))
                     else: # Fallback
                         parameters.append(self._get_node_text(child, code))
                if child.type == 'identifier': # simple single param
                     parameters.append(self._get_node_text(child, code))

        elif node.type == 'parenthesized_lambda_expression':
            # (x, y) => ...
            param_list = node.child_by_field_name('parameters')
            if param_list:
                for child in param_list.children:
                    if child.type == 'parameter':
                        name_node = child.child_by_field_name('name')
                        if name_node:
                             parameters.append(self._get_node_text(name_node, code))

        # 2. Body
        body_node = node.child_by_field_name('body')
        body_text = self._get_node_text(body_node, code) if body_node else ""
        
        # 3. LINQ Pattern Detection
        linq_pattern = None
        parent = node.parent
        
        # Skip 'argument' node if present (standard in invocations)
        if parent and parent.type == 'argument':
            parent = parent.parent
            
        if parent and parent.type == 'argument_list':
            invocation = parent.parent
            if invocation and invocation.type == 'invocation_expression':
                member_access = invocation.child_by_field_name('function')
                if member_access:
                     if member_access.type == 'member_access_expression':
                         name_node = member_access.child_by_field_name('name')
                         if name_node:
                             method_name_call = self._get_node_text(name_node, code)
                             linq_methods = [
                                 'Select', 'SelectMany', 'Where', 'OrderBy', 'OrderByDescending', 
                                 'ThenBy', 'ThenByDescending', 'GroupBy', 'GroupJoin', 'Join',
                                 'Any', 'All', 'First', 'FirstOrDefault', 'Single', 'SingleOrDefault', 
                                 'Last', 'LastOrDefault', 'Count', 'LongCount', 'Sum', 'Min', 'Max', 'Average',
                                 'Take', 'TakeWhile', 'Skip', 'SkipWhile', 'Distinct', 'Aggregate',
                                 'Zip', 'Union', 'Intersect', 'Except', 'Concat', 'Cast', 'OfType',
                                 'ToList', 'ToArray', 'ToDictionary', 'ToHashSet', 'AsEnumerable', 'AsQueryable'
                             ]
                             if method_name_call in linq_methods:
                                 linq_pattern = method_name_call
                     elif member_access.type == 'identifier':
                         method_name_call = self._get_node_text(member_access, code)
                         if method_name_call in ['Select', 'Where']: 
                             linq_pattern = method_name_call

        # 4. Closure Variables (Captured Variables)
        closure_vars = set()
        
        # Identify lambda-local variables to avoid false positives
        lambda_locals = set(parameters)
        if body_node:
            local_vars_in_lambda = self._extract_local_variables(body_node, code)
            lambda_locals.update(local_vars_in_lambda)
            
        def scan_body(n: tree_sitter.Node):
            if n.type == 'identifier':
                # Ensure it's not a property/member access (e.g. valid: x, invalid: this.x or obj.x)
                is_member_access_property = False
                parent = n.parent
                if parent and parent.type == 'member_access_expression':
                    # If this identifier is the 'name' part of access (right side), it's a property/field, not variable
                    name_node = parent.child_by_field_name('name')
                    if name_node and name_node.id == n.id:
                        is_member_access_property = True
                
                if not is_member_access_property:
                    var_name = self._get_node_text(n, code)
                    # It's a closure if it's defined in outer method, NOT a parameter, and NOT a local var of the lambda itself
                    if var_name in outer_locals and var_name not in lambda_locals:
                        closure_vars.add(var_name)
            
            for child in n.children:
                scan_body(child)
                
        if body_node:
            scan_body(body_node)

        # 5. Async detection
        is_async = False
        for child in node.children:
            if child.type == 'async':
                is_async = True
                break

        return LambdaExpression(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"({', '.join(parameters)}) => ...",
            parameters=parameters,
            closure_variables=list(closure_vars),
            is_async=is_async,
            linq_pattern=linq_pattern,
            body_text=body_text
        )

    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        """Get text content of a node (using byte slicing for safety)."""
        if not node:
            return ""
        return code.encode('utf-8')[node.start_byte:node.end_byte].decode('utf-8')
