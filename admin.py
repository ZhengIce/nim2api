import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse

import aiosqlite
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config

router = APIRouter(prefix="/admin/api")

SESSION_COOKIE = "nim_admin_session"
SESSION_TTL_SECONDS = 24 * 60 * 60
MODEL_CHECK_STATE = {
    "running": False,
    "last_run_at": 0,
    "next_run_at": 0,
    "last_total": 0,
    "last_success": 0,
    "last_trigger": "",
    "last_error": "",
}


def _session_key():
    return hashlib.sha256(f"nim-admin:{config.ADMIN_PASSWORD}".encode()).digest()


def _password_matches(candidate: str):
    return hmac.compare_digest(candidate.encode(), config.ADMIN_PASSWORD.encode())


def _issue_session():
    payload = f"{int(time.time()) + SESSION_TTL_SECONDS}:{secrets.token_urlsafe(18)}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(_session_key(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _valid_session(token: str):
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(_session_key(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        padded = encoded + "=" * (-len(encoded) % 4)
        expires, _ = base64.urlsafe_b64decode(padded).decode().split(":", 1)
        return int(expires) > time.time()
    except (ValueError, UnicodeDecodeError):
        return False


def _check_basic(request: Request):
    session = request.cookies.get(SESSION_COOKIE, "")
    if session and _valid_session(session):
        return None

    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, _, pwd = decoded.partition(":")
            if user == "admin" and _password_matches(pwd):
                return None
        except (ValueError, UnicodeDecodeError):
            pass
    return JSONResponse(status_code=401, content={"detail": "unauthorized"})


def _mask(value: str) -> str:
    if len(value) <= 8:
        return value[:2] + "***"
    return value[:8] + "***"


async def _json_body(request: Request):
    try:
        return await request.json()
    except Exception:
        return None


@router.post("/login")
async def login(request: Request):
    body = await _json_body(request)
    password = str((body or {}).get("password") or "")
    if not _password_matches(password):
        return JSONResponse(status_code=401, content={"detail": "密码错误"})
    response = JSONResponse({"ok": True})
    response.set_cookie(
        SESSION_COOKIE,
        _issue_session(),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return response


@router.post("/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/session")
async def session(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    return {"authenticated": True}


@router.get("/keys")
async def list_keys(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    now = time.time()
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM keys ORDER BY id")
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        row["api_key"] = _mask(row["api_key"])
        row["cooling"] = bool(row["enabled"] and row["cooldown_until"] > now)
        row["cooldown_remaining"] = max(0, int(row["cooldown_until"] - now))
    return {"keys": rows}


@router.post("/keys")
async def add_key(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    if body is None:
        return JSONResponse(status_code=400, content={"detail": "invalid json"})
    api_key = (body.get("api_key") or "").strip()
    label = (body.get("label") or "").strip()
    if not api_key:
        return JSONResponse(status_code=400, content={"detail": "api_key required"})
    async with aiosqlite.connect(config.DB_PATH) as conn:
        try:
            cur = await conn.execute(
                "INSERT INTO keys (api_key, label, created_at) VALUES (?,?,?)",
                (api_key, label, time.time()),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            return JSONResponse(status_code=409, content={"detail": "api_key already exists"})
    return {"id": cur.lastrowid}


@router.delete("/keys/{key_id}")
async def delete_key(key_id: int, request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("DELETE FROM keys WHERE id = ?", (key_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/keys/{key_id}/toggle")
async def toggle_key(key_id: int, request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE keys SET enabled = 1 - enabled, cooldown_until = 0 WHERE id = ?",
            (key_id,),
        )
        await conn.commit()
    return {"ok": True}


def _upstream_error(response):
    try:
        data = response.json()
        return data.get("detail") or data.get("error", {}).get("message")
    except (ValueError, AttributeError):
        return None


def _model_probe_payload(model_id):
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }


async def _probe_model(model, trigger="manual"):
    started = time.perf_counter()
    status = 0
    ok = False
    message = "没有可用于检测的上游密钥"
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM keys WHERE enabled = 1 AND cooldown_until < ? ORDER BY id",
            (time.time(),),
        )
        keys = [dict(row) for row in await cur.fetchall()]

    if keys:
        message = "模型请求失败"
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=8)) as client:
            for key in keys:
                try:
                    response = await client.post(
                        f"{config.UPSTREAM_BASE_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {key['api_key']}"},
                        json=_model_probe_payload(model["id"]),
                    )
                except httpx.TimeoutException:
                    message = "模型推理超时"
                    continue
                except httpx.HTTPError:
                    message = "无法连接上游服务"
                    continue

                status = response.status_code
                if response.is_success:
                    ok = True
                    message = "聊天补全请求成功"
                    break
                message = _upstream_error(response) or f"上游返回 HTTP {status}"
                if status not in {401, 403, 429} and status < 500:
                    break

    latency_ms = round((time.perf_counter() - started) * 1000)
    checked_at = time.time()
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE models SET last_checked_at = ?, last_check_status = ?, last_check_ok = ?,"
            " last_check_latency_ms = ?, last_check_message = ? WHERE id = ?",
            (checked_at, status, int(ok), latency_ms, message[:300], model["id"]),
        )
        await conn.execute(
            "INSERT INTO model_check_logs"
            " (model_id, status, ok, latency_ms, message, check_trigger, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                model["id"],
                status,
                int(ok),
                latency_ms,
                message[:300],
                trigger,
                checked_at,
            ),
        )
        await conn.execute(
            "DELETE FROM model_check_logs WHERE model_id = ? AND id NOT IN"
            " (SELECT id FROM model_check_logs WHERE model_id = ? ORDER BY id DESC LIMIT 200)",
            (model["id"], model["id"]),
        )
        await conn.commit()
    return {
        "id": model["id"],
        "status": status,
        "ok": ok,
        "latency_ms": latency_ms,
        "message": message,
        "checked_at": checked_at,
    }


def reset_model_check_schedule():
    MODEL_CHECK_STATE["next_run_at"] = (
        time.time() + config.MODEL_CHECK_INTERVAL_MINUTES * 60
        if config.MODEL_CHECK_ENABLED
        else 0
    )


async def _run_enabled_model_checks(trigger):
    if MODEL_CHECK_STATE["running"]:
        return {"results": [], "skipped": True}

    MODEL_CHECK_STATE["running"] = True
    MODEL_CHECK_STATE["last_error"] = ""
    try:
        async with aiosqlite.connect(config.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM models WHERE enabled = 1 ORDER BY id")
            rows = [dict(row) for row in await cur.fetchall()]
        semaphore = asyncio.Semaphore(3)

        async def run(row):
            async with semaphore:
                return await _probe_model(row, trigger)

        results = await asyncio.gather(*(run(row) for row in rows))
        MODEL_CHECK_STATE["last_run_at"] = time.time()
        MODEL_CHECK_STATE["last_total"] = len(results)
        MODEL_CHECK_STATE["last_success"] = sum(1 for result in results if result["ok"])
        MODEL_CHECK_STATE["last_trigger"] = trigger
        return {"results": results, "skipped": False}
    except Exception as exc:
        MODEL_CHECK_STATE["last_run_at"] = time.time()
        MODEL_CHECK_STATE["last_error"] = str(exc)[:300]
        raise
    finally:
        MODEL_CHECK_STATE["running"] = False
        reset_model_check_schedule()


async def model_check_scheduler():
    reset_model_check_schedule()
    while True:
        try:
            if not config.MODEL_CHECK_ENABLED:
                MODEL_CHECK_STATE["next_run_at"] = 0
                await asyncio.sleep(5)
                continue
            if not MODEL_CHECK_STATE["next_run_at"]:
                reset_model_check_schedule()
            delay = MODEL_CHECK_STATE["next_run_at"] - time.time()
            if delay > 0:
                await asyncio.sleep(min(5, delay))
                continue
            await _run_enabled_model_checks("scheduled")
        except asyncio.CancelledError:
            raise
        except Exception:
            MODEL_CHECK_STATE["next_run_at"] = time.time() + 60
            await asyncio.sleep(5)


@router.post("/model-checks/check")
async def check_model(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    model_id = str((body or {}).get("id") or "")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM models WHERE id = ?", (model_id,))
        row = await cur.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"detail": "model not found"})
    return await _probe_model(dict(row), "manual")


@router.post("/model-checks/run")
async def run_model_checks(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    return await _run_enabled_model_checks("manual")


@router.get("/model-checks/schedule")
async def model_check_schedule(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    return {
        "enabled": config.MODEL_CHECK_ENABLED,
        "interval_minutes": config.MODEL_CHECK_INTERVAL_MINUTES,
        **MODEL_CHECK_STATE,
    }


@router.get("/model-checks/history")
async def model_check_history(request: Request, points: int = 24):
    err = _check_basic(request)
    if err is not None:
        return err
    points = max(1, min(points, 60))
    history = {}
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT model_id, status, ok, latency_ms, check_trigger, created_at"
            " FROM model_check_logs ORDER BY model_id, id DESC"
        )
        rows = await cur.fetchall()
    for row in rows:
        model_history = history.setdefault(row["model_id"], [])
        if len(model_history) < points:
            model_history.append({
                "status": row["status"],
                "ok": bool(row["ok"]),
                "latency_ms": row["latency_ms"],
                "trigger": row["check_trigger"],
                "created_at": row["created_at"],
            })
    for model_history in history.values():
        model_history.reverse()
    return {"history": history, "points": points}


@router.get("/health")
async def health(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        keys = (await (await conn.execute("SELECT COUNT(*) FROM keys")).fetchone())[0]
        models = (await (await conn.execute("SELECT COUNT(*) FROM models")).fetchone())[0]
        logs = (await (await conn.execute("SELECT COUNT(*) FROM request_logs")).fetchone())[0]
    return {
        "service": "ok",
        "database": "ok",
        "upstream_base_url": config.UPSTREAM_BASE_URL,
        "counts": {"keys": keys, "models": models, "logs": logs},
        "checked_at": time.time(),
    }


@router.get("/models")
async def list_models(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM models ORDER BY id")
        rows = [dict(r) for r in await cur.fetchall()]
    return {"models": rows}


@router.post("/models")
async def add_model(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    model_id = str((body or {}).get("id") or "").strip()
    label = str((body or {}).get("label") or "").strip()
    if not model_id:
        return JSONResponse(status_code=400, content={"detail": "model id required"})
    async with aiosqlite.connect(config.DB_PATH) as conn:
        try:
            await conn.execute(
                "INSERT INTO models (id, label, source, last_seen_at, created_at) VALUES (?,?,?,?,?)",
                (model_id, label, "manual", time.time(), time.time()),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            return JSONResponse(status_code=409, content={"detail": "model already exists"})
    return {"ok": True}


@router.post("/models/sync")
async def sync_models(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM keys WHERE enabled = 1 ORDER BY id")
        keys = [dict(r) for r in await cur.fetchall()]
    if not keys:
        return JSONResponse(status_code=503, content={"detail": "没有可用的上游密钥"})

    payload = None
    last_status = 503
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=8)) as client:
        for key in keys:
            try:
                response = await client.get(
                    f"{config.UPSTREAM_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {key['api_key']}"},
                )
            except httpx.HTTPError:
                continue
            last_status = response.status_code
            if response.is_success:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                break
    if not isinstance(payload, dict):
        return JSONResponse(status_code=502, content={"detail": f"同步失败，上游状态 {last_status}"})

    now = time.time()
    items = payload.get("data") or []
    synced = 0
    async with aiosqlite.connect(config.DB_PATH) as conn:
        for item in items:
            if isinstance(item, str):
                model_id, owned_by = item, ""
            else:
                model_id = str(item.get("id") or "").strip()
                owned_by = str(item.get("owned_by") or "")
            if not model_id:
                continue
            await conn.execute(
                "INSERT INTO models (id, owned_by, source, last_seen_at, created_at)"
                " VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
                " owned_by = excluded.owned_by, source = 'upstream', last_seen_at = excluded.last_seen_at",
                (model_id, owned_by, "upstream", now, now),
            )
            synced += 1
        await conn.commit()
    return {"ok": True, "synced": synced}


@router.post("/models/toggle")
async def toggle_model(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    model_id = str((body or {}).get("id") or "")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("UPDATE models SET enabled = 1 - enabled WHERE id = ?", (model_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/models/delete")
async def delete_model(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    model_id = str((body or {}).get("id") or "")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("DELETE FROM model_check_logs WHERE model_id = ?", (model_id,))
        await conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await conn.commit()
    return {"ok": True}


@router.get("/stats")
async def stats(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    now = time.time()
    lt = time.localtime(now)
    day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT COUNT(*) AS total_requests, COALESCE(SUM(prompt_tokens),0) AS total_prompt,"
            " COALESCE(SUM(completion_tokens),0) AS total_completion,"
            " COALESCE(AVG(latency_ms),0) AS avg_latency FROM request_logs"
        )
        agg = dict(await cur.fetchone())
        cur = await conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens + completion_tokens),0) AS today_tokens"
            " FROM request_logs WHERE created_at >= ?",
            (day_start,),
        )
        today = dict(await cur.fetchone())
        cur = await conn.execute(
            "SELECT COUNT(*) AS total_keys,"
            " SUM(CASE WHEN enabled = 1 AND cooldown_until < ? THEN 1 ELSE 0 END) AS available_keys FROM keys",
            (now,),
        )
        keys = dict(await cur.fetchone())
    return {
        "total_requests": agg["total_requests"],
        "total_tokens": agg["total_prompt"] + agg["total_completion"],
        "today_tokens": today["today_tokens"],
        "avg_latency_ms": round(agg["avg_latency"] or 0),
        "total_keys": keys["total_keys"] or 0,
        "available_keys": keys["available_keys"] or 0,
    }


@router.get("/usage")
async def usage(request: Request, minutes: int = 60):
    err = _check_basic(request)
    if err is not None:
        return err
    minutes = max(1, min(minutes, 1440))
    now = time.time()
    start = now - minutes * 60
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT CAST(created_at / 60 AS INTEGER) AS bucket,"
            " SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion"
            " FROM request_logs WHERE created_at >= ? GROUP BY bucket ORDER BY bucket",
            (start,),
        )
        rows = {int(r["bucket"]): (r["prompt"], r["completion"]) for r in await cur.fetchall()}
    series = []
    for bucket in range(int(start // 60), int(now // 60) + 1):
        prompt, completion = rows.get(bucket, (0, 0))
        series.append({
            "t": bucket * 60,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total": prompt + completion,
        })
    return {"series": series}


@router.get("/logs")
async def logs(request: Request, limit: int = 50):
    err = _check_basic(request)
    if err is not None:
        return err
    limit = max(1, min(limit, 500))
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, k.label AS key_label, k.api_key AS api_key"
            " FROM request_logs l LEFT JOIN keys k ON l.key_id = k.id"
            " ORDER BY l.id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        if row.get("api_key"):
            row["api_key"] = _mask(row["api_key"])
    return {"logs": rows}


@router.get("/tokens")
async def list_tokens(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM gateway_tokens ORDER BY id")
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        row["token"] = _mask(row["token"])
    return {"tokens": rows}


@router.post("/tokens")
async def add_token(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    if body is None:
        return JSONResponse(status_code=400, content={"detail": "invalid json"})
    token = (body.get("token") or "").strip()
    label = (body.get("label") or "").strip()
    generated = False
    if not token:
        token = "gw-" + secrets.token_urlsafe(24)
        generated = True
    async with aiosqlite.connect(config.DB_PATH) as conn:
        try:
            cur = await conn.execute(
                "INSERT INTO gateway_tokens (token, label, created_at) VALUES (?,?,?)",
                (token, label, time.time()),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            return JSONResponse(status_code=409, content={"detail": "token already exists"})
    return {"id": cur.lastrowid, "token": token, "generated": generated}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: int, request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("DELETE FROM gateway_tokens WHERE id = ?", (token_id,))
        await conn.commit()
    return {"ok": True}


@router.post("/tokens/{token_id}/toggle")
async def toggle_token(token_id: int, request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("UPDATE gateway_tokens SET enabled = 1 - enabled WHERE id = ?", (token_id,))
        await conn.commit()
    return {"ok": True}


@router.get("/config")
async def get_config(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    return {
        "listen_port": config.LISTEN_PORT,
        "cooldown_seconds": config.COOLDOWN_SECONDS,
        "upstream_base_url": config.UPSTREAM_BASE_URL,
        "model_check_enabled": config.MODEL_CHECK_ENABLED,
        "model_check_interval_minutes": config.MODEL_CHECK_INTERVAL_MINUTES,
        "system_prompt_mode": config.SYSTEM_PROMPT_MODE,
        "system_prompt": config.SYSTEM_PROMPT,
        "admin_password_configured": bool(config.ADMIN_PASSWORD),
    }


@router.put("/config")
async def save_config(request: Request):
    err = _check_basic(request)
    if err is not None:
        return err
    body = await _json_body(request)
    if body is None:
        return JSONResponse(status_code=400, content={"detail": "invalid json"})
    try:
        listen_port = int(body.get("listen_port", config.LISTEN_PORT))
        cooldown = float(body.get("cooldown_seconds", config.COOLDOWN_SECONDS))
        model_check_interval = int(
            body.get("model_check_interval_minutes", config.MODEL_CHECK_INTERVAL_MINUTES)
        )
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"detail": "端口或时间间隔格式不正确"})
    model_check_enabled = body.get("model_check_enabled", config.MODEL_CHECK_ENABLED)
    system_prompt_mode = str(body.get("system_prompt_mode", config.SYSTEM_PROMPT_MODE))
    system_prompt = str(body.get("system_prompt", config.SYSTEM_PROMPT))
    upstream = str(body.get("upstream_base_url", config.UPSTREAM_BASE_URL)).strip().rstrip("/")
    parsed = urlparse(upstream)
    if not (1 <= listen_port <= 65535):
        return JSONResponse(status_code=400, content={"detail": "端口必须在 1 到 65535 之间"})
    if not (1 <= cooldown <= 86400):
        return JSONResponse(status_code=400, content={"detail": "冷却时间必须在 1 到 86400 秒之间"})
    if not isinstance(model_check_enabled, bool):
        return JSONResponse(status_code=400, content={"detail": "定时检测开关格式不正确"})
    if not (1 <= model_check_interval <= 10080):
        return JSONResponse(status_code=400, content={"detail": "定时检测间隔必须在 1 到 10080 分钟之间"})
    if system_prompt_mode not in {"passthrough", "prepend", "replace"}:
        return JSONResponse(status_code=400, content={"detail": "系统预设策略不正确"})
    if len(system_prompt) > 20000:
        return JSONResponse(status_code=400, content={"detail": "系统预设不能超过 20000 个字符"})
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return JSONResponse(status_code=400, content={"detail": "上游地址必须是有效的 HTTP(S) URL"})

    old_port = config.LISTEN_PORT
    values = {
        "listen_port": listen_port,
        "cooldown_seconds": cooldown,
        "upstream_base_url": upstream,
        "model_check_enabled": model_check_enabled,
        "model_check_interval_minutes": model_check_interval,
        "system_prompt_mode": system_prompt_mode,
        "system_prompt": system_prompt,
    }
    password = str(body.get("admin_password") or "")
    if password:
        if len(password) < 8:
            return JSONResponse(status_code=400, content={"detail": "管理密码至少需要 8 个字符"})
        values["admin_password"] = password
    config.update_settings(values)
    reset_model_check_schedule()

    response = JSONResponse({"ok": True, "restart_required": listen_port != old_port})
    if password:
        response.delete_cookie(SESSION_COOKIE, path="/")
    return response
