"""
Keep-alive pinger — prevents Render free tier cold starts.
Pings the /health endpoint every 14 minutes so the server never spins down.
Run this as a background thread started from main.py lifespan.
"""

import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)

SELF_URL = os.getenv("RENDER_EXTERNAL_URL", "")
INTERVAL = 14 * 60  # 14 minutes


async def _ping():
    if not SELF_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SELF_URL}/health")
            logger.info(f"Keep-alive ping → {r.status_code}")
    except Exception as e:
        logger.warning(f"Keep-alive ping failed: {e}")


async def start_keep_alive():
    if not SELF_URL:
        logger.info("RENDER_EXTERNAL_URL not set — keep-alive disabled")
        return
    logger.info(f"Keep-alive started, pinging {SELF_URL}/health every {INTERVAL//60} min")
    while True:
        await asyncio.sleep(INTERVAL)
        await _ping()
