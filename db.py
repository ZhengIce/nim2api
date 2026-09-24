import os
import time

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT UNIQUE NOT NULL,
    label TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    cooldown_until REAL DEFAULT 0,
    total_requests INTEGER DEFAULT 0,
    total_prompt_tokens INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER,
    model TEXT,
    status INTEGER,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS gateway_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    label TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    owned_by TEXT DEFAULT '',
    label TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    source TEXT DEFAULT 'upstream',
    last_seen_at REAL DEFAULT 0,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS model_check_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    status INTEGER DEFAULT 0,
    ok INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    message TEXT DEFAULT '',
    check_trigger TEXT DEFAULT 'manual',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_created ON request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_model_check_logs_model_created
    ON model_check_logs(model_id, created_at);
"""

KEY_COLUMNS = {
    "last_checked_at": "REAL DEFAULT 0",
    "last_check_status": "INTEGER DEFAULT 0",
    "last_check_latency_ms": "INTEGER DEFAULT 0",
    "last_check_message": "TEXT DEFAULT ''",
}

MODEL_COLUMNS = {
    "last_checked_at": "REAL DEFAULT 0",
    "last_check_status": "INTEGER DEFAULT 0",
    "last_check_ok": "INTEGER DEFAULT 0",
    "last_check_latency_ms": "INTEGER DEFAULT 0",
    "last_check_message": "TEXT DEFAULT ''",
}

async def init_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        cur = await db.execute("PRAGMA table_info(keys)")
        existing = {row[1] for row in await cur.fetchall()}
        for name, definition in KEY_COLUMNS.items():
            if name not in existing:
                await db.execute(f"ALTER TABLE keys ADD COLUMN {name} {definition}")
        cur = await db.execute("PRAGMA table_info(models)")
        existing = {row[1] for row in await cur.fetchall()}
        for name, definition in MODEL_COLUMNS.items():
            if name not in existing:
                await db.execute(f"ALTER TABLE models ADD COLUMN {name} {definition}")
        await db.commit()


def connect():
    db = aiosqlite.connect(config.DB_PATH)
    return db


async def log_request(key_id, model, status, prompt_tokens, completion_tokens, latency_ms):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO request_logs (key_id, model, status, prompt_tokens, completion_tokens, latency_ms, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (key_id, model, status, prompt_tokens, completion_tokens, latency_ms, time.time()),
        )
        await db.commit()
