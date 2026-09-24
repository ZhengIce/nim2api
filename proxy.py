import json
import time
from collections import deque

import aiosqlite
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

import config
import db
from pool import pool

router = APIRouter()

HOP_HEADERS = {"host", "content-length", "connection", "authorization"}
RETRYABLE_STATUSES = {401, 403, 429}


async def _load_enabled_tokens():
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute("SELECT token FROM gateway_tokens WHERE enabled = 1")
        return {r[0] for r in await cur.fetchall()}


async def _check_auth(request: Request):
    tokens = await _load_enabled_tokens()
    if not tokens:
        return None
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and auth[7:] in tokens:
        return None
    return JSONResponse(
        status_code=401,
        content={"error": {"message": "invalid gateway token"}},
    )


async def _model_is_disabled(model_id: str):
    if not model_id:
        return False
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute("SELECT enabled FROM models WHERE id = ?", (model_id,))
        row = await cur.fetchone()
    return row is not None and not bool(row[0])


async def _managed_models():
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        count = (await (await conn.execute("SELECT COUNT(*) FROM models")).fetchone())[0]
        if not count:
            return None
        cur = await conn.execute(
            "SELECT id, owned_by, created_at FROM models WHERE enabled = 1 ORDER BY id"
        )
        rows = await cur.fetchall()
    return {
        "object": "list",
        "data": [
            {
                "id": row["id"],
                "object": "model",
                "created": int(row["created_at"] or 0),
                "owned_by": row["owned_by"] or "nvidia",
            }
            for row in rows
        ],
    }


def _extract_usage_from_sse(chunks: list[str]):
    for raw in reversed(chunks):
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage") or (obj.get("response") or {}).get("usage")
            if usage:
                return _usage_counts(usage)
    return 0, 0


def _usage_counts(usage):
    return (
        usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0,
        usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0,
    )


def _response_headers(response):
    headers = {}
    for name, value in response.headers.items():
        lowered = name.lower()
        if (
            lowered in {"x-request-id", "retry-after", "openai-processing-ms"}
            or lowered.startswith("x-ratelimit-")
        ):
            headers[name] = value
    return headers


def _apply_system_preset(payload, endpoint):
    prompt = config.SYSTEM_PROMPT.strip()
    mode = config.SYSTEM_PROMPT_MODE
    if not prompt or mode == "passthrough":
        return payload

    if endpoint == "chat/completions":
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return payload
        if mode == "replace":
            messages = [
                message for message in messages
                if not isinstance(message, dict)
                or message.get("role") not in {"system", "developer"}
            ]
        payload["messages"] = [{"role": "system", "content": prompt}, *messages]
    elif endpoint == "responses":
        current = payload.get("instructions")
        if mode == "prepend" and isinstance(current, str) and current.strip():
            payload["instructions"] = f"{prompt}\n\n{current}"
        else:
            payload["instructions"] = prompt
    return payload


def _retryable(status_code):
    return status_code in RETRYABLE_STATUSES or status_code >= 500


async def _proxy_post(request: Request, endpoint: str, supports_stream=False):
    auth_err = await _check_auth(request)
    if auth_err is not None:
        return auth_err

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": {"message": "invalid json"}})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": {"message": "json object required"}})
    payload = _apply_system_preset(payload, endpoint)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    model = payload.get("model", "")
    stream = supports_stream and bool(payload.get("stream"))
    if await _model_is_disabled(model):
        return JSONResponse(
            status_code=403,
            content={"error": {"message": f"model '{model}' is disabled by gateway policy"}},
        )

    keys = await pool.acquire()
    if not keys:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "all keys cooling down or pool empty"}},
        )

    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS
    }
    url = f"{config.UPSTREAM_BASE_URL}/{endpoint}"

    last_error = None
    for key in keys:
        headers["Authorization"] = f"Bearer {key['api_key']}"
        started = time.time()
        try:
            if stream:
                result, retry_error = await _try_stream(key, model, url, headers, body, started)
                if result is not None:
                    return result
                if retry_error is not None:
                    last_error = retry_error
                continue
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, headers=headers, content=body)
            latency_ms = int((time.time() - started) * 1000)
        except httpx.HTTPError:
            await pool.on_rate_limited(key["id"])
            continue

        if _retryable(resp.status_code):
            await pool.on_rate_limited(key["id"])
            await db.log_request(key["id"], model, resp.status_code, 0, 0, latency_ms)
            last_error = JSONResponse(
                status_code=resp.status_code,
                content=_safe_json(resp),
                headers=_response_headers(resp),
            )
            continue
        if resp.status_code >= 400:
            await pool.on_failure(key["id"])
            await db.log_request(key["id"], model, resp.status_code, 0, 0, latency_ms)
            return JSONResponse(
                status_code=resp.status_code,
                content=_safe_json(resp),
                headers=_response_headers(resp),
            )

        prompt_tokens, completion_tokens = 0, 0
        try:
            data = resp.json()
            usage = data.get("usage") or {}
            prompt_tokens, completion_tokens = _usage_counts(usage)
        except Exception:
            data = None
        await pool.on_success(key["id"], prompt_tokens, completion_tokens)
        await db.log_request(
            key["id"], model, resp.status_code, prompt_tokens, completion_tokens, latency_ms
        )
        if data is not None:
            return JSONResponse(
                status_code=resp.status_code,
                content=data,
                headers=_response_headers(resp),
            )
        return JSONResponse(status_code=502, content={"error": {"message": "bad upstream response"}})

    if last_error is not None:
        return last_error
    return JSONResponse(
        status_code=503,
        content={"error": {"message": "all keys cooling down or pool empty"}},
    )


async def _try_stream(key, model, url, headers, body, started):
    """Return (response, retry_error); response is None when another key should be tried."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30))
    try:
        req = client.build_request("POST", url, headers=headers, content=body)
        resp = await client.send(req, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        await pool.on_rate_limited(key["id"])
        return None, None

    if _retryable(resp.status_code):
        latency_ms = int((time.time() - started) * 1000)
        content = await resp.aread()
        await resp.aclose()
        await client.aclose()
        await pool.on_rate_limited(key["id"])
        await db.log_request(key["id"], model, resp.status_code, 0, 0, latency_ms)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"error": {"message": content.decode(errors="replace")}}
        return None, JSONResponse(
            status_code=resp.status_code,
            content=parsed,
            headers=_response_headers(resp),
        )
    if resp.status_code >= 400:
        latency_ms = int((time.time() - started) * 1000)
        content = await resp.aread()
        await resp.aclose()
        await client.aclose()
        await pool.on_failure(key["id"])
        await db.log_request(key["id"], model, resp.status_code, 0, 0, latency_ms)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"error": {"message": content.decode(errors="replace")}}
        return JSONResponse(
            status_code=resp.status_code,
            content=parsed,
            headers=_response_headers(resp),
        ), None

    async def gen():
        chunks = deque(maxlen=100)
        prompt_tokens = completion_tokens = 0
        try:
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
                yield chunk
        finally:
            latency_ms = int((time.time() - started) * 1000)
            prompt_tokens, completion_tokens = _extract_usage_from_sse(list(chunks))
            await pool.on_success(key["id"], prompt_tokens, completion_tokens)
            await db.log_request(
                key["id"], model, 200, prompt_tokens, completion_tokens, latency_ms
            )
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers=_response_headers(resp),
    ), None


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await _proxy_post(request, "chat/completions", supports_stream=True)


@router.post("/v1/responses")
async def responses(request: Request):
    return await _proxy_post(request, "responses", supports_stream=True)


@router.post("/v1/completions")
async def completions(request: Request):
    return await _proxy_post(request, "completions", supports_stream=True)


@router.post("/v1/embeddings")
async def embeddings(request: Request):
    return await _proxy_post(request, "embeddings")


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": {"message": resp.text}}


@router.get("/v1/models")
async def list_models(request: Request):
    auth_err = await _check_auth(request)
    if auth_err is not None:
        return auth_err
    managed = await _managed_models()
    if managed is not None:
        return managed
    keys = await pool.acquire()
    if not keys:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "all keys cooling down or pool empty"}},
        )
    async with httpx.AsyncClient(timeout=30) as client:
        for key in keys:
            try:
                resp = await client.get(
                    f"{config.UPSTREAM_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {key['api_key']}"},
                )
            except httpx.HTTPError:
                await pool.on_rate_limited(key["id"])
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                await pool.on_rate_limited(key["id"])
                continue
            return JSONResponse(status_code=resp.status_code, content=_safe_json(resp))
    return JSONResponse(
        status_code=503,
        content={"error": {"message": "all keys cooling down or pool empty"}},
    )
