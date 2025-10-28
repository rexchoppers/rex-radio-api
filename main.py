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

def verify_signature(body: bytes, timestamp: str, signature: str, secret: bytes) -> bool:
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except ValueError:
        return False

    msg = timestamp.encode() + body
    expected_sig = hmac.new(secret, msg, hashlib.sha512).hexdigest()

    return hmac.compare_digest(expected_sig, signature)

@app.middleware("http")
async def hmac_auth(request: Request, call_next):
    if request.url.path == "/":
        return await call_next(request)

    signature = request.headers.get("x-signature")
    timestamp = request.headers.get("x-timestamp")

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature or timestamp")

    body = await request.body()

    if not verify_signature(body, timestamp, signature, request.app.state.hmac_secret):
        raise HTTPException(status_code=401, detail="Invalid or expired signature")

    return await call_next(request)