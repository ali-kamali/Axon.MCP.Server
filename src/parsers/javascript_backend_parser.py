import tree_sitter
import re
from typing import List, Optional, Dict, Any
from src.config.enums import SymbolKindEnum
from src.parsers.base_parser import ParsedSymbol

class BackendAnalyzer:
    """Analyzer for backend JavaScript/TypeScript frameworks (Express, NestJS)."""
    
    def analyze_node(self, node: tree_sitter.Node, code: str, parent_name: Optional[str] = None) -> List[ParsedSymbol]:
        """
        Analyze a node for backend patterns.
        
        Args:
            node: AST node
            code: Source code
            parent_name: Parent symbol name
            
        Returns:
            List of discovered backend symbols
        """
        symbols = []
        
        # Express.js routes
        if node.type == 'call_expression':
            express_route = self._analyze_express_route(node, code, parent_name)
            if express_route:
                symbols.append(express_route)
        
        # NestJS Controllers (handled during class parsing in main parser, but we can provide helpers)
        # Actually, we can detect them here if we are traversing, but usually classes are handled by the main parser.
        # However, we can add metadata to the class symbol if we detect it's a controller.
        # For now, let's focus on standalone detection if possible, or helper methods.
        
        return symbols

    def _analyze_express_route(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> Optional[ParsedSymbol]:
        """
        Detect Express.js routes like app.get('/path', ...) or router.post('/path', ...).
        """
        # Check function callee
        function_node = node.child_by_field_name('function')
        if not function_node:
            return None
            
        func_text = self._get_node_text(function_node, code)
        
        # Match patterns like app.get, router.post, etc.
        # Common HTTP methods
        methods = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']
        
        parts = func_text.split('.')
        if len(parts) == 2 and parts[1] in methods:
            # Likely a route definition
            # Check arguments
            args_node = node.child_by_field_name('arguments')
            if args_node and args_node.children:
                # First argument should be the path string
                first_arg = None
                for child in args_node.children:
                    if child.type == 'string':
                        first_arg = child
                        break
                    elif child.type == '(': # skip opening parenthesis
                        continue
                    else:
                        # If first arg is not string, might be middleware, but usually path is first
                        break
                
                if first_arg:
                    path = self._get_node_text(first_arg, code).strip('\'"`')
                    method = parts[1].upper()
                    
                    return ParsedSymbol(
                        kind=SymbolKindEnum.ENDPOINT,
                        name=f"{method} {path}",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_column=node.start_point[1],
                        end_column=node.end_point[1],
                        signature=f"{func_text}('{path}')",
                        documentation=f"Express.js {method} route",
                        structured_docs={
                            'type': 'express_route',
                            'method': method,
                            'path': path,
                            'handler': func_text
                        },
                        parent_name=parent_name,
                        fully_qualified_name=f"{parent_name}.{method}_{path}" if parent_name else f"{method}_{path}"
                    )
        
        return None

    def analyze_nestjs_class(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a class for NestJS @Controller decorator.
        Returns metadata dict if found.
        
        Note: In TypeScript AST, decorators can be:
        1. Direct children of class_declaration
        2. Siblings within export_statement
        """
        decorators = self._get_decorators(node, code)
        
        # Also check parent node if this is inside an export_statement
        if node.parent and node.parent.type == 'export_statement':
            decorators.extend(self._get_decorators(node.parent, code))
        
        for dec in decorators:
            if dec['name'] == 'Controller':
                # Extract path from @Controller('path')
                path = '/'
                if dec['arguments']:
                    path = dec['arguments'][0].strip('\'"')
                
                return {
                    'is_controller': True,
                    'path': path
                }
        return None

    def analyze_nestjs_method(self, node: tree_sitter.Node, code: str, controller_path: str = "/") -> Optional[Dict[str, Any]]:
        """
        Analyze a method for NestJS HTTP decorators (@Get, @Post, etc.).
        """
        decorators = self._get_decorators(node, code)
        methods = ['Get', 'Post', 'Put', 'Delete', 'Patch', 'Options', 'Head', 'All']
        
        for dec in decorators:
            if dec['name'] in methods:
                method = dec['name'].upper()
                path = ''
                if dec['arguments']:
                    path = dec['arguments'][0].strip('\'"')
                
                # Combine controller path and method path
                full_path = f"{controller_path}/{path}".replace('//', '/')
                if full_path.endswith('/') and len(full_path) > 1:
                    full_path = full_path[:-1]
                
                return {
                    'is_endpoint': True,
                    'method': method,
                    'path': full_path,
                    'route_path': path
                }
        return None

    def _get_decorators(self, node: tree_sitter.Node, code: str) -> List[Dict[str, Any]]:
        """
        Extract decorators from a node (class or method).
        
        Decorators can appear as:
        1. Direct children of the node
        2. Siblings before the node
        """
        decorators = []
        
        # Check for 'decorator' nodes in children
        for child in node.children:
            if child.type == 'decorator':
                decorators.append(self._parse_decorator(child, code))
        
        # For method_definition, check previous siblings (decorators come before methods)
        if node.type == 'method_definition':
            sibling = node.prev_sibling
            while sibling:
                if sibling.type == 'decorator':
                    decorators.insert(0, self._parse_decorator(sibling, code))
                    sibling = sibling.prev_sibling
                elif sibling.type in ['{', '}', ',']:  # Skip syntax tokens
                    sibling = sibling.prev_sibling
                else:
                    break
        
        return decorators

    def _parse_decorator(self, node: tree_sitter.Node, code: str) -> Dict[str, Any]:
        """Parse a decorator node."""
        text = self._get_node_text(node, code)
        # @Controller('users') -> name=Controller, args=['users']
        name_part = text.split('(')[0].strip('@')
        args = []
        
        if '(' in text:
            args_text = text[text.find('(')+1 : text.rfind(')')]
            # Simple split by comma, ignoring nested parens/quotes would be better but simple for now
            args = [a.strip() for a in args_text.split(',') if a.strip()]
            
        return {'name': name_part, 'arguments': args}

    def _get_node_text(self, node: tree_sitter.Node, code: str) -> str:
        """Get text content of a node."""
        return code[node.start_byte:node.end_byte].decode('utf-8') if isinstance(code, bytes) else code[node.start_byte:node.end_byte]
