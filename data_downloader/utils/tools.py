from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, overload

from data_downloader.logging import setup_logger

logger = setup_logger(__name__)


@overload
def safe_repr(obj: Path) -> str: ...


@overload
def safe_repr(obj: Mapping) -> dict: ...


@overload
def safe_repr(obj: Iterable) -> list: ...


@overload
def safe_repr(obj: Any) -> Any: ...


def safe_repr(obj: Path | Mapping | Iterable | Any) -> str | dict | list | Any:
    """Convert objects to strings for safe serialization"""
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, Mapping):
        return {k: safe_repr(v) for k, v in obj.items()}
    elif isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, Mapping)):
        return [safe_repr(x) for x in obj]
    else:
        return obj
