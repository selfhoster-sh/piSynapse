import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat
from memory import init_db
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piSynapse")

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically initialize the database schema on startup
    await init_db()
    
    # Warm up the FastEmbed model in a thread pool to avoid lag on the first user request
    logger.info("⏳ Initializing system, warming up semantic memory engine...")
    await asyncio.to_thread(lambda: __import__("embedding").get_model())
    
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
