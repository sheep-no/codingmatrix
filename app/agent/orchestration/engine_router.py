"""Select legacy or core generation handlers with optional shadow comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from .routing import CORE_ENGINE, engine_metadata, select_engine


Handler = Callable[[], Any | Awaitable[Any]]


@dataclass(frozen=True)
class EngineRouteResult:
    engine: str
    result: Any
    shadow: Optional[Dict[str, Any]] = None


def _file_paths(result: Any) -> set[str]:
    if not isinstance(result, dict):
        return set()
    files = result.get("generated_files", result.get("files", []))
    if isinstance(files, dict):
        return {str(path) for path in files}
    if isinstance(files, list):
        return {str(item.get("path")) for item in files if isinstance(item, dict) and item.get("path")}
    return set()


def compare_shadow_results(primary: Any, shadow: Any) -> Dict[str, Any]:
    """Compare stable result facts without retaining generated source content."""
    primary_paths = _file_paths(primary)
    shadow_paths = _file_paths(shadow)
    primary_success = primary.get("success") if isinstance(primary, dict) else None
    shadow_success = shadow.get("success") if isinstance(shadow, dict) else None
    return {
        "matches": primary_paths == shadow_paths and primary_success == shadow_success,
        "primary_success": primary_success,
        "shadow_success": shadow_success,
        "primary_file_count": len(primary_paths),
        "shadow_file_count": len(shadow_paths),
        "missing_from_primary": sorted(shadow_paths - primary_paths),
        "missing_from_shadow": sorted(primary_paths - shadow_paths),
    }


async def route_generation(
    legacy_handler: Handler,
    core_handler: Optional[Handler] = None,
    *,
    requested_engine: Optional[str] = None,
    shadow: bool = False,
) -> EngineRouteResult:
    """Run the selected handler and optionally run the other engine in shadow."""
    engine = select_engine(requested_engine)
    selected = core_handler if engine == CORE_ENGINE and core_handler else legacy_handler
    result = selected()
    if hasattr(result, "__await__"):
        result = await result

    shadow_result = None
    if shadow and core_handler is not None:
        comparison_handler = legacy_handler if engine == CORE_ENGINE else core_handler
        comparison = comparison_handler()
        if hasattr(comparison, "__await__"):
            comparison = await comparison
        shadow_result = compare_shadow_results(result, comparison)
        shadow_result["metadata"] = engine_metadata(engine)
    return EngineRouteResult(engine=engine, result=result, shadow=shadow_result)
