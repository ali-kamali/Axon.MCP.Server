"""React component analyzer for enhanced component analysis."""

import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class ReactHook:
    """Represents a React hook usage."""
    name: str
    line_number: int
    arguments: List[str]
    is_custom: bool


@dataclass
class ReactComponent:
    """Represents a React component with metadata."""
    name: str
    component_type: str  # 'functional', 'class', 'memo', 'forwardRef'
    props: List[Dict[str, str]]
    hooks: List[ReactHook]
    imports: List[str]
    exports: List[str]
    is_hoc: bool  # Higher-Order Component
    wrapped_component: Optional[str]


class ReactAnalyzer:
    """Analyzes React components for enhanced understanding."""
    
    # Standard React hooks
    STANDARD_HOOKS = {
        'useState', 'useEffect', 'useContext', 'useReducer', 'useCallback',
        'useMemo', 'useRef', 'useImperativeHandle', 'useLayoutEffect',
        'useDebugValue', 'useDeferredValue', 'useTransition', 'useId',
        'useSyncExternalStore', 'useInsertionEffect'
    }
    
    # Common HOC patterns
    HOC_PATTERNS = [
        'with', 'enhance', 'wrap', 'connect', 'memo', 'forwardRef'
    ]
    
    def analyze_component_from_symbol(
        self,
        symbol_data: Dict[str, Any],
        file_content: str
    ) -> Optional[ReactComponent]:
        """
        Analyze a symbol to determine if it's a React component.
        
        Args:
            symbol_data: Parsed symbol data
            file_content: Full file content
            
        Returns:
            ReactComponent if it's a React component, None otherwise
        """
        name = symbol_data.get('name', '')
        signature = symbol_data.get('signature', '')
        
        # Check if it's a component (starts with uppercase or has JSX)
        if not name or not name[0].isupper():
            return None
        
        # Detect component type
        component_type = self._detect_component_type(signature, file_content)
        
        if not component_type:
            return None
        
        # Extract props
        props = self._extract_props(symbol_data, signature)
        
        # Extract hooks if functional component
        hooks = []
        if component_type in ['functional', 'memo', 'forwardRef']:
            hooks = self._extract_hooks(file_content, symbol_data.get('start_line', 0))
        
        # Check if HOC
        is_hoc = self._is_higher_order_component(name, signature, file_content)
        
        # Extract wrapped component if HOC
        wrapped = self._extract_wrapped_component(file_content) if is_hoc else None
        
        return ReactComponent(
            name=name,
            component_type=component_type,
            props=props,
            hooks=hooks,
            imports=[],  # Would be populated from parse result
            exports=[],
            is_hoc=is_hoc,
            wrapped_component=wrapped
        )
    
    def _detect_component_type(self, signature: str, content: str) -> Optional[str]:
        """Detect the type of React component."""
        sig_lower = signature.lower()
        
        # Check for React.memo
        if 'react.memo' in sig_lower or 'memo(' in sig_lower:
            return 'memo'
        
        # Check for React.forwardRef
        if 'react.forwardref' in sig_lower or 'forwardref(' in sig_lower:
            return 'forwardRef'
        
        # Check for class component
        if 'class' in sig_lower and ('component' in sig_lower or 'purecomponent' in sig_lower):
            return 'class'
        
        # Check for functional component (arrow or function with JSX return)
        if ('function' in sig_lower or '=>' in signature) and self._has_jsx_return(content):
            return 'functional'
        
        return None
    
    def _has_jsx_return(self, content: str) -> bool:
        """Check if content has JSX return statement."""
        # Look for return statements with JSX
        jsx_patterns = [
            r'return\s*\(',  # return (
            r'return\s*<',   # return <
            r'=>\s*\(',      # => (
            r'=>\s*<',       # => <
        ]
        
        for pattern in jsx_patterns:
            if re.search(pattern, content):
                return True
        
        return False
    
    def _extract_props(
        self,
        symbol_data: Dict[str, Any],
        signature: str
    ) -> List[Dict[str, str]]:
        """Extract component props from parameters."""
        props = []
        params = symbol_data.get('parameters', [])
        
        # For functional components, first param is props
        if params:
            first_param = params[0]
            if isinstance(first_param, dict):
                # If props are destructured, parse them
                prop_name = first_param.get('name', '')
                if '{' in prop_name:  # Destructured props
                    props = self._parse_destructured_props(prop_name)
                else:
                    # Props as single object
                    props = [{
                        'name': prop_name,
                        'type': first_param.get('type', 'any'),
                        'required': True
                    }]
        
        return props
    
    def _parse_destructured_props(self, destructured: str) -> List[Dict[str, str]]:
        """Parse destructured props like { name, age, email }."""
        props = []
        
        # Remove braces and split by comma
        clean = destructured.strip('{}').strip()
        if not clean:
            return props
        
        parts = [p.strip() for p in clean.split(',')]
        
        for part in parts:
            # Handle default values: name = 'default'
            if '=' in part:
                prop_name = part.split('=')[0].strip()
                default = part.split('=')[1].strip()
                props.append({
                    'name': prop_name,
                    'type': 'unknown',
                    'required': False,
                    'default': default
                })
            else:
                props.append({
                    'name': part,
                    'type': 'unknown',
                    'required': True
                })
        
        return props
    
    def _extract_hooks(self, content: str, start_line: int) -> List[ReactHook]:
        """Extract React hooks from component body."""
        hooks = []
        lines = content.split('\n')
        
        # Look for hook calls (use* functions)
        hook_pattern = r'\b(use[A-Z]\w*)\s*\('
        
        for i, line in enumerate(lines[start_line:], start=start_line):
            matches = re.finditer(hook_pattern, line)
            for match in matches:
                hook_name = match.group(1)
                
                # Extract arguments (simplified)
                args = self._extract_hook_arguments(line, match.end())
                
                hooks.append(ReactHook(
                    name=hook_name,
                    line_number=i + 1,
                    arguments=args,
                    is_custom=hook_name not in self.STANDARD_HOOKS
                ))
        
        return hooks
    
    def _extract_hook_arguments(self, line: str, start_pos: int) -> List[str]:
        """Extract hook arguments (simplified version)."""
        # Find the closing parenthesis
        remaining = line[start_pos:]
        
        # Simple extraction - just get first few tokens
        args_match = re.match(r'([^)]+)', remaining)
        if args_match:
            args_str = args_match.group(1)
            return [a.strip() for a in args_str.split(',')][:3]  # Limit to 3 args
        
        return []
    
    def _is_higher_order_component(
        self,
        name: str,
        signature: str,
        content: str
    ) -> bool:
        """Determine if this is a Higher-Order Component."""
        # Check naming patterns
        name_lower = name.lower()
        for pattern in self.HOC_PATTERNS:
            if name_lower.startswith(pattern):
                return True
        
        # Check if it returns a component
        if 'return' in content and '=> {' in content:
            return True
        
        # Check if it wraps a component
        if re.search(r'<\w+\s+{\.\.\.props}', content):
            return True
        
        return False
    
    def _extract_wrapped_component(self, content: str) -> Optional[str]:
        """Extract the wrapped component name from HOC."""
        # Look for component being wrapped
        match = re.search(r'<(\w+)\s+{\.\.\.props}', content)
        if match:
            return match.group(1)
        
        return None


class VueAnalyzer:
    """Analyzes Vue components for enhanced understanding."""
    
    def analyze_vue_component(
        self,
        symbol_data: Dict[str, Any],
        template_content: str,
        script_content: str
    ) -> Dict[str, Any]:
        """
        Analyze a Vue component.
        
        Args:
            symbol_data: Parsed symbol data
            template_content: Template section content
            script_content: Script section content
            
        Returns:
            Dict with Vue component metadata
        """
        return {
            'name': symbol_data.get('name', 'UnknownComponent'),
            'props': self._extract_vue_props(script_content),
            'emits': self._extract_vue_emits(script_content),
            'composables': self._extract_composables(script_content),
            'template_components': self._extract_template_components(template_content),
            'is_composition_api': self._is_composition_api(script_content)
        }
    
    def _extract_vue_props(self, script: str) -> List[Dict[str, Any]]:
        """Extract Vue props definition."""
        props = []
        
        # Look for props definition
        props_match = re.search(r'props:\s*{([^}]+)}', script, re.DOTALL)
        if props_match:
            props_content = props_match.group(1)
            # Parse prop definitions (simplified)
            prop_lines = props_content.split(',')
            for line in prop_lines:
                if ':' in line:
                    prop_name = line.split(':')[0].strip()
                    props.append({'name': prop_name, 'type': 'unknown'})
        
        return props
    
    def _extract_vue_emits(self, script: str) -> List[str]:
        """Extract emitted events."""
        emits = []
        
        # Look for $emit calls
        emit_matches = re.findall(r'\$emit\([\'"](\w+)[\'"]', script)
        emits.extend(emit_matches)
        
        # Look for emits definition (Vue 3)
        emits_def = re.search(r'emits:\s*\[([^\]]+)\]', script)
        if emits_def:
            emit_names = re.findall(r'[\'"](\w+)[\'"]', emits_def.group(1))
            emits.extend(emit_names)
        
        return list(set(emits))  # Remove duplicates
    
    def _extract_composables(self, script: str) -> List[str]:
        """Extract used composables (use* functions)."""
        # Look for composable usage
        composables = re.findall(r'\b(use[A-Z]\w*)\s*\(', script)
        return list(set(composables))
    
    def _extract_template_components(self, template: str) -> List[str]:
        """Extract components used in template."""
        # Find component tags
        components = re.findall(r'<([A-Z][a-zA-Z0-9-]*)', template)
        return list(set(components))
    
    def _is_composition_api(self, script: str) -> bool:
        """Check if using Composition API."""
        composition_indicators = ['setup()', 'ref(', 'reactive(', 'computed(']
        return any(indicator in script for indicator in composition_indicators)

