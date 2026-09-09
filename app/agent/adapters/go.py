"""Go language adapter for imports, symbols, and package paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from .generic import GenericLanguageAdapter
from .language_adapter import ImportInfo, LanguageAdapterRegistry, SymbolDefinition


class GoLanguageAdapter(GenericLanguageAdapter):
    language = "go"
    extensions = [".go"]
    package_init_filename = ""
    supports_cross_file_symbol_validation = False

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        imports: List[ImportInfo] = []
        blocks = re.findall(r"\bimport\s*\((.*?)\)", content, flags=re.DOTALL)
        candidates = list(blocks)
        candidates.extend(re.findall(r"\bimport\s+([^\n]+)", content))
        for candidate in candidates:
            for match in re.finditer(r'(?:^|\s)(?:([\w.]+)\s+)?"([^"]+)"', candidate):
                alias, module = match.groups()
                imports.append(ImportInfo(
                    module=module,
                    alias=alias,
                    raw_line=match.group(0).strip(),
                ))
        return imports

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        module = import_info.module.strip("/")
        if not self.is_project_module(module):
            return []
        parts = list(Path(module).parts)
        marker_index = next(
            index for index, part in enumerate(parts) if part in {"cmd", "internal", "pkg"}
        )
        local_module = "/".join(parts[marker_index:])
        package = parts[-1]
        return [f"{local_module}/{package}.go", f"{local_module}.go"]

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        definitions: Dict[str, SymbolDefinition] = {}
        for line_number, line in enumerate(content.splitlines(), 1):
            type_match = re.search(r"\btype\s+(\w+)\s+(struct|interface)\b", line)
            if type_match:
                name, symbol_type = type_match.groups()
                definitions[name] = SymbolDefinition(
                    name, symbol_type, line_number, is_exported=name[:1].isupper()
                )
                continue
            function_match = re.search(r"\bfunc\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)\)", line)
            if function_match:
                name = function_match.group(1)
                definitions[name] = SymbolDefinition(
                    name, "function", line_number,
                    signature=line.strip().removesuffix("{" ).strip(),
                    is_exported=name[:1].isupper(),
                )
        return definitions

    def get_package_init_file(self, package_path: str) -> str:
        return ""

    def is_project_module(self, module_name: str) -> bool:
        if not module_name:
            return False
        parts = Path(module_name).parts
        return any(part in {"cmd", "internal", "pkg"} for part in parts)


LanguageAdapterRegistry.register(GoLanguageAdapter())
