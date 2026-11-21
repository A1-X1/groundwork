"""SQLite storage for things users create: drawn areas and structures (projects).

One file, standard library only. Location: ``GROUNDWORK_DB`` or ``.groundwork/groundwork.db`` at
the repo root (gitignored). Tables are created on first use, so there is no migration step.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE IF NOT EXISTS areas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    geometry    TEXT NOT NULL,          -- GeoJSON Polygon
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,              -- JSON
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS structures (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    profile     TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '{}',   -- JSON: requirements (GPUs, cooling, ...)
    priorities  TEXT NOT NULL DEFAULT '[]',   -- JSON list of layer ids
    area_id     TEXT REFERENCES areas(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("GROUNDWORK_DB") or ROOT / ".groundwork" / "groundwork.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- areas


def _area(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["geometry"] = json.loads(d["geometry"])
    return d


def list_areas() -> list[dict[str, Any]]:
    with connect() as c:
        return [_area(r) for r in c.execute("SELECT * FROM areas ORDER BY created_at DESC")]


def get_area(area_id: str) -> dict[str, Any]:
    with connect() as c:
        row = c.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone()
    if row is None:
        raise KeyError(f"area '{area_id}'")
    return _area(row)


def create_area(name: str, geometry: dict[str, Any], note: str = "") -> dict[str, Any]:
    aid, now = uuid.uuid4().hex[:12], _now()
    with connect() as c:
        c.execute(
            "INSERT INTO areas VALUES (?, ?, ?, ?, ?, ?)",
            (aid, name, note, json.dumps(geometry), now, now),
        )
    return get_area(aid)


def update_area(area_id: str, **fields: Any) -> dict[str, Any]:
    get_area(area_id)
    sets = {k: v for k, v in fields.items() if v is not None}
    if "geometry" in sets:
        sets["geometry"] = json.dumps(sets["geometry"])
    if sets:
        sets["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in sets)
        with connect() as c:
            c.execute(f"UPDATE areas SET {cols} WHERE id = ?", (*sets.values(), area_id))
    return get_area(area_id)


def delete_area(area_id: str) -> None:
    get_area(area_id)
    with connect() as c:
        c.execute("DELETE FROM areas WHERE id = ?", (area_id,))


# --------------------------------------------------------------------------- structures


def _structure(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["spec"] = json.loads(d["spec"]) or None
    d["priorities"] = json.loads(d["priorities"])
    return d


def list_structures() -> list[dict[str, Any]]:
    with connect() as c:
        rows = c.execute("SELECT * FROM structures ORDER BY created_at DESC")
        return [_structure(r) for r in rows]


def get_structure(sid: str) -> dict[str, Any]:
    with connect() as c:
        row = c.execute("SELECT * FROM structures WHERE id = ?", (sid,)).fetchone()
    if row is None:
        raise KeyError(f"structure '{sid}'")
    return _structure(row)


def create_structure(
    name: str,
    type_: str,
    profile: str,
    spec: dict[str, Any] | None,
    priorities: list[str],
    area_id: str | None,
) -> dict[str, Any]:
    if area_id:
        get_area(area_id)
    sid, now = uuid.uuid4().hex[:12], _now()
    with connect() as c:
        c.execute(
            "INSERT INTO structures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, name, type_, profile, json.dumps(spec or {}), json.dumps(priorities), area_id,
             now, now),
        )
    return get_structure(sid)


def update_structure(sid: str, **fields: Any) -> dict[str, Any]:
    get_structure(sid)
    sets = {k: v for k, v in fields.items() if v is not None}
    for k in ("spec", "priorities"):
        if k in sets:
            sets[k] = json.dumps(sets[k])
    if sets.get("area_id"):
        get_area(sets["area_id"])
    if sets:
        sets["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in sets)
        with connect() as c:
            c.execute(f"UPDATE structures SET {cols} WHERE id = ?", (*sets.values(), sid))
    return get_structure(sid)


def delete_structure(sid: str) -> None:
    get_structure(sid)
    with connect() as c:
        c.execute("DELETE FROM structures WHERE id = ?", (sid,))


# --------------------------------------------------------------------------- settings


def get_setting(key: str) -> Any:
    """JSON value for a key (e.g. "azure_ml"), or None. No secrets are stored here."""
    with connect() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def set_setting(key: str, value: Any) -> None:
    """Store a JSON value; ``None`` deletes the key."""
    with connect() as c:
        if value is None:
            c.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            c.execute(
                "INSERT INTO settings VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (key, json.dumps(value), _now()),
            )
