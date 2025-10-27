import os
from contextlib import asynccontextmanager
from typing import List

from beanie import init_beanie
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from pymongo import AsyncMongoClient

from models.configuration import Configuration
from requests.update_configuration_request import UpdateConfigurationRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    mongodb_uri = os.getenv("MONGO_URI", "")

    client = AsyncMongoClient(mongodb_uri)
    db = client["rex_radio"]
    await init_beanie(database=db, document_models=[Configuration])

    app.state.mongo_client = client

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