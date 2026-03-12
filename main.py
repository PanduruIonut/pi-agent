#!/usr/bin/env python3
"""
Entry point — runs the Telegram bot and FastAPI web server concurrently.
"""

import asyncio
import logging
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_api():
    from api import app
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "9000"))
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("Starting web API on %s:%s", host, port)
    try:
        await server.serve()
    except (OSError, SystemExit) as e:
        logger.error("Web API failed to start: %s — bot will continue running", e)


async def run_bot():
    from bot import build_app
    app = build_app()
    logger.info("Starting Telegram bot")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()  # run forever
        await app.updater.stop()
        await app.stop()


async def main():
    tasks = []

    if os.getenv("TELEGRAM_BOT_TOKEN"):
        tasks.append(asyncio.create_task(run_bot()))
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")

    tasks.append(asyncio.create_task(run_api()))

    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down")
        for t in tasks:
            t.cancel()


if __name__ == "__main__":
    asyncio.run(main())
