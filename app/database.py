"""Слой работы с базой данных SQLite для планировщика проектов."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "planner.db"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',          -- active | paused | done
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',        -- low | medium | high
            due_date TEXT,                         -- 'YYYY-MM-DD HH:MM' — момент напоминания
            reminder_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',            -- open | done
            created_at TEXT DEFAULT (datetime('now','localtime')),
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """)


def rows_to_list(rows):
    return [dict(r) for r in rows]
