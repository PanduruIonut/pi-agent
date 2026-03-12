"""
FastAPI web API interface for the Pi agent.

Endpoints:
  POST /ask        — ask the agent anything (JSON body: {"prompt": "..."})
  GET  /status     — quick system status report
  GET  /docker     — Docker container report
  GET  /health     — liveness check (no auth required)

All endpoints (except /health) require the header:
  X-API-Key: <your API_KEY from .env>
"""

import os
import logging
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from agent import ask

logger = logging.getLogger(__name__)

app = FastAPI(title="Pi Agent API", version="1.0")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(key: str = Security(api_key_header)):
    expected = os.getenv("API_KEY", "")
    if not expected:
        raise HTTPException(500, "API_KEY not configured on server")
    if key != expected:
        raise HTTPException(403, "Invalid or missing X-API-Key header")
    return key


class AskRequest(BaseModel):
    prompt: str


class AskResponse(BaseModel):
    response: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_auth)])
async def ask_endpoint(body: AskRequest):
    if not body.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    try:
        response = await ask(body.prompt)
        return AskResponse(response=response)
    except Exception as e:
        logger.exception("Agent error")
        raise HTTPException(500, str(e))


@app.get("/status", response_model=AskResponse, dependencies=[Depends(require_auth)])
async def status_endpoint():
    response = await ask(
        "Give me a full system status report: system info, resource usage, and any issues."
    )
    return AskResponse(response=response)


@app.get("/docker", response_model=AskResponse, dependencies=[Depends(require_auth)])
async def docker_endpoint():
    response = await ask(
        "Check all Docker containers. Report their status, resource usage, "
        "and flag any that are stopped or unhealthy."
    )
    return AskResponse(response=response)
