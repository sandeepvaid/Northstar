"""Campaign Data Hub API.

Run: uvicorn app.api.main:app --reload   (from the backend/ directory)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import deliveries, ingest, metrics

app = FastAPI(title="Campaign Data Hub", version="0.1.0")

# Allow the Vite dev server to call the API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics.router)
app.include_router(deliveries.router)
app.include_router(ingest.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
