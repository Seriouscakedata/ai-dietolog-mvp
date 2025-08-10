"""Utilities for safe JSON storage.

This module implements atomic reading and writing of JSON files with file locking.
Each Telegram user has a dedicated directory under ``data/<tg_user_id>/`` where
all of their JSON files are stored.  All access should go through the
functions defined here to ensure consistency and proper locking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Type, TypeVar

from filelock import FileLock
from pydantic import BaseModel
from .schema import Today
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Base data directory.  This will be created on first import if it doesn't
# already exist.  Use the monkeypatch fixture in tests to override this
# location.
DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _lock_path(path: Path) -> Path:
    """Return the path of the lock file corresponding to ``path``.

    The lock file uses the same name as the target file, with an extra
    ``.lock`` suffix.  This prevents concurrent writes and ensures atomic
    replacement of JSON files.
    """
    return path.with_suffix(path.suffix + ".lock")


def read_json(path: Path, model_cls: Type[T]) -> T:
    """Read a JSON file into a pydantic model.

    If the file does not exist, an empty instance of ``model_cls`` is
    returned.  Reading is protected by a file lock to avoid reading a
    partially written file.

    Args:
        path: Path to the JSON file.
        model_cls: The pydantic model class to instantiate.

    Returns:
        An instance of ``model_cls`` loaded from JSON.
    """
    if not path.exists():
        return model_cls()  # type: ignore[arg-type]
    # Acquire a lock while reading to avoid concurrent writes corrupting the file.
    lock = FileLock(str(_lock_path(path)))
    with lock:
        contents = path.read_text(encoding="utf-8")
    # Handle empty or corrupted files gracefully by returning a default instance
    if not contents.strip():
        return model_cls()  # type: ignore[arg-type]
    try:
        return model_cls.model_validate_json(contents)
    except Exception:
        return model_cls()  # type: ignore[arg-type]


def write_json(path: Path, obj: BaseModel) -> None:
    """Atomically write a pydantic object to a JSON file.

    The target directory is created if it does not exist.  The entire
    operation is guarded by a file lock to ensure that no other process
    attempts to read or write the file concurrently.

    Args:
        path: Path to write to.
        obj: A pydantic model instance to serialise.
    """
    # Ensure the parent directory exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Acquire the lock associated with this file.
    lock = FileLock(str(_lock_path(path)))
    with lock:
        # Serialise the model first so that any ``ValueError`` (e.g. NaN
        # values when ``allow_nan`` is ``False``) is raised before we touch the
        # target file.  ``model_dump`` produces a plain ``dict`` that we can
        # encode safely with ``json.dumps``.
        data = obj.model_dump(mode="json")
        json_data = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json_data, encoding="utf-8")
        tmp_path.replace(path)


def user_dir(user_id: str | int) -> Path:
    """Return the directory path for a specific Telegram user.

    Directories are created lazily.  Passing non‑string values is allowed
    (e.g. ints) and will be converted to strings.
    """
    user_path = DATA_DIR / str(user_id)
    user_path.mkdir(parents=True, exist_ok=True)
    return user_path


def json_path(user_id: str | int, filename: str) -> Path:
    """Compute the path to a JSON file in a user's directory.

    Args:
        user_id: Telegram user identifier.
        filename: Name of the JSON file (e.g. ``profile.json``).
    Returns:
        Absolute ``Path`` to the requested JSON file.
    """
    return user_dir(user_id) / filename


def load_profile(user_id: str | int, model_cls: Type[T]) -> T:
    """Convenience function to load a user's profile JSON.

    Args:
        user_id: Telegram user identifier.
        model_cls: Pydantic model class representing the profile.

    Returns:
        An instance of ``model_cls``.
    """
    return read_json(json_path(user_id, "profile.json"), model_cls)


def save_profile(user_id: str | int, profile: BaseModel) -> None:
    """Write a profile object for a user.

    Args:
        user_id: Telegram user identifier.
        profile: Pydantic model representing the profile.
    """
    write_json(json_path(user_id, "profile.json"), profile)


def today_path(user_id: str | int) -> Path:
    """Return path to ``today.json`` for a user."""
    return json_path(user_id, "today.json")


def load_today(user_id: str | int) -> Today:
    """Load today's meal log for ``user_id``."""
    path = today_path(user_id)
    today = read_json(path, Today)
    logger.debug(
        "load_today: user=%s path=%s meals=%d summary=%s",
        user_id,
        path,
        len(today.meals),
        today.summary.model_dump(),
    )
    return today


def save_today(user_id: str | int, today: Today) -> None:
    """Persist today's data for ``user_id``.

    This method now merges the incoming ``today`` object with any existing
    meals already stored on disk.  Previously a call that contained only the
    latest meal would overwrite the file and discard earlier entries.  By
    merging we ensure that multiple meal confirmations within a day are
    accumulated instead of replacing each other.
    """
    path = today_path(user_id)
    # Load existing state so previously saved meals are not lost.
    existing = load_today(user_id)
    meal_map = {m.id: m for m in existing.meals}
    for meal in today.meals:
        meal_map[meal.id] = meal
    existing.meals = list(meal_map.values())
    existing.summary = today.summary
    existing.day_closed = today.day_closed
    existing.last_updated = today.last_updated
    logger.debug(
        "save_today: user=%s path=%s meals=%d summary=%s",
        user_id,
        path,
        len(existing.meals),
        existing.summary.model_dump(),
    )
    write_json(path, existing)


def append_meal(user_id: str | int, meal: BaseModel) -> None:
    """Append a meal to ``today.json`` for the user."""
    path = today_path(user_id)
    logger.info(
        "append_meal: user=%s meal_id=%s path=%s",
        user_id,
        getattr(meal, "id", "<unknown>"),
        path,
    )
    today = load_today(user_id)
    today.append_meal(meal)
    save_today(user_id, today)
