import base64
import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from beanie import init_beanie
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from pymongo import AsyncMongoClient
from redis import asyncio as aioredis
from fastapi.responses import JSONResponse

from logger import init_logger
from models.configuration import Configuration
from models.presenter import Presenter, ScheduleSlot
from requests.update_configuration_request import UpdateConfigurationRequest
from requests.presenter_requests import CreatePresenterRequest, UpdatePresenterRequest

logger = init_logger("rex-radio.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting API server")

    logger.info("🔌 Loading .env")
    load_dotenv()
    logger.info("✅ .env loaded")

    logger.info("🔌 Loading HMAC secret")
    app.state.hmac_secret = os.getenv("HMAC_SECRET", "default_secret").encode()
    logger.info("✅ HMAC secret loaded")

    # MongoDB
    logger.info("🔌 Loading MongoDB")
    mongodb_uri = os.getenv("MONGO_URI", "")

    client = AsyncMongoClient(mongodb_uri)
    db = client["rex_radio"]
    await init_beanie(database=db, document_models=[Configuration, Presenter])

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
async def read_configuration(field: Literal["name", "description", "genres"]):
    config = await Configuration.find_one(Configuration.field == field)

    if not config:
        return JSONResponse(
            {
                "field": field,
                "value": None
            },
            status_code=200
        )

    return JSONResponse(
        {
            "field": config.field,
            "value": config.value
        },
        status_code=200
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

        return JSONResponse(
            {},
            status_code=200
        )

        return {"status": "ok"}

    except ValidationError as e:
        print(e.errors())
        raise HTTPException(status_code=400, detail=e.errors())

    except Exception as e:
        print(e)
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

    # Generate expected HMAC (Base64, to match your bash)
    digest = hmac.new(secret, message, hashlib.sha512).digest()
    expected_sig = base64.b64encode(digest).decode()

    # Compare
    return hmac.compare_digest(expected_sig, signature)

# @app.middleware("http")
async def hmac_auth(request: Request, call_next):
    # Skip authentication for root or docs endpoints
    if request.url.path in ["/", "/docs", "/openapi.json"]:
        return await call_next(request)

    signature = request.headers.get("x-signature")
    timestamp = request.headers.get("x-timestamp")

    print(f"Signature: {signature}")
    print(f"Timestamp: {timestamp}")

    if not signature or not timestamp:
        print("Missing signature or timestamp")
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
        print("Invalid or expired signature")
        return JSONResponse(
            {"error": "Invalid or expired signature"},
            status_code=401
        )

    return await call_next(request)


@app.post("/presenters")
async def create_presenter(payload: CreatePresenterRequest):
    try:
        presenter = Presenter(
            name=payload.name,
            voice_id=payload.voice_id,
            model_id=payload.model_id,
            schedules=payload.schedules,
        )
        await presenter.insert()
        return presenter
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/presenters")
async def list_presenters():
    items = await Presenter.find_all().to_list()
    return items


@app.get("/presenters/{presenter_id}")
async def get_presenter(presenter_id: str):
    presenter = await Presenter.get(presenter_id)
    if not presenter:
        raise HTTPException(status_code=404, detail="Presenter not found")
    return presenter


@app.patch("/presenters/{presenter_id}")
async def update_presenter(presenter_id: str, payload: UpdatePresenterRequest):
    presenter = await Presenter.get(presenter_id)
    if not presenter:
        raise HTTPException(status_code=404, detail="Presenter not found")

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(presenter, k, v)

    try:
        await presenter.save()
        return presenter
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/presenters/{presenter_id}")
async def delete_presenter(presenter_id: str):
    presenter = await Presenter.get(presenter_id)
    if not presenter:
        raise HTTPException(status_code=404, detail="Presenter not found")
    await presenter.delete()
    return JSONResponse({}, status_code=204)