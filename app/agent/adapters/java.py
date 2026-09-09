"""Java language adapter for imports, symbols, and project file resolution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from .generic import GenericLanguageAdapter
from .language_adapter import ImportInfo, LanguageAdapterRegistry, SymbolDefinition


class JavaLanguageAdapter(GenericLanguageAdapter):
    language = "java"
    extensions = [".java"]
    package_init_filename = ""
    supports_cross_file_symbol_validation = False
    external_package_prefixes = (
        "java.",
        "javax.",
        "jakarta.",
        "org.springframework.",
        "org.junit.",
        "org.mockito.",
        "org.hibernate.",
        "org.slf4j.",
        "org.sqlite.",
        "com.fasterxml.",
    )

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        imports: List[ImportInfo] = []
        for line in content.splitlines():
            match = re.match(r"\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;", line)
            if match:
                module = match.group(1)
                imports.append(ImportInfo(
                    module=module,
                    symbols=[] if module.endswith(".*") else [module.rsplit(".", 1)[-1]],
                    raw_line=line.strip(),
                ))
        return imports

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        module = import_info.module.removesuffix(".*")
        if not module or module.startswith(self.external_package_prefixes):
            return []
        relative_path = module.replace(".", "/") + ".java"
        return [f"src/main/java/{relative_path}", f"src/test/java/{relative_path}", relative_path]

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        definitions: Dict[str, SymbolDefinition] = {}
        patterns = (
            (r"\b(class|interface|enum|record)\s+(\w+)", "class"),
            (r"\b(?:public|protected|private)?\s*(?:static\s+)?[\w<>?, \[\]]+\s+(\w+)\s*\([^;{}]*\)\s*\{", "function"),
        )
        for line_number, line in enumerate(content.splitlines(), 1):
            for pattern, symbol_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(2) if symbol_type == "class" else match.group(1)
                    definitions[name] = SymbolDefinition(name, symbol_type, line_number)
                    break
        return definitions

    def is_project_module(self, module_name: str) -> bool:
        return bool(module_name) and not module_name.startswith(self.external_package_prefixes)


LanguageAdapterRegistry.register(JavaLanguageAdapter())
