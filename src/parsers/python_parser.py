import ast
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.config.enums import LanguageEnum, SymbolKindEnum, AccessModifierEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class PythonParser(BaseParser):
    """Python language parser using builtin AST module."""

    def __init__(self):
        self.language = LanguageEnum.PYTHON

    def get_language(self) -> LanguageEnum:
        return self.language

    def is_supported(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.py'

    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        start_time = time.time()

        symbols: List[ParsedSymbol] = []
        imports: List[str] = []
        exports: List[str] = []
        errors: List[str] = []

        try:
            tree = ast.parse(code)
            visitor = _PythonAstVisitor(code)
            visitor.visit(tree)
            symbols = visitor.symbols
            imports = visitor.imports
            exports = visitor.exports
        except SyntaxError as e:
            errors.append(f"Python syntax error: {str(e)}")
        except Exception as e:
            errors.append(f"Python parsing error: {str(e)}")

        duration_ms = (time.time() - start_time) * 1000

        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=imports,
            exports=exports,
            parse_errors=errors,
            parse_duration_ms=duration_ms,
        )


class _PythonAstVisitor(ast.NodeVisitor):
    def __init__(self, code: str):
        self.code = code
        self.lines = code.splitlines()
        self.symbols: List[ParsedSymbol] = []
        self.imports: List[str] = []
        self.exports: List[str] = []
        self.class_stack: List[str] = []
        self.function_depth = 0

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = ('.' * node.level) + (node.module or '')
        if module:
            self.imports.append(module)
        for alias in node.names:
            if module:
                self.imports.append(f"{module}.{alias.name}")
            else:
                self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        parent_name = self.class_stack[-1] if self.class_stack else None
        class_name = node.name
        fully_qualified_name = '.'.join(self.class_stack + [class_name]) if self.class_stack else class_name

        bases = [self._safe_unparse(base) for base in node.bases]
        signature = f"class {class_name}"
        if bases:
            signature += f"({', '.join(bases)})"

        self.symbols.append(
            ParsedSymbol(
                kind=SymbolKindEnum.CLASS,
                name=class_name,
                start_line=node.lineno,
                end_line=getattr(node, 'end_lineno', node.lineno),
                start_column=getattr(node, 'col_offset', 0),
                end_column=self._end_column(node),
                signature=signature,
                documentation=ast.get_docstring(node),
                access_modifier=self._access_modifier_for_name(class_name),
                parent_name=parent_name,
                fully_qualified_name=fully_qualified_name,
            )
        )

        self.class_stack.append(class_name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_function(node, is_async=False)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_function(node, is_async=True)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def visit_Assign(self, node: ast.Assign):
        # Export extraction via __all__ = [...]
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == '__all__':
                extracted = self._extract_all_exports(node.value)
                if extracted:
                    self.exports.extend(extracted)

        # Module-level constants/variables
        if not self.class_stack and self._is_module_level(node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._record_module_symbol(target.id, node)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        # Handle module-level annotated assignments (e.g., FOO: int = 1)
        if self._is_module_level(node) and isinstance(node.target, ast.Name):
            self._record_module_symbol(node.target.id, node)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        # Export extraction via __all__ += [...]
        if isinstance(node.target, ast.Name) and node.target.id == '__all__':
            extracted = self._extract_all_exports(node.value)
            if extracted:
                self.exports.extend(extracted)

        self.generic_visit(node)

    def _record_function(self, node: ast.AST, is_async: bool):
        parent_name = self.class_stack[-1] if self.class_stack else None
        func_name = node.name  # type: ignore[attr-defined]
        fully_qualified_name = '.'.join(self.class_stack + [func_name]) if self.class_stack else func_name

        args = self._extract_parameters(node)
        return_type = self._safe_unparse(getattr(node, 'returns', None))

        prefix = 'async def' if is_async else 'def'
        signature = f"{prefix} {func_name}({', '.join(p['name'] for p in args)})"
        if return_type:
            signature += f" -> {return_type}"

        self.symbols.append(
            ParsedSymbol(
                kind=SymbolKindEnum.METHOD if self.class_stack else SymbolKindEnum.FUNCTION,
                name=func_name,
                start_line=node.lineno,  # type: ignore[attr-defined]
                end_line=getattr(node, 'end_lineno', node.lineno),  # type: ignore[attr-defined]
                start_column=getattr(node, 'col_offset', 0),
                end_column=self._end_column(node),
                signature=signature,
                documentation=ast.get_docstring(node),
                parameters=args,
                return_type=return_type,
                access_modifier=self._access_modifier_for_name(func_name),
                parent_name=parent_name,
                fully_qualified_name=fully_qualified_name,
            )
        )

    def _record_module_symbol(self, var_name: str, node: ast.AST):
        self.symbols.append(
            ParsedSymbol(
                kind=SymbolKindEnum.CONSTANT if var_name.isupper() else SymbolKindEnum.VARIABLE,
                name=var_name,
                start_line=getattr(node, 'lineno', 1),
                end_line=getattr(node, 'end_lineno', getattr(node, 'lineno', 1)),
                start_column=getattr(node, 'col_offset', 0),
                end_column=self._end_column(node),
                signature=f"{var_name} = ...",
                documentation=None,
                access_modifier=self._access_modifier_for_name(var_name),
                fully_qualified_name=var_name,
            )
        )

    def _extract_parameters(self, node: ast.AST) -> List[Dict[str, Any]]:
        params: List[Dict[str, Any]] = []
        args_obj = getattr(node, 'args', None)
        if not args_obj:
            return params

        arg_nodes = list(args_obj.posonlyargs) + list(args_obj.args) + list(args_obj.kwonlyargs)
        for arg in arg_nodes:
            params.append(
                {
                    'name': arg.arg,
                    'type': self._safe_unparse(arg.annotation) if arg.annotation else None,
                }
            )

        if args_obj.vararg:
            params.append({'name': f"*{args_obj.vararg.arg}", 'type': self._safe_unparse(args_obj.vararg.annotation) if args_obj.vararg.annotation else None})
        if args_obj.kwarg:
            params.append({'name': f"**{args_obj.kwarg.arg}", 'type': self._safe_unparse(args_obj.kwarg.annotation) if args_obj.kwarg.annotation else None})

        return params

    def _extract_all_exports(self, value: ast.AST) -> List[str]:
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            exports = []
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    exports.append(elt.value)
            return exports
        return []

    def _safe_unparse(self, node: Optional[ast.AST]) -> Optional[str]:
        if node is None:
            return None
        try:
            return ast.unparse(node)
        except Exception:
            return None

    def _access_modifier_for_name(self, name: str) -> AccessModifierEnum:
        return AccessModifierEnum.PRIVATE if name.startswith('_') else AccessModifierEnum.PUBLIC

    def _end_column(self, node: ast.AST) -> int:
        end_col = getattr(node, 'end_col_offset', None)
        if isinstance(end_col, int):
            return end_col

        lineno = getattr(node, 'lineno', 1)
        if 1 <= lineno <= len(self.lines):
            return len(self.lines[lineno - 1])
        return 0

    def _is_module_level(self, node: ast.AST) -> bool:
        # Module-level symbols are represented by top-level body nodes.
        # Class stack is enough for our use case because we only track class nesting.
        return not self.class_stack and self.function_depth == 0
