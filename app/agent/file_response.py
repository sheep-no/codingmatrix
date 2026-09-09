"""Normalize and classify model responses intended to represent one file."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class FileResponse:
    kind: str
    content: Optional[str] = None
    diagnostic: Optional[str] = None


_CODE_KEYS = ("content", "code", "file_content", "source", "body", "implementation")
_TOOL_KEYS = ("tool", "tool_calls", "function_call", "function", "action", "operation")


def parse_file_response(raw: Any, *, expected_path: str = "") -> FileResponse:
    """Return a normalized file response without executing model instructions."""
    if not isinstance(raw, str):
        return FileResponse("invalid", diagnostic="model response is not text")
    text = re.sub(r"<(?:think|thinking)>.*?</(?:think|thinking)>", "", raw,
                  flags=re.DOTALL | re.IGNORECASE).lstrip()
    if not text.strip():
        return FileResponse("invalid", diagnostic="model response is empty")

    candidate = text
    code_match = re.search(r"```(?:[\w+#.-]+)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_match:
        candidate = code_match.group(1).strip()

    stripped_candidate = candidate.strip()
    if stripped_candidate.startswith("{"):
        try:
            payload = json.loads(stripped_candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in _CODE_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    path = str(payload.get("path") or payload.get("file_path") or "")
                    if expected_path and path and path != expected_path:
                        return FileResponse("invalid", diagnostic=f"response path mismatch: {path}")
                    return FileResponse("structured", content=value.strip())
            if any(key in payload for key in _TOOL_KEYS):
                return FileResponse("tool_call", diagnostic="model returned tool-call JSON")
            return FileResponse("metadata", diagnostic="model returned JSON metadata instead of file content")

    if stripped_candidate.startswith("[") and stripped_candidate.endswith("]"):
        try:
            json.loads(stripped_candidate)
            return FileResponse("metadata", diagnostic="model returned a JSON array instead of file content")
        except json.JSONDecodeError:
            pass
    if not stripped_candidate:
        return FileResponse("invalid", diagnostic="normalized file content is empty")
    return FileResponse("code", content=candidate)


__all__ = ["FileResponse", "parse_file_response"]
