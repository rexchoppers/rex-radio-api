import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager
from typing import List

from beanie import init_beanie
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from pymongo import AsyncMongoClient
from redis import asyncio as aioredis
from fastapi.responses import JSONResponse

from logger import init_logger
from models.configuration import Configuration
from requests.update_configuration_request import UpdateConfigurationRequest

logger = init_logger("rex-radio.daemon.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting API server")

    logger.info("🔌 Loading .env")
    load_dotenv()
    logger.info("✅ .env loaded")

    # MongoDB
    logger.info("🔌 Loading MongoDB")
    mongodb_uri = os.getenv("MONGO_URI", "")

    client = AsyncMongoClient(mongodb_uri)
    db = client["rex_radio"]
    await init_beanie(database=db, document_models=[Configuration])

    app.state.mongo_client = client
    logger.info("✅ MongoDB connected")

    # Redis
    logger.info("🔌 Loading Redis")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(redis_url, decode_responses=True)
    app.state.redis = redis
    logger.info("✅ Redis connected")

    yield

    client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def read_root():
    print(Configuration.find_all())
    return {"Hello": "World"}

@app.get("/config/{field}")
async def read_configuration(field: str):
    config = await Configuration.find_one(Configuration.field == field)
    if config:
        return JSONResponse(
            {
                "field": config.field,
                "value": config.value
            },
            status_code=200
        )
    else:
        return JSONResponse(
            {
                "error": "Configuration not found"
            },
            status_code=400
        )


@app.patch("/config")
async def update_configuration(updates: List[UpdateConfigurationRequest]):
    try:
        for update in updates:
            existing = await Configuration.find_one(Configuration.field == update.field)
            if existing:
                await existing.set({Configuration.value: update.value})
            else:
                await Configuration(field=update.field, value=update.value).insert()

        return {"status": "ok"}

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def verify_signature(method: str, path: str, body: bytes, timestamp: str, signature: str, secret: bytes) -> bool:
    try:
        # Reject timestamps older/newer than 5 minutes
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except ValueError:
        return False

    # Build message in a consistent format
    message = f"{timestamp}{method}{path}".encode() + body

    # Generate expected HMAC
    expected_sig = hmac.new(secret, message, hashlib.sha512).hexdigest()

    # Constant-time compare to avoid timing attacks
    return hmac.compare_digest(expected_sig, signature)

@app.middleware("http")
async def hmac_auth(request: Request, call_next):
    # Skip authentication for root or docs endpoints
    if request.url.path in ["/", "/docs", "/openapi.json"]:
        return await call_next(request)

    signature = request.headers.get("x-signature")
    timestamp = request.headers.get("x-timestamp")

    if not signature or not timestamp:
        return JSONResponse(
            {"error": "Missing signature or timestamp"},
            status_code=401
        )

    method = request.method.upper()
    path = request.url.path

    # Only read body for non-GET requests
    body = b""
    if method not in ("GET", "HEAD", "DELETE"):
        body = await request.body()

    # Verify signature
    secret = getattr(request.app.state, "hmac_secret", None)
    if not secret:
        return JSONResponse({"error": "Server misconfiguration (missing HMAC secret)"}, status_code=500)

    if not verify_signature(method, path, body, timestamp, signature, secret):
        return JSONResponse(
            {"error": "Invalid or expired signature"},
            status_code=401
        )

    return await call_next(request)