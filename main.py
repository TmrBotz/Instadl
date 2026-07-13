"""
main.py — Entry point
FastAPI (uvicorn) + Pyrogram bot ek saath run hote hain.
"""

import asyncio
import logging
import uvicorn

# Python 3.10+ fix — event loop pehle set karo
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from config import Config
from api import api
from bot import bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Main")


async def run_api():
    config = uvicorn.Config(
        app=api,
        host="0.0.0.0",
        port=Config.PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot():
    await bot.start()
    logger.info("✅ Bot started")
    await asyncio.Event().wait()


async def main():
    logger.info("🚀 Starting Insta Reel Downloader — API + Bot")
    await asyncio.gather(
        run_api(),
        run_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
