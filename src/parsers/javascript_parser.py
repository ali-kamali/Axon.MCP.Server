import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript
import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.tree_sitter_parser import TreeSitterParser
from src.parsers.base_parser import ParsedSymbol
from src.parsers.react_analyzer import ReactAnalyzer
from src.parsers.javascript_backend_parser import BackendAnalyzer

class JavaScriptParser(TreeSitterParser):
    """JavaScript/JSX language parser using Tree-sitter."""
    
    def __init__(self):
        super().__init__(LanguageEnum.JAVASCRIPT, tree_sitter_javascript)
        self.react_analyzer = ReactAnalyzer()
        self.backend_analyzer = BackendAnalyzer()
        self.api_calls = []  # Store detected API calls for Phase 2
        self.events = []  # Store detected events for Phase 2
    
    def extract_imports(self, node: tree_sitter.Node, code: str) -> List[str]:
        """Extract imported modules."""
        imports = []
        
        def traverse(n):
            # ES6 Imports
            if n.type == 'import_statement':
                source = self._find_child_by_type(n, 'string')
                if source:
                    imports.append(self._get_node_text(source, code).strip('"\''))
            
            # CommonJS require
            elif n.type == 'call_expression':
                func = n.children[0] if n.children else None
                if func and self._get_node_text(func, code) == 'require':
                    args = self._find_child_by_type(n, 'arguments')
                    if args and args.children:
                        # args children: ( "module" )
                        for child in args.children:
                            if child.type == 'string':
                                imports.append(self._get_node_text(child, code).strip('"\''))

            for child in n.children:
                traverse(child)
        
        traverse(node)
        return imports

    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a JavaScript file."""
        return file_path.suffix.lower() in ['.js', '.jsx', '.mjs']
    
    def _extract_symbols(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        """Extract JavaScript symbols from AST."""
        symbols = []
        
        def traverse(n: tree_sitter.Node, parent_name: Optional[str] = None):
            # Function declarations
            if n.type == 'function_declaration':
                symbol = self._parse_function(n, code, parent_name)
                symbols.append(symbol)
            
            # Arrow functions assigned to variables
            elif n.type in ['lexical_declaration', 'variable_declaration']:
                symbols.extend(self._parse_variable_functions(n, code, parent_name))
            
            # Class declarations
            elif n.type == 'class_declaration':
                symbol = self._parse_class(n, code, parent_name)
                symbols.append(symbol)
                parent_name = symbol.fully_qualified_name
            
            # Method definitions (inside classes)
            elif n.type == 'method_definition':
                symbols.append(self._parse_method(n, code, parent_name))
            
            # Recursively traverse children
            for child in n.children:
                traverse(child, parent_name)
        
        traverse(node)
        
        # Second pass: Analyze for backend patterns (Express routes) and API calls
        def traverse_backend(n: tree_sitter.Node, parent_name: Optional[str] = None):
            # Express routes
            if n.type == 'call_expression':
                # Check for Express routes first
                express_route = self.backend_analyzer._analyze_express_route(n, code, parent_name)
                if express_route:
                    symbols.append(express_route)
                
                # Extract API calls (frontend or backend-to-backend)
                api_call = self._extract_api_call(n, code)
                if api_call:
                    self.api_calls.append(api_call)
                
                # Extract events (Phase 2)
                event = self._extract_event(n, code)
                if event:
                    self.events.append(event)
            
            for child in n.children:
                traverse_backend(child, parent_name)
                
        traverse_backend(node)
        return symbols
    
    def _parse_function(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse a function declaration."""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "anonymous"
        
        parameters = self._extract_parameters(node, code)
        return_type = self._extract_return_type(node, code)
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Analyze if this is a React component (functional)
        if name and name[0].isupper():  # Component naming convention
            react_component = self.react_analyzer.analyze_component_from_symbol(
                {
                    'name': name,
                    'signature': self._get_function_signature(node, code),
                    'start_line': node.start_point[0],
                    'parameters': parameters
                },
                code
            )
            
            if react_component:
                if not jsdoc:
                    jsdoc = {}
                jsdoc['react_component'] = {
                    'type': react_component.component_type,
                    'is_hoc': react_component.is_hoc,
                    'hooks': [{'name': h.name, 'line': h.line_number, 'is_custom': h.is_custom} for h in react_component.hooks],
                    'props': react_component.props
                }
        
        return ParsedSymbol(
            kind=SymbolKindEnum.FUNCTION,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_function_signature(node, code),
            documentation=plain_doc,
            structured_docs=jsdoc,
            parameters=parameters,
            return_type=return_type,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _parse_variable_functions(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> List[ParsedSymbol]:
        """Parse variable declarations that contain arrow functions."""
        symbols = []
        
        for child in node.children:
            if child.type == 'variable_declarator':
                name_node = self._find_child_by_type(child, 'identifier')
                value_node = child.children[-1] if child.children else None
                
                if value_node and value_node.type in ['arrow_function', 'function']:
                    name = self._get_node_text(name_node, code) if name_node else "anonymous"
                    parameters = self._extract_parameters(value_node, code)
                    
                    node_text = self._get_node_text(node, code)
                    signature = node_text.split('=')[0].strip() + ' => {...}' if '=' in node_text else node_text[:200]
                    
                    # Extract JSDoc documentation
                    jsdoc = self._find_jsdoc(node, code)
                    plain_doc = self._find_documentation(node, code)
                    
                    symbols.append(ParsedSymbol(
                        kind=SymbolKindEnum.FUNCTION,
                        name=name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_column=node.start_point[1],
                        end_column=node.end_point[1],
                        signature=signature,
                        documentation=plain_doc,
                        structured_docs=jsdoc,
                        parameters=parameters,
                        parent_name=parent_name,
                        fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
                    ))
        
        return symbols
    
    def _parse_class(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse a class declaration."""
        # Try both identifier (JavaScript) and type_identifier (TypeScript)
        name_node = self._find_child_by_type(node, 'identifier') or self._find_child_by_type(node, 'type_identifier')
        name = self._get_node_text(name_node, code) if name_node else "AnonymousClass"
        
        node_text = self._get_node_text(node, code)
        signature = node_text.split('{')[0].strip() if '{' in node_text else node_text[:200]
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Analyze if this is a React component
        react_component = self.react_analyzer.analyze_component_from_symbol(
            {
                'name': name,
                'signature': signature,
                'start_line': node.start_point[0],
                'parameters': []
            },
            code
        )
        
        # Add React metadata to structured_docs
        if react_component and jsdoc:
            jsdoc['react_component'] = {
                'type': react_component.component_type,
                'is_hoc': react_component.is_hoc,
                'hooks': [{'name': h.name, 'line': h.line_number, 'is_custom': h.is_custom} for h in react_component.hooks],
                'props': react_component.props
            }
        elif react_component:
            jsdoc = {
                'react_component': {
                    'type': react_component.component_type,
                    'is_hoc': react_component.is_hoc,
                    'hooks': [{'name': h.name, 'line': h.line_number, 'is_custom': h.is_custom} for h in react_component.hooks],
                    'props': react_component.props
                }
            }
        
        # Analyze for NestJS Controller
        nestjs_info = self.backend_analyzer.analyze_nestjs_class(node, code)
        if nestjs_info:
            if not jsdoc:
                jsdoc = {}
            jsdoc['nestjs_controller'] = nestjs_info
            
        return ParsedSymbol(
            kind=SymbolKindEnum.CLASS,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=signature,
            documentation=plain_doc,
            structured_docs=jsdoc,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _parse_method(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse a method definition inside a class."""
        # Get method name (property_identifier or identifier)
        name_node = self._find_child_by_type(node, 'property_identifier')
        if not name_node:
            name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "anonymous"
        
        parameters = self._extract_parameters(node, code)
        
        # Extract return type (TypeScript support)
        return_type = self._extract_return_type(node, code)
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        # Analyze for NestJS Endpoint
        nestjs_endpoint = self.backend_analyzer.analyze_nestjs_method(node, code, "")
        if nestjs_endpoint:
            if not jsdoc:
                jsdoc = {}
            jsdoc['nestjs_endpoint'] = nestjs_endpoint
            
        return ParsedSymbol(
            kind=SymbolKindEnum.METHOD,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_function_signature(node, code),
            documentation=plain_doc,
            structured_docs=jsdoc,
            parameters=parameters,
            return_type=return_type,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _extract_return_type(self, node: tree_sitter.Node, code: str) -> Optional[str]:
        """Extract return type annotation (for TypeScript)."""
        # Look for type_annotation node
        type_annotation = self._find_child_by_type(node, 'type_annotation')
        if type_annotation:
            # Get the type (skip the ':' token)
            for child in type_annotation.children:
                if child.type != ':':
                    return self._get_node_text(child, code)
        return None
    
    def _extract_parameters(self, node: tree_sitter.Node, code: str) -> List[dict]:
        """Extract function parameters with TypeScript type annotations."""
        parameters = []
        formal_params = self._find_child_by_type(node, 'formal_parameters')
        
        if formal_params:
            for child in formal_params.children:
                if child.type in ['identifier', 'required_parameter', 'optional_parameter']:
                    param_text = self._get_node_text(child, code)
                    
                    # Extract name and type for TypeScript
                    if ':' in param_text:
                        parts = param_text.split(':', 1)
                        param_name = parts[0].strip()
                        param_type = parts[1].strip() if len(parts) > 1 else None
                    else:
                        param_name = param_text.strip()
                        param_type = None
                    
                    parameters.append({'name': param_name, 'type': param_type})
        
        return parameters
    
    def _get_function_signature(self, node: tree_sitter.Node, code: str) -> str:
        """Get function signature."""
        text = self._get_node_text(node, code)
        # Extract up to opening brace
        if '{' in text:
            return text.split('{')[0].strip()
        return text[:200]  # Limit length
    
    def _find_jsdoc(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSDoc/TSDoc comments before a symbol.
        
        Parses JSDoc tags like:
        /**
         * @description Function description
         * @param {string} name - Parameter description
         * @param {number} age - Age parameter
         * @returns {User} User object
         * @throws {Error} If validation fails
         * @example
         * const user = createUser('John', 30);
         * @deprecated Use createUserV2 instead
         * @see {@link UserService}
         * @template T Type parameter
         * @typeParam T - Type parameter description
         */
        
        Args:
            node: AST node to find documentation for
            code: Source code
            
        Returns:
            Dictionary with structured documentation or None if not found
        """
        # Get the lines before this node
        start_line = node.start_point[0]
        if start_line == 0:
            return None
        
        lines = code.split('\n')
        doc_lines = []
        in_doc_comment = False
        
        # Look backwards from the node's start line
        for i in range(start_line - 1, -1, -1):
            line = lines[i].strip()
            
            if line.endswith('*/'):
                # Found end of JSDoc comment, start collecting
                in_doc_comment = True
                # Remove */ and add the line
                doc_lines.insert(0, line[:-2].strip())
            elif in_doc_comment:
                if line.startswith('/**'):
                    # Found start of JSDoc comment
                    doc_lines.insert(0, line[3:].strip())
                    break
                elif line.startswith('*'):
                    # Middle of JSDoc comment
                    doc_lines.insert(0, line[1:].strip())
                else:
                    # Malformed comment, stop
                    break
            elif line.startswith('//') or line == '':
                # Regular comment or empty line before JSDoc, continue
                continue
            else:
                # Hit non-comment line, stop
                break
        
        if not doc_lines:
            return None
        
        # Parse JSDoc tags from documentation
        doc_text = '\n'.join(doc_lines)
        structured_docs = {}
        
        # Extract description (text before first @ tag)
        desc_match = re.match(r'^([^@]*)', doc_text, re.DOTALL)
        if desc_match and desc_match.group(1).strip():
            structured_docs['description'] = desc_match.group(1).strip()
        
        # Extract @param tags
        param_matches = re.findall(
            r'@param\s+(?:\{([^\}]+)\}\s+)?(\w+)(?:\s*-\s*(.*))?', 
            doc_text, 
            re.MULTILINE
        )
        if param_matches:
            structured_docs['params'] = [
                {
                    'name': name,
                    'type': param_type if param_type else None,
                    'description': desc.strip() if desc else None
                }
                for param_type, name, desc in param_matches
            ]
        
        # Extract @returns/@return tag
        returns_match = re.search(
            r'@returns?\s+(?:\{([^\}]+)\}\s+)?(.+)', 
            doc_text, 
            re.MULTILINE
        )
        if returns_match:
            structured_docs['returns'] = {
                'type': returns_match.group(1) if returns_match.group(1) else None,
                'description': returns_match.group(2).strip() if returns_match.group(2) else None
            }
        
        # Extract @example tag
        example_match = re.search(r'@example\s+(.*?)(?=@|\Z)', doc_text, re.DOTALL)
        if example_match:
            structured_docs['example'] = example_match.group(1).strip()
        
        # Extract @throws/@exception tags
        throws_matches = re.findall(
            r'@(?:throws|exception)\s+(?:\{([^\}]+)\}\s+)?(.+)', 
            doc_text, 
            re.MULTILINE
        )
        if throws_matches:
            structured_docs['throws'] = [
                {'type': exc_type if exc_type else None, 'description': desc.strip()}
                for exc_type, desc in throws_matches
            ]
        
        # Extract @deprecated tag
        deprecated_match = re.search(r'@deprecated\s+(.+)', doc_text, re.MULTILINE)
        if deprecated_match:
            structured_docs['deprecated'] = deprecated_match.group(1).strip()
        
        # Extract @see tags
        see_matches = re.findall(r'@see\s+(?:\{@link\s+([^\}]+)\}|(\S+))', doc_text)
        if see_matches:
            structured_docs['see_also'] = [
                link or ref for link, ref in see_matches
            ]
        
        # Extract @template/@typeParam tags (TypeScript)
        template_matches = re.findall(
            r'@(?:template|typeParam)\s+(\w+)(?:\s*-\s*(.*))?', 
            doc_text, 
            re.MULTILINE
        )
        if template_matches:
            structured_docs['type_params'] = [
                {'name': name, 'description': desc.strip() if desc else None}
                for name, desc in template_matches
            ]
        
        # Extract @typedef tag (TypeScript type definitions)
        typedef_match = re.search(r'@typedef\s+(?:\{([^\}]+)\}\s+)?(\w+)', doc_text)
        if typedef_match:
            structured_docs['typedef'] = {
                'type': typedef_match.group(1) if typedef_match.group(1) else None,
                'name': typedef_match.group(2)
            }
        
        # Extract @author tag
        author_match = re.search(r'@author\s+(.+)', doc_text, re.MULTILINE)
        if author_match:
            structured_docs['author'] = author_match.group(1).strip()
        
        # Extract @since tag
        since_match = re.search(r'@since\s+(.+)', doc_text, re.MULTILINE)
        if since_match:
            structured_docs['since'] = since_match.group(1).strip()
        
        return structured_docs if structured_docs else None
    
    def _extract_api_call(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """
        Extract HTTP API call from a call_expression node.
        
        Detects patterns:
        - fetch(url, options)
        - axios.get(url), axios.post(url, data), etc.
        - axios(config)
        - this.http.get(url) (Angular)
        - this.$http.get(url) (Vue)
        - Vue.http.get(url)
        
        Args:
            node: call_expression AST node
            code: Source code
            
        Returns:
            Dictionary with API call details or None if not an API call
        """
        if node.type != 'call_expression':
            return None
        
        # Get the function being called
        function_node = node.children[0] if node.children else None
        if not function_node:
            return None
        
        function_text = self._get_node_text(function_node, code)
        
        # Pattern 1: fetch(url, options)
        if function_text == 'fetch' or function_text.endswith('.fetch'):
            return self._extract_fetch_call(node, code)
        
        # Pattern 2: axios.METHOD(url) or axios(config)
        elif 'axios' in function_text:
            return self._extract_axios_call(node, function_node, code)
        
        # Pattern 3: Node.js http/https.request(url, options)
        elif function_text in ['http.request', 'https.request', 'http.get', 'https.get']:
            return self._extract_node_http_call(node, function_node, code)
            
        # Pattern 4: Angular HttpClient - this.http.METHOD(url)
        elif '.http.' in function_text or function_text.startswith('http.'):
            return self._extract_angular_http_call(node, function_node, code)
        
        # Pattern 5: Vue $http - this.$http.METHOD(url)
        elif '.$http.' in function_text or function_text.startswith('$http.'):
            return self._extract_vue_http_call(node, function_node, code)
            
        # Pattern 6: got(url) or got.get(url)
        elif function_text == 'got' or function_text.startswith('got.'):
            return self._extract_got_call(node, function_node, code)
            
        # Pattern 7: superagent.get(url)
        elif function_text.startswith('superagent.') or function_text.startswith('request.'): # superagent often imported as request
            return self._extract_superagent_call(node, function_node, code)

        # Pattern 8: React Query / TanStack Query
        elif function_text in ['useQuery', 'useMutation', 'useInfiniteQuery']:
            return self._extract_react_query_call(node, function_node, code)
            
        # Pattern 9: SWR
        elif function_text == 'useSWR':
            return self._extract_swr_call(node, function_node, code)
            
        # Pattern 10: Apollo Client
        elif function_text in ['useQuery', 'useMutation', 'useSubscription', 'useApolloQuery']:
            return self._extract_apollo_call(node, function_node, code)

        # Pattern 11: Nuxt 3 / Vue 3
        elif function_text in ['useFetch', '$fetch', 'useAsyncData']:
            return self._extract_nuxt_call(node, function_node, code)
            
        # Pattern 12: Next.js Data Fetching
        elif function_text in ['getServerSideProps', 'getStaticProps']:
            return self._extract_nextjs_data_fetching(node, function_node, code)
            
        # Pattern 13: Redux Toolkit Query
        elif function_text in ['createApi', 'fetchBaseQuery']:
            return self._extract_rtk_query_call(node, function_node, code)
        
        return None
    
    def _extract_fetch_call(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract fetch() API call details."""
        # fetch(url, options)
        args = self._get_call_arguments(node, code)
        if not args or len(args) == 0:
            return None
        
        url = args[0]
        method = 'GET'  # fetch defaults to GET
        
        # Check options object for method
        if len(args) > 1:
            options_text = args[1]
            # Look for method: 'POST', method: "PUT", etc.
            method_match = re.search(r'method\s*:\s*["\'](\w+)["\']', options_text)
            if method_match:
                method = method_match.group(1).upper()
        
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': method,
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'fetch',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',  # Default, can be overridden
            'context_metadata': {
                'raw_url': url,
                'has_options': len(args) > 1
            }
        }
    
    def _extract_axios_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract axios API call details."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        # axios.METHOD(url, ...)
        if '.' in function_text:
            parts = function_text.split('.')
            method_name = parts[-1]
            
            # axios.get, axios.post, etc.
            if method_name.lower() in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                if not args or len(args) == 0:
                    return None
                
                url = args[0]
                url_pattern, is_dynamic = self._normalize_url(url)
                
                return {
                    'http_method': method_name.upper(),
                    'url_pattern': url_pattern,
                    'is_dynamic_url': is_dynamic,
                    'http_client_library': 'axios',
                    'line_number': node.start_point[0] + 1,
                    'call_type': 'frontend_to_backend',
                    'context_metadata': {
                        'raw_url': url,
                        'has_data': len(args) > 1
                    }
                }
        
        # axios(config) - config object
        if function_text == 'axios' and args and len(args) > 0:
            config_text = args[0]
            # Try to extract method and url from config object
            method_match = re.search(r'method\s*:\s*["\'](\w+)["\']', config_text)
            url_match = re.search(r'url\s*:\s*([^,}]+)', config_text)
            
            if url_match:
                url = url_match.group(1).strip()
                method = method_match.group(1).upper() if method_match else 'GET'
                url_pattern, is_dynamic = self._normalize_url(url)
                
                return {
                    'http_method': method,
                    'url_pattern': url_pattern,
                    'is_dynamic_url': is_dynamic,
                    'http_client_library': 'axios',
                    'line_number': node.start_point[0] + 1,
                    'call_type': 'frontend_to_backend',
                    'context_metadata': {
                        'raw_url': url,
                        'config_object': True
                    }
                }
        
        return None
    
    def _extract_angular_http_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Angular HttpClient call details."""
        function_text = self._get_node_text(function_node, code)
        parts = function_text.split('.')
        
        if len(parts) < 2:
            return None
        
        method_name = parts[-1]
        if method_name.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'request']:
            return None
        
        args = self._get_call_arguments(node, code)
        if not args or len(args) == 0:
            return None
        
        url = args[0]
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': method_name.upper(),
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'angular-http',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'raw_url': url
            }
        }
    
    def _extract_vue_http_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Vue $http call details."""
        function_text = self._get_node_text(function_node, code)
        parts = function_text.split('.')
        
        if len(parts) < 2:
            return None
        
        method_name = parts[-1]
        if method_name.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'head']:
            return None
        
        args = self._get_call_arguments(node, code)
        if not args or len(args) == 0:
            return None
        
        url = args[0]
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': method_name.upper(),
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'vue-http',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'raw_url': url
            }
        }
    
    def _extract_node_http_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Node.js http/https module call details."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args or len(args) == 0:
            return None
            
        # http.request(url, options) or http.request(options)
        # http.get(url, options)
        
        method = 'GET' if 'get' in function_text else 'POST' # Default to POST for request if not specified, but usually GET
        if 'request' in function_text:
            method = 'UNKNOWN' # Could be anything, determined by options
            
        url = args[0]
        # If first arg is not a string (likely options object), we might miss the URL if we don't parse the object
        # But often it's http.request('url', ...)
        
        url_pattern, is_dynamic = self._normalize_url(url)
        
        # Check options for method if available
        if len(args) > 1:
            options_text = args[1]
            method_match = re.search(r'method\s*:\s*["\'](\w+)["\']', options_text)
            if method_match:
                method = method_match.group(1).upper()
        
        return {
            'http_method': method,
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'node-http',
            'line_number': node.start_point[0] + 1,
            'call_type': 'backend_to_backend',
            'context_metadata': {
                'raw_url': url,
                'module': function_text.split('.')[0]
            }
        }

    def _extract_got_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract got library call details."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args or len(args) == 0:
            return None
            
        url = args[0]
        method = 'GET'
        
        # got.post(url), got.delete(url)
        if '.' in function_text:
            parts = function_text.split('.')
            if len(parts) > 1:
                method_candidate = parts[1].upper()
                if method_candidate in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']:
                    method = method_candidate
        
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': method,
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'got',
            'line_number': node.start_point[0] + 1,
            'call_type': 'backend_to_backend',
            'context_metadata': {
                'raw_url': url
            }
        }

    def _extract_superagent_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract superagent call details."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args or len(args) == 0:
            return None
            
        url = args[0]
        method = 'GET'
        
        # superagent.post(url)
        if '.' in function_text:
            parts = function_text.split('.')
            if len(parts) > 1:
                method_candidate = parts[1].upper()
                if method_candidate in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD']:
                    method = method_candidate
        
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': method,
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'superagent',
            'line_number': node.start_point[0] + 1,
            'call_type': 'backend_to_backend',
            'context_metadata': {
                'raw_url': url
            }
        }

    def _extract_react_query_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract React Query / TanStack Query calls."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args:
            return None
            
        # useQuery(['key'], () => fetch(...)) or useQuery({ queryKey: [...], queryFn: ... })
        # We are interested if we can find the URL in the queryFn.
        # But often the URL is not directly visible here if it's a wrapper.
        # However, we can at least record the "intent" to fetch data.
        
        # For now, we'll extract the query key as a proxy for the "resource" being accessed
        query_key = "unknown"
        if len(args) > 0:
            first_arg = args[0]
            if first_arg.startswith('[') or first_arg.startswith('{'):
                 query_key = first_arg
            else:
                # If first arg is NOT an array or object, it might be Apollo (which takes a Document node/variable)
                # React Query v3/v4 usually takes array key first.
                # If it's a string, it could be React Query v3 (string key) OR Apollo (variable name).
                # But Apollo usually takes a variable that is UPPERCASE (convention for gql docs).
                if first_arg[0].isupper():
                    return None # Likely Apollo
        
        return {
            'http_method': 'GET' if 'Query' in function_text else 'POST', # Mutation usually implies state change
            'url_pattern': f"react-query:{query_key}", # Virtual URL pattern
            'is_dynamic_url': True,
            'http_client_library': 'react-query',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'query_key': query_key,
                'function': function_text
            }
        }

    def _extract_swr_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract SWR useSWR calls."""
        args = self._get_call_arguments(node, code)
        
        if not args:
            return None
            
        # useSWR('/api/user', fetcher)
        url = args[0]
        url_pattern, is_dynamic = self._normalize_url(url)
        
        return {
            'http_method': 'GET',
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'swr',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'raw_url': url
            }
        }

    def _extract_apollo_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Apollo Client useQuery/useMutation calls."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args:
            return None
            
        # useQuery(GET_DOGS)
        # We want to find the operation name if possible.
        # The first arg is usually the query document.
        query_doc = args[0]
        
        return {
            'http_method': 'POST', # GraphQL is usually POST
            'url_pattern': f"graphql:{query_doc}",
            'is_dynamic_url': False,
            'http_client_library': 'apollo-client',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'operation': query_doc,
                'function': function_text
            }
        }

    def _extract_nuxt_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Nuxt 3 useFetch/$fetch calls."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args:
            return None
            
        # useFetch('/api/users')
        url = args[0]
        url_pattern, is_dynamic = self._normalize_url(url)
        
        method = 'GET'
        if len(args) > 1:
            options_text = args[1]
            method_match = re.search(r'method\s*:\s*["\'](\w+)["\']', options_text)
            if method_match:
                method = method_match.group(1).upper()
        
        return {
            'http_method': method,
            'url_pattern': url_pattern,
            'is_dynamic_url': is_dynamic,
            'http_client_library': 'nuxt',
            'line_number': node.start_point[0] + 1,
            'call_type': 'frontend_to_backend',
            'context_metadata': {
                'raw_url': url,
                'function': function_text
            }
        }

    def _extract_nextjs_data_fetching(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Next.js data fetching functions."""
        # ... (omitted for brevity, no changes needed here as it returns None anyway)
        return None

    def _extract_rtk_query_call(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract Redux Toolkit Query calls."""
        function_text = self._get_node_text(function_node, code)
        args = self._get_call_arguments(node, code)
        
        if not args:
            return None
            
        if function_text == 'createApi':
            # createApi({ baseQuery: fetchBaseQuery({ baseUrl: '/api' }), endpoints: ... })
            # We want to extract the baseUrl.
            # This is complex to parse from the args string without full object parsing.
            # But we can try regex on the args text.
            args_text = self._get_node_text(node, code)
            base_url_match = re.search(r'baseUrl\s*:\s*["\']([^"\']+)["\']', args_text)
            base_url = base_url_match.group(1) if base_url_match else "unknown"
            
            return {
                'http_method': 'CONFIG',
                'url_pattern': base_url,
                'is_dynamic_url': False,
                'http_client_library': 'rtk-query',
                'line_number': node.start_point[0] + 1,
                'call_type': 'frontend_to_backend',
                'context_metadata': {
                    'base_url': base_url
                }
            }
        elif function_text == 'fetchBaseQuery':
            # fetchBaseQuery({ baseUrl: '/api' })
            args_text = self._get_node_text(node, code)
            base_url_match = re.search(r'baseUrl\s*:\s*["\']([^"\']+)["\']', args_text)
            base_url = base_url_match.group(1) if base_url_match else "unknown"
             
            return {
                'http_method': 'CONFIG',
                'url_pattern': base_url,
                'is_dynamic_url': False,
                'http_client_library': 'rtk-query',
                'line_number': node.start_point[0] + 1,
                'call_type': 'frontend_to_backend',
                'context_metadata': {
                    'base_url': base_url
                }
            }
            
        return None
    
    def _get_call_arguments(self, call_node: tree_sitter.Node, code: str) -> List[str]:
        """Extract arguments from a call_expression node."""
        arguments = []
        
        # Find the arguments node
        for child in call_node.children:
            if child.type == 'arguments':
                for arg_child in child.children:
                    if arg_child.type not in ['(', ')', ',']:
                        arg_text = self._get_node_text(arg_child, code)
                        arguments.append(arg_text)
                break
        
        return arguments
    
    def _normalize_url(self, url_text: str) -> tuple[str, bool]:
        """
        Normalize URL pattern and determine if it's dynamic.
        
        Returns:
            Tuple of (normalized_url, is_dynamic)
        """
        # Remove quotes
        url_clean = url_text.strip().strip('"\'`')
        
        # Check for template literals or string concatenation
        is_dynamic = False
        
        # Template literal: `${baseUrl}/users/${id}`
        if '${' in url_clean or '`' in url_text:
            is_dynamic = True
            # Replace variables with placeholders
            url_clean = re.sub(r'\$\{[^}]+\}', '{var}', url_clean)
        
        # String concatenation: baseUrl + "/users"
        elif '+' in url_text:
            is_dynamic = True
            # Try to extract the static part
            parts = url_text.split('+')
            static_parts = [p.strip().strip('"\'') for p in parts if '"' in p or "'" in p]
            url_clean = ''.join(static_parts) or '{dynamic_url}'
        
        # Variable reference
        elif not url_clean.startswith('/') and not url_clean.startswith('http'):
            is_dynamic = True
            url_clean = '{variable_url}'
        
        return url_clean, is_dynamic
    
    def _extract_imports(self, node: tree_sitter.Node, code: str) -> List[str]:
        """Extract import statements."""
        imports = []
        
        def traverse(n: tree_sitter.Node):
            if n.type == 'import_statement':
                # Extract module path
                for child in n.children:
                    if child.type == 'string':
                        import_path = self._get_node_text(child, code).strip('\'"')
                        imports.append(import_path)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return imports
    
    def _extract_event(self, node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """
        Extract event publishing/subscription from a call_expression node.
        
        Detects patterns:
        - channel.publish(exchange, routingKey, content) (amqplib)
        - channel.sendToQueue(queue, content) (amqplib)
        - channel.consume(queue, callback) (amqplib)
        """
        if node.type != 'call_expression':
            return None
        
        function_node = node.children[0] if node.children else None
        if not function_node:
            return None
        
        function_text = self._get_node_text(function_node, code)
        
        # amqplib patterns
        if 'channel.' in function_text or function_text.startswith('ch.'):
            if '.publish' in function_text:
                return self._extract_amqp_publish(node, function_node, code)
            elif '.sendToQueue' in function_text:
                return self._extract_amqp_send_to_queue(node, function_node, code)
            elif '.consume' in function_text:
                return self._extract_amqp_consume(node, function_node, code)
                
        return None

    def _extract_amqp_publish(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract amqplib publish call."""
        args = self._get_call_arguments(node, code)
        if not args or len(args) < 2:
            return None
            
        # channel.publish(exchange, routingKey, content, [options])
        exchange = args[0].strip('\'"`')
        routing_key = args[1].strip('\'"`')
        
        return {
            'type': 'publish',
            'event_type_name': routing_key if routing_key else 'unknown',
            'messaging_library': 'amqplib',
            'topic_name': exchange,
            'routing_key': routing_key,
            'line_number': node.start_point[0] + 1,
            'event_metadata': {
                'exchange': exchange,
                'routing_key': routing_key
            }
        }

    def _extract_amqp_send_to_queue(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract amqplib sendToQueue call."""
        args = self._get_call_arguments(node, code)
        if not args or len(args) < 1:
            return None
            
        # channel.sendToQueue(queue, content, [options])
        queue = args[0].strip('\'"`')
        
        return {
            'type': 'publish',
            'event_type_name': 'UnknownEvent', # Direct queue send doesn't imply event type name usually
            'messaging_library': 'amqplib',
            'topic_name': queue, # Using topic_name to store queue for now, or we can add queue_name to PublishedEvent
            'line_number': node.start_point[0] + 1,
            'event_metadata': {
                'queue': queue
            }
        }

    def _extract_amqp_consume(self, node: tree_sitter.Node, function_node: tree_sitter.Node, code: str) -> Optional[Dict[str, Any]]:
        """Extract amqplib consume call."""
        args = self._get_call_arguments(node, code)
        if not args or len(args) < 1:
            return None
            
        # channel.consume(queue, callback, [options])
        queue = args[0].strip('\'"`')
        
        return {
            'type': 'subscribe',
            'event_type_name': 'UnknownEvent',
            'messaging_library': 'amqplib',
            'queue_name': queue,
            'line_number': node.start_point[0] + 1,
            'event_metadata': {
                'queue': queue
            }
        }


class TypeScriptParser(JavaScriptParser):
    """TypeScript language parser (extends JavaScript parser)."""
    
    def __init__(self, use_tsx: bool = False):
        """
        Initialize TypeScript parser.
        
        Args:
            use_tsx: If True, use TSX grammar for JSX support. If False, use regular TypeScript grammar.
        """
        self.use_tsx = use_tsx
        
        # Create dynamic language module
        class DynamicTypeScriptModule:
            @staticmethod
            def language():
                if use_tsx:
                    return tree_sitter_typescript.language_tsx()
                else:
                    return tree_sitter_typescript.language_typescript()
        
        TreeSitterParser.__init__(self, LanguageEnum.TYPESCRIPT, DynamicTypeScriptModule)
        self.react_analyzer = ReactAnalyzer()
        self.backend_analyzer = BackendAnalyzer()
        self.api_calls = []  # Store detected API calls for Phase 2
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a TypeScript file."""
        return file_path.suffix.lower() in ['.ts', '.tsx']
    
    def _extract_symbols(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        """Extract TypeScript symbols including interfaces."""
        # Use JavaScript extraction as base
        symbols = super()._extract_symbols(node, code)
        
        # Add TypeScript-specific symbols
        def traverse(n: tree_sitter.Node, parent_name: Optional[str] = None):
            # Interface declarations
            if n.type == 'interface_declaration':
                symbols.append(self._parse_interface(n, code, parent_name))
            
            # Type aliases
            elif n.type == 'type_alias_declaration':
                symbols.append(self._parse_type_alias(n, code, parent_name))
            
            # Enum declarations
            elif n.type == 'enum_declaration':
                symbols.append(self._parse_enum(n, code, parent_name))
            
            for child in n.children:
                traverse(child, parent_name)
        
        traverse(node)
        return symbols
    
    def _parse_interface(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse an interface declaration."""
        name_node = self._find_child_by_type(node, 'type_identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownInterface"
        
        node_text = self._get_node_text(node, code)
        signature = node_text.split('{')[0].strip() if '{' in node_text else node_text[:200]
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        return ParsedSymbol(
            kind=SymbolKindEnum.INTERFACE,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=signature,
            documentation=plain_doc,
            structured_docs=jsdoc,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _parse_type_alias(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse a type alias declaration."""
        name_node = self._find_child_by_type(node, 'type_identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownType"
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        return ParsedSymbol(
            kind=SymbolKindEnum.TYPE_ALIAS,  # Proper symbol kind for type aliases
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=self._get_node_text(node, code)[:200],
            documentation=plain_doc,
            structured_docs=jsdoc,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )
    
    def _parse_enum(self, node: tree_sitter.Node, code: str, parent_name: Optional[str]) -> ParsedSymbol:
        """Parse an enum declaration."""
        name_node = self._find_child_by_type(node, 'identifier')
        name = self._get_node_text(name_node, code) if name_node else "UnknownEnum"
        
        node_text = self._get_node_text(node, code)
        signature = node_text.split('{')[0].strip() if '{' in node_text else node_text[:200]
        
        # Extract JSDoc documentation
        jsdoc = self._find_jsdoc(node, code)
        plain_doc = self._find_documentation(node, code)
        
        return ParsedSymbol(
            kind=SymbolKindEnum.ENUM,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            signature=signature,
            documentation=plain_doc,
            structured_docs=jsdoc,
            parent_name=parent_name,
            fully_qualified_name=f"{parent_name}.{name}" if parent_name else name
        )

