from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# --- Constants for ASF ---
ASF_COOKIE_URL = "https://sentinel1.asf.alaska.edu/METADATA_RAW/SA/S1A_IW_RAW__0SSV_20141229T072718_20141229T072750_003931_004B96_B79F.iso.xml"
ASF_TOKEN_ENV = "EARTHDATA_TOKEN"


class URLHandler:
    """Base class/Interface for URL handlers."""

    def can_handle(self, url: str) -> bool:
        """Check if this handler supports the given URL."""
        return False

    async def prepare(self, client: Any, engine: str) -> dict[str, str]:
        """Perform pre-download actions (e.g., cookie priming) and return extra headers.

        Args:
            client: The async client (httpx.AsyncClient or aiohttp.ClientSession)
            engine: The engine name ("httpx" or "aiohttp")

        Returns:
            dict: Extra headers to be added to the request

        """
        return {}


class ASFHandler(URLHandler):
    """Handler for Alaska Satellite Facility (ASF) URLs.

    Implements:
    1. Bearer Token Authentication (if EARTHDATA_TOKEN is set)
    2. Cookie Priming (if Netrc usage is inferred)
    """

    def can_handle(self, url: str) -> bool:
        return "asf.alaska.edu" in urlparse(url).netloc

    async def prepare(self, client: Any, engine: str) -> dict[str, str]:
        headers = {}
        token = os.getenv(ASF_TOKEN_ENV)

        if token:
            # Case 1: Bearer Token Present - Use it
            logger.debug("ASF Handler: Using Bearer Token")
            headers["Authorization"] = f"Bearer {token}"
        else:
            # Case 2: No Token (Netrc) - Prime Cookies
            # Note: This request primes the cookies in the client's cookie jar
            logger.debug("ASF Handler: Priming Cookies")
            try:
                if engine == "httpx":
                    await client.get(ASF_COOKIE_URL, follow_redirects=True)
                elif engine == "aiohttp":
                    async with client.get(ASF_COOKIE_URL, allow_redirects=True) as r:
                        r.raise_for_status()
            except Exception as e:
                logger.warning(
                    "ASF Handler: Cookie priming failed: %s. Download may fail if using Netrc.",
                    e,
                )

        return headers


# Registry of active handlers
HANDLERS: list[URLHandler] = [ASFHandler()]


async def process_url_handlers(url: str, client: Any, engine: str) -> dict[str, str]:
    """Execute matching handlers and aggregate headers.

    Args:
        url: The target URL
        client: The async client
        engine: The engine name

    Returns:
        dict: Combined extra headers from all matching handlers

    """
    final_headers = {}
    for handler in HANDLERS:
        if handler.can_handle(url):
            try:
                headers = await handler.prepare(client, engine)
                final_headers.update(headers)
            except Exception as e:
                logger.error(f"Handler {handler.__class__.__name__} failed: {e}")

    return final_headers
