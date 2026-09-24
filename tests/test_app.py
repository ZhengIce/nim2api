import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx

import config
import db
from main import app
from pool import pool


class GatewayAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._old_db_path = config.DB_PATH
        self._old_system_prompt_mode = config.SYSTEM_PROMPT_MODE
        self._old_system_prompt = config.SYSTEM_PROMPT
        self.temp_dir = tempfile.TemporaryDirectory()
        config.DB_PATH = os.path.join(self.temp_dir.name, "gateway.db")
        config.SYSTEM_PROMPT_MODE = "passthrough"
        config.SYSTEM_PROMPT = ""
        pool._cursor = 0
        await db.init_db()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        config.DB_PATH = self._old_db_path
        config.SYSTEM_PROMPT_MODE = self._old_system_prompt_mode
        config.SYSTEM_PROMPT = self._old_system_prompt
        self.temp_dir.cleanup()

    async def login(self):
        response = await self.client.post(
            "/admin/api/login",
            json={"password": config.ADMIN_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)

    async def test_login_protects_admin_endpoints(self):
        response = await self.client.get("/admin/api/session")
        self.assertEqual(response.status_code, 401)

        await self.login()
        response = await self.client.get("/admin/api/session")
        self.assertEqual(response.status_code, 200)
        response = await self.client.get("/admin/api/health")
        self.assertEqual(response.status_code, 200)
        response = await self.client.get("/admin/api/model-checks/schedule")
        self.assertEqual(response.status_code, 200)
        self.assertIn("enabled", response.json())
        self.assertIn("next_run_at", response.json())
        response = await self.client.get("/admin/api/model-checks/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["history"], {})

    async def test_disabled_model_is_blocked_before_upstream_request(self):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO models (id, enabled, source, created_at) VALUES (?,?,?,?)",
            ("disabled/test-model", 0, "manual", 0),
        )
        conn.commit()
        conn.close()

        response = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "disabled/test-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(response.status_code, 403)

    async def test_model_check_records_missing_key_result(self):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO models (id, enabled, source, created_at) VALUES (?,?,?,?)",
            ("test/chat-model", 1, "manual", 0),
        )
        conn.commit()
        conn.close()

        await self.login()
        response = await self.client.post(
            "/admin/api/model-checks/check",
            json={"id": "test/chat-model"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], 0)
        self.assertIn("上游密钥", response.json()["message"])

        conn = sqlite3.connect(config.DB_PATH)
        row = conn.execute(
            "SELECT last_checked_at, last_check_message FROM models WHERE id = ?",
            ("test/chat-model",),
        ).fetchone()
        history_row = conn.execute(
            "SELECT status, ok, check_trigger, created_at"
            " FROM model_check_logs WHERE model_id = ?",
            ("test/chat-model",),
        ).fetchone()
        conn.close()
        self.assertGreater(row[0], 0)
        self.assertIn("上游密钥", row[1])
        self.assertEqual(history_row[:3], (0, 0, "manual"))
        self.assertGreater(history_row[3], 0)

        response = await self.client.get("/admin/api/model-checks/history?points=24")
        self.assertEqual(response.status_code, 200)
        history = response.json()["history"]["test/chat-model"]
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["ok"])
        self.assertEqual(history[0]["status"], 0)

    async def test_editor_compatibility_routes_exist(self):
        requests = [
            ("/v1/responses", {"model": "test/model", "input": "hello"}),
            ("/v1/completions", {"model": "test/model", "prompt": "hello"}),
            ("/v1/embeddings", {"model": "test/model", "input": "hello"}),
        ]
        for path, payload in requests:
            with self.subTest(path=path):
                response = await self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 503)

    async def test_system_preset_and_auth_failure_rotate_to_next_key(self):
        conn = sqlite3.connect(config.DB_PATH)
        conn.executemany(
            "INSERT INTO keys (api_key, label, created_at) VALUES (?,?,?)",
            [("bad-key", "bad", 0), ("good-key", "good", 0)],
        )
        conn.commit()
        conn.close()

        config.SYSTEM_PROMPT_MODE = "replace"
        config.SYSTEM_PROMPT = "Gateway system preset"
        attempts = []
        forwarded = []

        def handler(request):
            attempts.append(request.headers.get("authorization"))
            forwarded.append(request.read().decode())
            if request.headers.get("authorization") == "Bearer bad-key":
                return httpx.Response(401, json={"error": {"message": "invalid upstream key"}})
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            )

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            return real_async_client(transport=httpx.MockTransport(handler))

        with patch("proxy.httpx.AsyncClient", side_effect=client_factory):
            response = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": "test/model",
                    "messages": [
                        {"role": "system", "content": "client preset"},
                        {"role": "user", "content": "hello"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempts, ["Bearer bad-key", "Bearer good-key"])
        payload = json.loads(forwarded[-1])
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "Gateway system preset"})
        self.assertNotIn("client preset", [message.get("content") for message in payload["messages"]])

        conn = sqlite3.connect(config.DB_PATH)
        cooldown = conn.execute("SELECT cooldown_until FROM keys WHERE api_key = 'bad-key'").fetchone()[0]
        conn.close()
        self.assertGreater(cooldown, 0)

    async def test_vue_routes_serve_the_spa(self):
        response = await self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        for path in ("/", "/login", "/overview", "/checks", "/models", "/keys", "/tokens", "/settings", "/docs"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("NIM Gateway Console", response.text)


if __name__ == "__main__":
    unittest.main()
