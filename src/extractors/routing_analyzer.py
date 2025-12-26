import tree_sitter
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from src.utils.logging_config import get_logger
import re

logger = get_logger(__name__)

@dataclass
class RouteInfo:
    route_template: str
    http_method: str # GET, POST, PUT, DELETE, PATCH, etc.
    parameters: List[str]

class RoutingAnalyzer:
    """
    Analyzes C# code to extract ASP.NET Core routing information.
    Resolves [Route] and HTTP verb attributes to determine full API endpoints.
    """
    
    def __init__(self):
        self.http_verbs = {
            'HttpGet': 'GET',
            'HttpPost': 'POST',
            'HttpPut': 'PUT',
            'HttpDelete': 'DELETE',
            'HttpPatch': 'PATCH',
            'HttpHead': 'HEAD',
            'HttpOptions': 'OPTIONS'
        }

    def analyze(self, class_node: tree_sitter.Node, method_node: tree_sitter.Node, code: str) -> Optional[RouteInfo]:
        """
        Analyze a method within a class to determine its API route.
        Returns None if not an API endpoint.
        """
        # 1. Check if class is a controller (has [ApiController] or [Route])
        # To avoid re-parsing class attributes every time, caller might pass this info?
        # To avoid re-parsing class attributes every time, caller might pass this info?
        # For now, we'll re-extract from class_node.
        class_attributes = self._extract_attributes(class_node, code)
        
        is_controller = any(attr['name'] == 'ApiController' or attr['name'].endswith('Controller') for attr in class_attributes)
        # Also check inheritance? Typically we look for [ApiController] or [Route] for explicit routing.
        # Let's rely on [Route] presence on class or method, or [HttpGet] etc.
        
        class_route = self._find_route_template(class_attributes)
        
        # 2. Extract method attributes
        method_attributes = self._extract_attributes(method_node, code)
        
        # 3. Determine HTTP Method and Action Route
        http_method = "GET" # Default? actually if public and in controller, usually GET? 
        # But safest to look for explicit verb. If no verb but is public in controller, logic is complex.
        # We will strictly require at least one HTTP attribute OR a [Route] attribute on the method to consider it an endpoint
        # unless the class has [ApiController].
        
        explicit_verb_found = False
        action_route = None
        
        for attr in method_attributes:
            name = attr['name']
            if name in self.http_verbs:
                http_method = self.http_verbs[name]
                explicit_verb_found = True
                # Check for arguments: [HttpGet("template")]
                if attr.get('arguments') and len(attr['arguments']) > 0:
                    action_route = self._clean_route_arg(attr['arguments'][0])
            elif name == 'Route':
                 if attr.get('arguments') and len(attr['arguments']) > 0:
                    action_route = self._clean_route_arg(attr['arguments'][0])

        if not explicit_verb_found and not action_route:
             # If class has [ApiController] and method is public, it might be an endpoint.
             # But without attributes, conventions apply.
             # For now, let's limit to explicit attributes to avoid noise.
             if not any(a['name'] == 'Route' for a in method_attributes):
                 return None

        # 4. Combine Routes
        # Resolve [controller] token
        controller_name_node = class_node.child_by_field_name('name')
        if not controller_name_node:
            logger.warning("Could not find class name node for controller routing")
            return None
            
        controller_name = self._get_node_text(controller_name_node, code)
        if controller_name.endswith('Controller'):
            controller_name_token = controller_name[:-10] # Remove 'Controller' suffix
        else:
            controller_name_token = controller_name

        full_route = ""
        
        if class_route:
            full_route = class_route.replace('[controller]', controller_name_token)
        
        if action_route:
            # Resolve [action] token
            method_name_node = method_node.child_by_field_name('name')
            if method_name_node:
                method_name = self._get_node_text(method_name_node, code)
                action_route = action_route.replace('[action]', method_name)
            
            if action_route.startswith('/'):
                # Absolute route override
                full_route = action_route.lstrip('/')
            else:
                if full_route:
                    full_route = f"{full_route}/{action_route}"
                else:
                    full_route = action_route
        
        # Cleanup: Remove duplicate slashes
        full_route = re.sub(r'/+', '/', full_route)
        
        return RouteInfo(
            route_template=full_route,
            http_method=http_method,
            parameters=[] # To be implemented if we want to extract {id} parameters
        )

    def _extract_attributes(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        # Simplified attribute extraction
        attributes = []
        # In C# AST, attribute_list -> attribute
        # We need to scan children or modifier lists logic
        
        
        # Helper to find attribute lists
        # cursor = node.walk() # Unused
        
        # Attributes usually appear before the declaration or in a separate modifier list node depending on TS version
        # For tree-sitter-c-sharp:
        # method_declaration
        #   attribute_list
        #     attribute
        
        for child in node.children:
            if child.type == 'attribute_list':
                for attr in child.children:
                    if attr.type == 'attribute':
                        name_node = attr.child_by_field_name('name')
                        if name_node:
                            name = self._get_node_text(name_node, code)
                            args = []
                            # For tree-sitter-c-sharp, arguments might be in 'argument_list' child
                            # Structure: attribute -> name, argument_list
                            arg_list = attr.child_by_field_name('arguments') # Field name is arguments?
                            
                            # Fallback if field name doesn't work (check children types)
                            if not arg_list:
                                arg_list = self._find_child_by_type(attr, 'attribute_argument_list')
                            
                            if arg_list:
                                for arg in arg_list.children:
                                    if arg.type == 'attribute_argument':
                                         # Logic to get text of argument expression
                                         # attribute_argument -> expression?
                                         expr = arg.child_by_field_name('expression')
                                         if expr:
                                             args.append(self._get_node_text(expr, code))
                                         else:
                                             # Fallback to children excluding name/colon
                                             for grandchild in arg.children:
                                                 if grandchild.type not in ('name_colon', ':'):
                                                     args.append(self._get_node_text(grandchild, code))
                                                     break
                                                     
                                    elif arg.type not in ('(', ')', ','): 
                                         # Sometimes arguments are direct children of list? 
                                         # Let's grab text of interesting nodes
                                         text = self._get_node_text(arg, code)
                                         if text not in ('(', ')', ','):
                                             args.append(text)
                            
                            attributes.append({'name': name, 'arguments': args})
        return attributes

    def _find_child_by_type(self, node: tree_sitter.Node, type_name: str) -> Optional[tree_sitter.Node]:
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _find_route_template(self, attributes: List[Dict[str, Any]]) -> Optional[str]:
        for attr in attributes:
            if attr['name'] == 'Route' and attr.get('arguments'):
                return self._clean_route_arg(attr['arguments'][0])
        return None

    def _clean_route_arg(self, arg: str) -> str:
        # arg comes as string literal, e.g. "api/[controller]"
        if not arg:
            return ""
        return arg.strip('"').strip("'")

    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        if not node:
            return ""
        snippet = code[node.start_byte:node.end_byte]
        return snippet.decode('utf8') if isinstance(snippet, bytes) else snippet
