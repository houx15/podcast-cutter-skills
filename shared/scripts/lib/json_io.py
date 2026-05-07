"""Atomic JSON read/write helpers.

Atomicity matters because a half-written words.json (megabytes of
ASR output) corrupts the entire downstream pipeline. We always write
to <path>.tmp and rename at the end.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def dump_json(payload: Any, path: Path) -> None:
    """Serialize payload to path atomically. Creates parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path) -> Any:
    """Read and parse JSON from path. Raises FileNotFoundError if absent."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
