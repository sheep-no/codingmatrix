"""Rust language adapter for use declarations, modules, and symbols."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from .generic import GenericLanguageAdapter
from .language_adapter import ImportInfo, LanguageAdapterRegistry, SymbolDefinition


class RustLanguageAdapter(GenericLanguageAdapter):
    language = "rust"
    extensions = [".rs"]
    package_init_filename = "lib.rs"
    supports_cross_file_symbol_validation = False

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        imports: List[ImportInfo] = []
        for line in content.splitlines():
            use_match = re.match(r"\s*(?:pub\s+)?use\s+([^;]+);", line)
            if use_match:
                module = use_match.group(1).strip()
                imports.append(ImportInfo(
                    module=module,
                    is_relative=module.startswith(("crate::", "self::", "super::")),
                    raw_line=line.strip(),
                ))
                continue
            module_match = re.match(r"\s*(?:pub\s+)?mod\s+(\w+)\s*;", line)
            if module_match:
                imports.append(ImportInfo(
                    module=module_match.group(1), is_relative=True, raw_line=line.strip()
                ))
        return imports

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        module = import_info.module.split("::{", 1)[0].rstrip(":")
        if not import_info.is_relative and not module.startswith("crate::"):
            return []
        current_dir = Path(current_file).parent
        if module.startswith("crate::"):
            parts = module.removeprefix("crate::").split("::")
            base = Path("src")
        elif module.startswith("super::"):
            parts = module.removeprefix("super::").split("::")
            base = current_dir.parent
        elif module.startswith("self::"):
            parts = module.removeprefix("self::").split("::")
            base = current_dir
        else:
            parts = module.split("::")
            base = current_dir
        if len(parts) > 1 and parts[-1][:1].isupper():
            parts = parts[:-1]
        target = base.joinpath(*parts)
        return [target.with_suffix(".rs").as_posix(), (target / "mod.rs").as_posix()]

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        definitions: Dict[str, SymbolDefinition] = {}
        patterns = (
            (r"\b(?:pub\s+)?(struct|enum|trait)\s+(\w+)", None),
            (r"\b(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(([^)]*)\)", "function"),
        )
        for line_number, line in enumerate(content.splitlines(), 1):
            for pattern, fixed_type in patterns:
                match = re.search(pattern, line)
                if not match:
                    continue
                if fixed_type:
                    name, symbol_type = match.group(1), fixed_type
                else:
                    symbol_type, name = match.group(1), match.group(2)
                definitions[name] = SymbolDefinition(
                    name, symbol_type, line_number, signature=line.strip(),
                    is_exported=bool(re.search(r"\bpub\b", line)),
                )
                break
        return definitions

    def get_package_init_file(self, package_path: str) -> str:
        return f"{package_path.rstrip('/')}/mod.rs"

    def is_project_module(self, module_name: str) -> bool:
        return module_name.startswith(("crate::", "self::", "super::"))


LanguageAdapterRegistry.register(RustLanguageAdapter())
