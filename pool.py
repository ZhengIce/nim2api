import time

import aiosqlite

import config


class KeyPool:
    def __init__(self):
        self._cursor = 0

    async def _load_available(self):
        now = time.time()
        async with aiosqlite.connect(config.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM keys WHERE enabled = 1 AND cooldown_until < ? ORDER BY id",
                (now,),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def acquire(self):
        keys = await self._load_available()
        if not keys:
            return None
        n = len(keys)
        start = self._cursor % n
        self._cursor += 1
        return keys[start:] + keys[:start]

    async def on_rate_limited(self, key_id):
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE keys SET cooldown_until = ?, fail_count = fail_count + 1 WHERE id = ?",
                (time.time() + config.COOLDOWN_SECONDS, key_id),
            )
            await db.commit()

    async def on_failure(self, key_id):
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE keys SET fail_count = fail_count + 1 WHERE id = ?",
                (key_id,),
            )
            await db.commit()

    async def on_success(self, key_id, prompt_tokens, completion_tokens):
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE keys SET total_requests = total_requests + 1,"
                " total_prompt_tokens = total_prompt_tokens + ?,"
                " total_completion_tokens = total_completion_tokens + ?"
                " WHERE id = ?",
                (prompt_tokens, completion_tokens, key_id),
            )
            await db.commit()


pool = KeyPool()
