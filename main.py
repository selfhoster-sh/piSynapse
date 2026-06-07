import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat
from memory import init_db
from embedding import get_model as _warm_up_embedding
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piSynapse")

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("⏳ Initializing system, warming up semantic memory engine...")
    await asyncio.to_thread(_warm_up_embedding)
    yield
    logger.info("🛑 piSynapse shutting down...")

app = FastAPI(title="piSynapse", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
