"""Resolve the analysis engine saved with a site or overridden for a run."""

from typing import Any, Mapping, Optional


def resolve_engine(config: Mapping[str, Any], override: Optional[str] = None) -> str:
    """Keep legacy behavior for older sites that have no saved engine."""
    selected = override if override is not None else config.get("engine", "legacy")
    if not isinstance(selected, str) or selected.lower() not in ("legacy", "pipeline"):
        raise ValueError("Engine must be 'legacy' or 'pipeline'.")
    return selected.lower()
