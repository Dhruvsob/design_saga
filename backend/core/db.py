"""Mongo client (single instance shared across the app)."""
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import os

# Ensure env is loaded when this module is imported first
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

client = AsyncIOMotorClient(_mongo_url)
db = client[_db_name]
