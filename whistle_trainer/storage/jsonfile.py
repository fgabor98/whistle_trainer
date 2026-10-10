"""Atomic JSON files with recovery from unreadable content."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class UnreadableFile(Exception):
    """The file exists but its content cannot be used."""


def read_json(path: Path) -> dict | None:
    """The file's JSON object, or None if the file does not exist.

    Raises UnreadableFile if the file is not a JSON object.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise UnreadableFile(str(error)) from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise UnreadableFile(str(error)) from error
    if not isinstance(data, dict):
        raise UnreadableFile("not a JSON object")
    return data


def write_json_atomic(path: Path, data: dict) -> None:
    """Write so that a crash leaves either the old or the new file, never a partial one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def quarantine(path: Path) -> Path:
    """Move an unreadable file aside so it is kept but no longer used."""
    backup = path.with_name(path.name + ".corrupt")
    os.replace(path, backup)
    return backup


def require(data: dict, key: str, kind: type | tuple[type, ...], default=None):
    """A typed value from loaded JSON, or the default when missing.

    Raises UnreadableFile if the value has the wrong type.
    """
    if key not in data or data[key] is None:
        return default
    value = data[key]
    # bool is a subclass of int; a stored true/false is never a valid number.
    if not isinstance(value, kind) or (isinstance(value, bool) and bool not in _as_tuple(kind)):
        raise UnreadableFile(f"{key!r} has an unexpected value")
    return value


def _as_tuple(kind: type | tuple[type, ...]) -> tuple[type, ...]:
    return kind if isinstance(kind, tuple) else (kind,)
