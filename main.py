import asyncio
import contextlib
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import db
from admin import model_check_scheduler, router as admin_router
from proxy import router as proxy_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="NVIDIA NIM Gateway", docs_url="/swagger", redoc_url=None)
model_check_task = None


@app.on_event("startup")
async def startup():
    global model_check_task
    os.makedirs(config.DATA_DIR, exist_ok=True)
    await db.init_db()
    model_check_task = asyncio.create_task(model_check_scheduler())


@app.on_event("shutdown")
async def shutdown():
    global model_check_task
    if model_check_task is not None:
        model_check_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await model_check_task
        model_check_task = None


app.include_router(proxy_router)
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}


@app.get("/")
@app.get("/login")
@app.get("/overview")
@app.get("/checks")
@app.get("/models")
@app.get("/keys")
@app.get("/tokens")
@app.get("/settings")
@app.get("/docs")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.LISTEN_PORT)
