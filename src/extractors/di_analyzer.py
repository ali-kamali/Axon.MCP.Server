import tree_sitter
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class DIRegistration:
    service_type: str
    implementation_type: Optional[str]
    lifetime: str
    line: int
    column: int
    code_snippet: str

class DIAnalyzer:
    """
    Analyzes C# code (Startup.cs, Program.cs) for Dependency Injection registrations.
    """
    
    def __init__(self):
        self.registrations: List[DIRegistration] = []
        # Common DI methods in ASP.NET Core
        self.di_methods = {
            'AddSingleton', 'AddScoped', 'AddTransient', 
            'AddDbContext', 'AddHttpClient', 'AddHostedService'
        }

    def analyze(self, node: tree_sitter.Node, code: str) -> List[DIRegistration]:
        """
        Analyze the AST node for DI registrations.
        """
        self.registrations = []
        self._traverse(node, code)
        return self.registrations

    def _traverse(self, node: tree_sitter.Node, code: str, depth: int = 0):
        if depth > 1000:
            return

        if node.type == 'invocation_expression':
            self._check_invocation(node, code)
        
        for child in node.children:
            self._traverse(child, code, depth + 1)

    def _check_invocation(self, node: tree_sitter.Node, code: str):
        # Look for member access: services.AddScoped...
        member_access = node.child_by_field_name('function')
        if not member_access:
            return
        
        # logger.info(f"Invoking: {self._get_node_text(member_access, code)} (Type: {member_access.type})")
        
        if member_access.type not in ('member_access_expression', 'generic_name'):
            return

        # Check for generic version: AddScoped<IFoo, Foo>()
        # or simple version: AddScoped(typeof(IFoo), typeof(Foo))
        
        # Handle generic name in member access (AddScoped<T>)
        # The structure is usually:
        # invocation_expression
        #   function: generic_name
        #     identifier: AddScoped
        #     type_argument_list: <IFoo, Foo>
        
        # Or:
        # invocation_expression
        #   function: member_access_expression
        #     expression: identifier (services)
        #     name: generic_name
        #       identifier: AddScoped
        #       type_argument_list: ...

        actual_method_name = ""
        generic_args = []
        
        if member_access.type == 'generic_name':
             # Direct generic call: AddScoped<IFoo, Foo>()
             for child in member_access.children:
                if child.type == 'identifier':
                    actual_method_name = self._get_node_text(child, code)
                elif child.type == 'type_argument_list':
                    generic_args = self._extract_type_arguments(child, code) 
        elif member_access.type == 'member_access_expression':
             name_node = member_access.child_by_field_name('name')
             if name_node:
                 # logger.info(f"Member access name node type: {name_node.type}")
                 if name_node.type == 'generic_name':
                     # generic_name structure: identifier, type_argument_list
                     id_node = name_node.child_by_field_name('function') # wait, generic_name doesn't have function field usually
                     
                     # Let's define manual traversal for generic_name children since field names vary
                     # Expected: identifier, type_argument_list
                     for child in name_node.children:
                        if child.type == 'identifier':
                            actual_method_name = self._get_node_text(child, code)
                        elif child.type == 'type_argument_list':
                            generic_args = self._extract_type_arguments(child, code)
                            
                 elif name_node.type == 'identifier':
                     actual_method_name = self._get_node_text(name_node, code)
        
        if actual_method_name in self.di_methods:
            service_type = None
            impl_type = None
            
            # Case 1: Generic arguments <IService, Service>
            if generic_args:
                if len(generic_args) >= 1:
                    service_type = generic_args[0]
                if len(generic_args) >= 2:
                    impl_type = generic_args[1]
                # If only one arg: AddSingleton<Service>(), implementation is same as service
                if len(generic_args) == 1:
                    impl_type = service_type

            # Case 2: Arguments (typeof(IService), typeof(Service))
            # Fallback if no generics
            if not service_type:
                args = node.child_by_field_name('arguments')
                if args:
                    arg_types = self._extract_typeof_arguments(args, code)
                    if len(arg_types) >= 1:
                        service_type = arg_types[0]
                    if len(arg_types) >= 2:
                        impl_type = arg_types[1]
                    elif len(arg_types) == 1:
                         # AddSingleton(typeof(Service)) -> impl = service
                         impl_type = service_type

            if service_type:
                self.registrations.append(DIRegistration(
                    service_type=service_type,
                    implementation_type=impl_type,
                    lifetime=actual_method_name.replace('Add', ''),
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    code_snippet=self._get_node_text(node, code)
                ))
            else:
                logger.debug(f"Skipped registration at line {node.start_point[0] + 1}: no service type found")

 

    def _extract_type_arguments(self, node: tree_sitter.Node, code: str) -> List[str]:
        types = []
        for child in node.children:
            if child.type in ('identifier', 'qualified_name', 'generic_name', 'predefined_type'):
                types.append(self._get_node_text(child, code))
        return types

    def _extract_typeof_arguments(self, args_node: tree_sitter.Node, code: str) -> List[str]:
        # args_node is argument_list
        types = []
        for arg in args_node.children:
            if arg.type == 'argument':
                # check for typeof_expression
                expr = arg.children[0] if arg.children else None
                if expr and expr.type == 'typeof_expression':
                    # typeof(Type)
                    type_node = expr.child_by_field_name('type')
                    if type_node:
                        types.append(self._get_node_text(type_node, code))
        return types

    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        if not node:
            return ""
        snippet = code[node.start_byte:node.end_byte]
        return snippet.decode('utf8') if isinstance(snippet, bytes) else snippet

    def _find_child_by_type(self, node: tree_sitter.Node, type_name: str) -> Optional[tree_sitter.Node]:
        for child in node.children:
            if child.type == type_name:
                return child
        return None
