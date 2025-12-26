
    def _extract_minimal_api_endpoints(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        """
        Extract C# Minimal API endpoints like app.MapGet("/path", ...).
        
        Pattern:
        - invocation_expression
          - member_access_expression (app.MapGet, app.MapPost, etc.)
          - argument_list
            - First argument is the route path (string_literal)
        """
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
                                        # Get the path  (extract content between quotes)
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
