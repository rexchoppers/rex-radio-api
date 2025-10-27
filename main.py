import os
from contextlib import asynccontextmanager

from beanie import init_beanie
from dotenv import load_dotenv
from fastapi import FastAPI
from pymongo import AsyncMongoClient

from models.configuration import Configuration

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    mongodb_uri = os.getenv("MONGO_URI", "")

    client = AsyncMongoClient(mongodb_uri)
    db = client["mydatabase"]
    await init_beanie(database=db, document_models=[Configuration])

    app.state.mongo_client = client

    yield

    client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def read_root():
    print(Configuration.find_all())
    return {"Hello": "World"}