
import asyncio
import os
from unittest import mock
import pytest
from data_downloader.url_handlers import ASFHandler, process_url_handlers, ASF_COOKIE_URL

@pytest.mark.asyncio
async def test_asf_handler_token():
    """Verify ASFHandler uses token if available."""
    handler = ASFHandler()
    
    with mock.patch.dict(os.environ, {"EARTHDATA_TOKEN": "fake_token"}):
        headers = await handler.prepare(mock.AsyncMock(), "httpx")
        assert headers["Authorization"] == "Bearer fake_token"

@pytest.mark.asyncio
async def test_asf_handler_netrc_httpx():
    """Verify ASFHandler primes cookies for partial netrc auth (httpx)."""
    handler = ASFHandler()
    mock_client = mock.AsyncMock()
    
    with mock.patch.dict(os.environ, {}, clear=True):
        await handler.prepare(mock_client, "httpx")
        
    mock_client.get.assert_called_with(ASF_COOKIE_URL, follow_redirects=True)

@pytest.mark.asyncio
async def test_asf_handler_netrc_aiohttp():
    """Verify ASFHandler primes cookies for partial netrc auth (aiohttp)."""
    handler = ASFHandler()
    mock_client = mock.AsyncMock()
    
    # Mock context manager for aiohttp.get
    mock_response = mock.Mock()
    mock_response.raise_for_status = mock.Mock()
    
    mock_client.get.return_value.__aenter__.return_value = mock_response
    
    with mock.patch.dict(os.environ, {}, clear=True):
        await handler.prepare(mock_client, "aiohttp")
        
    mock_client.get.assert_called_with(ASF_COOKIE_URL, allow_redirects=True)

@pytest.mark.asyncio
async def test_process_url_handlers_match():
    """Verify process_url_handlers calls the correct handler."""
    url = "https://sentinel1.asf.alaska.edu/foo/bar"
    mock_client = mock.AsyncMock()
    
    with mock.patch.dict(os.environ, {"EARTHDATA_TOKEN": "token"}):
        headers = await process_url_handlers(url, mock_client, "httpx")
        assert headers["Authorization"] == "Bearer token"

@pytest.mark.asyncio
async def test_process_url_handlers_no_match():
    """Verify process_url_handlers does nothing for non-matching URLs."""
    url = "https://google.com"
    mock_client = mock.AsyncMock()
    
    headers = await process_url_handlers(url, mock_client, "httpx")
    assert headers == {}
