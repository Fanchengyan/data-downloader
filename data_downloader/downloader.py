"""Main downloader module."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import random
import selectors
import time
from enum import Enum
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Any, Literal, NamedTuple
from urllib.parse import urlparse

import aiohttp
import browser_cookie3 as bc
import httpx
import requests
from dateutil.parser import parse
from tqdm import tqdm

from ._chunked_download import (
    _detect_and_resume_download,
    _download_data_chunked_aiohttp,
    _download_data_chunked_httpx,
)
from ._metadata import _ChunkedDownloadMetadata
from .logging import setup_logger, tqdm_handler
from .netrc import Netrc
from .url_handlers import process_url_handlers
from .utils.tools import safe_repr

if TYPE_CHECKING:
    from collections.abc import Iterable
    from http.cookiejar import CookieJar


logger = setup_logger(__name__, handler=tqdm_handler)


class DownloadAction(Enum):
    """Action to take after HTTP status check.

    Attributes
    ----------
    PROCEED : str
        Continue with download (200/206 status, ready to download)
    COMPLETED : str
        File already downloaded completely, skip download
    RETRY : str
        Retryable error occurred (202, 408, 429, 5xx), should retry
    REDIRECT : str
        HTTP redirect (301/302), follow to new URL
    FAIL : str
        Permanent failure (401, 403, 404, etc.), abort download

    """

    PROCEED = "proceed"
    COMPLETED = "completed"
    RETRY = "retry"
    REDIRECT = "redirect"
    FAIL = "fail"


class StatusResult(NamedTuple):
    """Result of HTTP status check.

    Parameters
    ----------
    action : DownloadAction
        Action to take based on HTTP status
    extra : str | int | None
        Additional context:
        - For REDIRECT: new URL (str)
        - For RETRY: HTTP status code (int)
        - For others: None

    Examples
    --------
    >>> # File already downloaded
    >>> StatusResult(DownloadAction.COMPLETED)
    StatusResult(action=<DownloadAction.COMPLETED: 'completed'>, extra=None)

    >>> # Need to retry due to 429
    >>> StatusResult(DownloadAction.RETRY, 429)
    StatusResult(action=<DownloadAction.RETRY: 'retry'>, extra=429)

    >>> # Redirect to new URL
    >>> StatusResult(DownloadAction.REDIRECT, "https://new-url.com/file")
    StatusResult(action=<DownloadAction.REDIRECT: 'redirect'>, extra='https://new-url.com/file')

    """

    action: DownloadAction
    extra: str | int | None = None


# Retryable HTTP status codes (transient errors)
RETRYABLE_STATUS_CODES = {
    202: "Accepted (data being prepared)",
    408: "Request Timeout",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}

def _extract_checksum_from_headers(headers: Any) -> dict[str, Any] | None:
    """Extract checksum information from HTTP response headers.

    Parameters
    ----------
    headers : dict-like
        HTTP response headers

    Returns
    -------
    dict | None
        {"type": "md5|sha256|etag", "value": "...", "reliable": bool}
        or None if no checksum found

    """
    import base64

    # 1. Content-MD5 (most reliable, but rare)
    if "content-md5" in headers:
        try:
            md5_b64 = headers["content-md5"]
            md5_hex = base64.b64decode(md5_b64).hex()
            return {"type": "md5", "value": md5_hex, "reliable": True}  # noqa: TRY300
        except Exception:
            pass

    # 2. Digest header (RFC 3230)
    if "digest" in headers:
        digest = headers["digest"]
        if "SHA-256=" in digest:
            try:
                hash_b64 = digest.split("SHA-256=")[1].split(",")[0]
                hash_hex = base64.b64decode(hash_b64).hex()
                return {"type": "sha256", "value": hash_hex, "reliable": True}  # noqa: TRY300
            except Exception:
                pass

    # 3. AWS S3 metadata
    if "x-amz-meta-md5" in headers:
        return {"type": "md5", "value": headers["x-amz-meta-md5"], "reliable": True}

    # 4. Custom checksum headers
    for key, value in headers.items():
        if key.lower().startswith("x-checksum-"):
            algo = key.lower().replace("x-checksum-", "")
            return {"type": algo, "value": value, "reliable": True}

    # 5. ETag (unreliable, may not be actual hash)
    if "etag" in headers:
        etag = headers["etag"].strip('"')
        return {"type": "etag", "value": etag, "reliable": False}

    return None


def _verify_file_checksum(
    file_path: Path,
    checksum_info: dict[str, Any] | None,
    verify_unreliable: bool = False,
) -> bool:
    """Verify file integrity using checksum.

    Parameters
    ----------
    file_path : Path
        File to verify
    checksum_info : dict | None
        Checksum information from headers
    verify_unreliable : bool
        Whether to verify unreliable checksums (e.g., ETag)

    Returns
    -------
    bool
        True if verification passed or no checksum available,
        False if verification failed

    """
    import hashlib

    if not checksum_info:
        logger.debug("No checksum available for verification")
        return True

    # Skip unreliable checksums unless explicitly requested
    if not checksum_info["reliable"] and not verify_unreliable:
        logger.info(
            "Skipping unreliable checksum verification (%s)", checksum_info["type"]
        )
        return True

    algo = checksum_info["type"]
    expected = checksum_info["value"].lower()

    # Select hash algorithm
    if algo == "md5":
        hasher = hashlib.md5()
    elif algo == "sha256":
        hasher = hashlib.sha256()
    elif algo == "sha1":
        hasher = hashlib.sha1()
    elif algo == "etag":
        # ETag might be MD5, try it
        hasher = hashlib.md5()
    else:
        logger.warning("Unsupported checksum algorithm: %s", algo)
        return True

    # Calculate file hash (chunk by chunk to avoid memory issues)
    try:
        with Path(file_path).open("rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)

        actual = hasher.hexdigest()

        if actual == expected:
            logger.info("✓ Checksum verification passed (%s)", algo)
            return True

        logger.error(
            "✗ Checksum verification FAILED!\n"
            "  Algorithm: %s\n"
            "  Expected:  %s\n"
            "  Actual:    %s\n"
            "  File may be corrupted: %s",
            algo,
            expected,
            actual,
            file_path.name,
        )
        return False  # noqa: TRY300
    except Exception:
        logger.exception("Error during checksum verification: %s")
        return False


async def _download_checksum_file(
    client: Any, checksum_url: str, timeout: int = 30
) -> dict[str, Any] | None:
    """Download and parse external checksum file.

    Parameters
    ----------
    client : httpx.AsyncClient or aiohttp.ClientSession
        HTTP client
    checksum_url : str
        URL to checksum file (e.g., .md5, .sha256)
    timeout : int
        Request timeout in seconds

    Returns
    -------
    dict | None
        {"type": "md5|sha256", "value": "..."} or None if failed

    """
    try:
        # Determine algorithm from URL
        if checksum_url.endswith(".md5"):
            algo = "md5"
        elif checksum_url.endswith(".sha256"):
            algo = "sha256"
        elif checksum_url.endswith(".sha1"):
            algo = "sha1"
        else:
            logger.warning("Unknown checksum file format: %s", checksum_url)
            return None

        # Download checksum file
        if isinstance(client, httpx.AsyncClient):
            r = await client.get(checksum_url, timeout=timeout)
            content = r.text
        else:  # aiohttp
            async with client.get(checksum_url, timeout=timeout) as r:
                content = await r.text()

        # Parse checksum (format: "hash filename" or just "hash")
        checksum = content.strip().split()[0]

        return {"type": algo, "value": checksum, "reliable": True}  # noqa: TRY300

    except Exception as e:
        logger.debug("Failed to download checksum file %s: %s", checksum_url, e)
        return None


def _auto_detect_chunks(file_size: int) -> int:
    """Automatically determine optimal number of chunks based on file size.

    Parameters
    ----------
    file_size : int
        File size in bytes

    Returns
    -------
    int
        Recommended number of chunks

    Notes
    -----
    Strategy:
    - < 10 MB: 1 chunk (no splitting)
    - 10 MB - 100 MB: 4 chunks
    - 100 MB - 1 GB: 8 chunks
    - > 1 GB: 16 chunks

    """
    MB = 1024 * 1024  # noqa: N806
    GB = 1024 * MB  # noqa: N806

    if file_size < 10 * MB:
        return 1
    if file_size < 100 * MB:
        return 4
    if file_size < 1 * GB:
        return 8
    return 16


def _merge_chunks(file_path: Path, chunks: int) -> None:
    """Merge chunk files into final file.

    Parameters
    ----------
    file_path : Path
        Target file path
    chunks : int
        Number of chunks to merge

    Notes
    -----
    Merges files like filename.part0, filename.part1, ... into filename
    and deletes part files after successful merge.

    """
    logger.info("Merging %s chunks into %s...", chunks, file_path.name)

    with Path(file_path).open("wb") as target:
        for i in range(chunks):
            part_path = file_path.parent / f"{file_path.name}.part{i}"
            if not part_path.exists():
                msg = f"Missing part file: {part_path.name}"
                logger.error(msg)
                raise FileNotFoundError(msg)

            with Path(part_path).open("rb", encoding="utf-8") as part:
                target.write(part.read())

    # Delete part files after successful merge
    for i in range(chunks):
        part_path = file_path.parent / f"{file_path.name}.part{i}"
        part_path.unlink()

    logger.info("Successfully merged %s chunks", chunks)


def _get_retry_wait_time(response: Any, status_code: int) -> float:
    """Calculate wait time based on Retry-After header and status code.

    Parameters
    ----------
    response : HTTP response object
        Response object with headers
    status_code : int
        HTTP status code

    Returns
    -------
    float
        Wait time in seconds

    """
    # Try to read Retry-After header
    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            # Retry-After can be seconds
            wait_time = float(retry_after)
            logger.info("Server requested wait of %s seconds", wait_time)
            return min(wait_time, 60)  # Max 60 seconds
        except ValueError:
            # Retry-After can also be HTTP date format
            try:
                retry_date = parse(retry_after)
                now = dt.datetime.now(dt.timezone.utc)
                wait_time = (retry_date - now).total_seconds()
                wait_time = max(0, min(wait_time, 60))
                if wait_time > 0:
                    logger.info(
                        "Server requested wait until %s (%.1fs)", retry_after, wait_time
                    )
                return wait_time  # noqa: TRY300
            except Exception:
                pass  # Parse failed, use default

    # No Retry-After header, use default strategy
    if status_code == 429:  # Rate limiting
        return random.uniform(2, 10)
    # 202, 408, 5xx
    return random.uniform(0.5, 5)


def get_url_host(url: str) -> str:
    """Return the url host for a given url."""
    ri = urlparse(url)
    # Strip port numbers from netloc. This weird `if...encode`` dance is
    # used for Python 3.2, which doesn't support unicode literals.
    splitstr = b":"
    if isinstance(url, str):
        splitstr = splitstr.decode("ascii")
    return ri.netloc.split(splitstr)[0]


def get_netrc_auth(url: str) -> tuple[str, str] | None:
    """Return the Requests tuple auth for a given url from .netrc."""
    host = get_url_host(url)
    _netrc = Netrc().authenticators(host)

    if _netrc:
        # Return with login / password
        login_i = 0 if _netrc[0] else 1
        return (_netrc[login_i], _netrc[2])
    return None


def _parse_file_name(response: Any) -> str:
    """Parse the file_name from the headers of web response or url."""
    if "Content-disposition" in response.headers:
        file_name = (
            response
            .headers["Content-disposition"]
            .split("filename=")[1]
            .strip('"')
            .strip("'")
        )
    else:
        file_name = Path(urlparse(str(response.url)).path).name
    return file_name


def _unit_formater(size: float, suffix: str) -> str:
    prefixs = ["", "k", "M", "G", "T"]
    idx = 0
    while size / 1024 >= 1:
        size = size / 1024
        idx += 1
        if idx == 4:
            break

    return f"{size:.2f}{prefixs[idx]}{suffix}"


def _new_file_from_web(r: Any, file_path: str | Path) -> bool:
    """Whether have new file from the website."""
    try:
        if not Path(file_path).exists():
            return False
        time_remote = parse(r.headers.get("Last-Modified"))
        time_local = dt.datetime.fromtimestamp(
            Path(file_path).stat().st_mtime, dt.timezone.utc
        )
        return time_remote > time_local  # noqa: TRY300
    except Exception as e:
        params = {
            "message": "Error for _new_file_from_web",
            "url": file_path,
            "error": str(e),
        }
        msg = pformat(safe_repr(params), indent=4)
        logger.debug(msg)
        return False


def _get_cookiejar(authorize_from_browser: bool) -> CookieJar | None:
    cj = None
    if authorize_from_browser:
        try:
            cj = bc.load()
        except Exception as e:
            params = {
                "message": "Error for _get_cookiejar",
                "error": str(e),
                "info": "Could not load cookie from browser. "
                "Please login in website via browser before run this code\n  So far "
                "the following browsers are supported: Chrome,Firefox, Opera, Edge, "
                "Chromium",
            }
            msg = pformat(safe_repr(params), indent=4)
            logger.exception(msg)
    return cj


def _handle_status(
    r: Any, url: str, local_size: int, file_name: str | Path, file_path: str | Path
) -> StatusResult:
    """Check HTTP response status and determine download action.

    Parameters
    ----------
    r : Any
        HTTP response object (requests.Response, httpx.Response, or aiohttp.ClientResponse)
    url : str
        URL being downloaded
    local_size : int
        Size of existing local file (0 if not exists)
    file_name : str | Path
        Name of the file to download
    file_path : str | Path
        Full path where file will be saved

    Returns
    -------
    StatusResult
        Named tuple containing:
        - action: DownloadAction enum indicating what to do
        - extra: Additional data (redirect URL or status code)

    Notes
    -----
    This function sets global variables:
    - support_resume: bool - whether server supports resume
    - remote_size: int - total file size from server
    - pbar: tqdm - progress bar instance (for resumable downloads)

    Examples
    --------
    >>> # File already complete
    >>> result = _handle_status(response_206, url, 1000, "file.txt", "/tmp/file.txt")
    >>> result.action == DownloadAction.COMPLETED
    True

    >>> # Need to retry (429 Too Many Requests)
    >>> result = _handle_status(response_429, url, 0, "file.txt", "/tmp/file.txt")
    >>> result.action == DownloadAction.RETRY
    True
    >>> result.extra
    429

    """
    global support_resume, pbar, remote_size

    # Get status code - works with requests/httpx (.status_code) and aiohttp (.status)
    status_code = getattr(r, "status_code", None) or getattr(r, "status", None)

    if status_code is None:
        logger.error(
            "Unable to get status code from response object of type %s",
            type(r).__name__,
        )
        return StatusResult(DownloadAction.FAIL)

    if status_code in {206, 416}:
        support_resume = True
        remote_size = int(r.headers["Content-Range"].rsplit("/")[-1])

        # init process bar
        if _new_file_from_web(r, file_path):
            logger.info(
                "There is a new file from %s. %s is ready to be downloaded again",
                url,
                Path(file_name).name,
            )
            Path(file_path).unlink()
        elif local_size < remote_size:
            pbar = tqdm(
                initial=local_size,
                total=remote_size,
                unit="B",
                unit_scale=True,
                dynamic_ncols=True,
                desc=Path(file_name).name,
            )
        else:
            logger.info(
                "%s was downloaded entirely. skipping download", Path(file_name).name
            )
            return StatusResult(DownloadAction.COMPLETED)
        # Continue with download
        return StatusResult(DownloadAction.PROCEED)

    if status_code == 200:
        # know the total size, then delete the file that wasn't downloaded entirely
        # and redownload it.
        if "Content-length" in r.headers:
            remote_size = int(r.headers["Content-length"])

            if _new_file_from_web(r, file_path):
                logger.info(
                    "There is a new file from %s. %s is ready to be downloaded again",
                    url,
                    Path(file_name).name,
                )
                Path(file_path).unlink()
            elif 0 < local_size < remote_size:
                logger.info(
                    "  Detect %s wasn't downloaded entirely Prepare to remove the "
                    "local file and redownload since the "
                    "server not supports resuming breakpoint",
                    Path(file_name).name,
                )
                Path(file_path).unlink()
            elif local_size > remote_size:
                logger.info(
                    "Detected the local file (%s) is larger than the server file. "
                    " Prepare to remove local the file and redownload...",
                    Path(file_name).name,
                )
                Path(file_path).unlink()
            elif local_size == remote_size:
                logger.info(
                    "%s was downloaded entirely. skipping download",
                    Path(file_name).name,
                )
                return StatusResult(DownloadAction.COMPLETED)
        # don't know the total size, warning user if detect the file was downloaded.
        elif Path(file_path).exists():
            logger.warning(
                ">>> Warning: Detect the %s was downloaded, but can't parse the "
                "it's size from website\n"
                "    If you know it wasn't downloaded entirely, delete it and "
                "redownload it again. skipping download...",
                Path(file_name).name,
            )
            return StatusResult(DownloadAction.COMPLETED)
        # Continue with download
        return StatusResult(DownloadAction.PROCEED)

    if status_code in RETRYABLE_STATUS_CODES:
        # Unified handling of retryable errors
        reason = RETRYABLE_STATUS_CODES[status_code]
        logger.info(">>> Server returned %s (%s), will retry...", status_code, reason)
        return StatusResult(DownloadAction.RETRY, status_code)

    if status_code in {301, 302}:
        url_new = r.headers["Location"]
        logger.warning(">>> Warning: the website has redirected to %s", url_new)
        return StatusResult(DownloadAction.REDIRECT, url_new)

    if status_code == 401:
        netrc_file = Path("~/.netrc").expanduser()
        logger.error(
            ">>> Authorization failed! Please check your username and password in %s. "
            "More details about .netrc file: https://data-downloader.readthedocs.io/en/latest/user_guide/netrc.html"
            "\n Or authorizing by browser and set the parameter "
            "`authorize_from_browser` to `True`",
            netrc_file,
        )
        return StatusResult(DownloadAction.FAIL)

    if status_code == 403:
        logger.error(
            ">>> Forbidden! Access to the requested resource was denied by the server"
        )
        return StatusResult(DownloadAction.FAIL)

    logger.error(
        '  Download file from "%s" failed,  The service returns the HTTP '
        "Status Code: %s",
        url,
        status_code,
    )
    return StatusResult(DownloadAction.FAIL)


def _download_data_httpx(
    url: str,
    folder: str | Path | None = None,
    file_name: str | Path | None = None,
    client: httpx.Client | None = None,
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    _max_retries: int | None = None,
) -> bool:
    """Download a single file using httpx.

    Parameters
    ----------
    url : str
        URL of web file
    folder : str, optional
        The folder to store output files. Default current folder.
    file_name : str, optional
        The file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client : httpx.Client, optional
        Client maintaining connection. Default None
    follow_redirects : bool, optional
        Enables or disables HTTP redirects. Default True
    retry : int, optional
        Number of retries for transient errors (202, 408, 429, 500-504).
        Each retry waits 0.5-5 seconds (2-10 seconds for 429 with Retry-After).
        Default is 10.
    authorize_from_browser : bool, optional
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logging in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.
    _max_retries : int | None, optional
        Internal parameter to track initial retry count. Do not set manually.

    """
    # Initialize max_retries on first call
    if _max_retries is None:
        _max_retries = retry

    # init parameters
    global support_resume, pbar, remote_size

    params = {
        "message": "downloading data with httpx",
        "url": url,
        "folder": folder,
        "file_name": file_name,
        "follow_redirects": follow_redirects,
        "retry": retry,
        "authorize_from_browser": authorize_from_browser,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.debug(msg)

    support_resume = False
    headers = {"Range": "bytes=0-4"}
    if not client:
        client = httpx

    cj = _get_cookiejar(authorize_from_browser)
    auth = get_netrc_auth(url)

    r = client.get(
        url,
        headers=headers,
        timeout=120,
        follow_redirects=follow_redirects,
        cookies=cj,
        auth=auth,
    )
    r.close()

    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        file_path = Path(folder) / file_name
    else:
        file_path = Path(file_name).resolve()

    local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

    result = _handle_status(r, url, local_size, file_name, file_path)

    # Handle different actions
    if result.action == DownloadAction.COMPLETED:
        return True

    if result.action == DownloadAction.FAIL:
        return False

    if result.action == DownloadAction.REDIRECT:
        # Redirect to new URL
        return _download_data_httpx(
            str(result.extra),
            folder=folder,
            file_name=file_name,
            client=client,
            follow_redirects=follow_redirects,
            retry=retry,
            authorize_from_browser=authorize_from_browser,
            _max_retries=_max_retries,
        )

    if result.action == DownloadAction.RETRY:
        # Retryable error
        if retry > 0:
            status_code = int(result.extra)
            wait_time = _get_retry_wait_time(r, status_code)

            current_attempt = _max_retries - retry + 1
            remaining = retry - 1

            if remaining <= 3:  # Warning when few attempts left
                logger.warning(
                    ">>> Retrying %s for %s (%s attempts remaining)",
                    status_code,
                    url,
                    remaining,
                )
            else:
                logger.info(
                    ">>> Retrying %s (attempt %s/%s)",
                    status_code,
                    current_attempt,
                    _max_retries,
                )

            time.sleep(wait_time)
            return _download_data_httpx(
                url,
                folder=folder,
                file_name=file_name,
                client=client,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )

        logger.error(">>> Max retries (%s) exceeded for %s", _max_retries, url)
        return False

    # result.action == DownloadAction.PROCEED
    # Continue with download

    # begin downloading
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None

    try:
        with (
            client.stream("GET", url, headers=headers, timeout=120, cookies=cj) as r,
            Path(file_path).open("ab") as f,
        ):
            time_start_realtime = time_start = time.time()
            for chunk in r.iter_raw():
                if chunk:
                    size_add = len(chunk)
                    local_size += size_add
                    f.write(chunk)
                    f.flush()
                    if support_resume:
                        pbar.update(size_add)
                    else:
                        time_end_realtime = time.time()
                        time_span = time_end_realtime - time_start_realtime
                        if time_span > 1:
                            speed_realtime = size_add / time_span
                            logger.info(
                                "  Downloading %s [Speed: %s | Size: %s]",
                                Path(file_name).name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            )
                            time_start_realtime = time_end_realtime
            if not support_resume:
                time_cost = time.time() - time_start
                speed = local_size / time_cost if time_cost > 0 else 0
                logger.info(
                    "  Finish downloading %s [Speed: %s | Total Size: %s]",
                    Path(file_name).name,
                    _unit_formater(speed, "B/s"),
                    _unit_formater(local_size, "B"),
                )
        return True
    except (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadError,
        httpx.RemoteProtocolError,
    ) as e:
        logger.error(
            "Connection error while downloading %s from %s: %s",
            Path(file_name).name,
            url,
            type(e).__name__,
        )
        if retry > 0:
            current_attempt = _max_retries - retry + 1
            wait_time = random.uniform(1, 5)
            logger.info(
                ">>> Retrying connection (attempt %s/%s) after %.1fs...",
                current_attempt,
                _max_retries,
                wait_time,
            )
            time.sleep(wait_time)
            return _download_data_httpx(
                url,
                folder=folder,
                file_name=file_name,
                client=client,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )
        logger.error(
            ">>> Max retries (%s) exceeded for %s due to connection errors",
            _max_retries,
            url,
        )
        return False
    except Exception as e:
        logger.exception(
            "Unexpected error while downloading %s from %s: %s",
            Path(file_name).name,
            url,
            str(e),
        )
        return False


def _download_data_requests(
    url: str,
    folder: str | Path | None = None,
    file_name: str | Path | None = None,
    client: requests.Session | None = None,
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    _max_retries: int | None = None,
) -> bool:
    """Download a single file using requests.

    Parameters
    ----------
    url : str
        URL of web file
    folder : str, optional
        The folder to store output files. Default current folder.
    file_name : str, optional
        The file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client : requests.Session, optional
        Client maintaining connection. Default None
    follow_redirects : bool, optional
        Enables or disables HTTP redirects. Default True
    retry : int, optional
        Number of retries for transient errors (202, 408, 429, 500-504).
        Each retry waits 0.5-5 seconds (2-10 seconds for 429 with Retry-After).
        Default is 10.
    authorize_from_browser : bool, optional
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logging in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.
    _max_retries : int | None, optional
        Internal parameter to track initial retry count. Do not set manually.

    """
    # Initialize max_retries on first call
    if _max_retries is None:
        _max_retries = retry
    # init parameters
    global support_resume, pbar, remote_size

    params = {
        "message": "downloading data with requests",
        "url": url,
        "folder": folder,
        "file_name": file_name,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.debug(msg)

    support_resume = False
    headers = {"Range": "bytes=0-4"}
    if not client:
        client = requests

    cj = _get_cookiejar(authorize_from_browser)

    r = client.get(
        url, headers=headers, timeout=120, allow_redirects=follow_redirects, cookies=cj
    )
    r.close()

    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        file_path = Path(folder) / file_name
    else:
        file_path = Path(file_name).resolve()

    local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

    result = _handle_status(r, url, local_size, file_name, file_path)

    # Handle different actions
    if result.action == DownloadAction.COMPLETED:
        return True

    if result.action == DownloadAction.FAIL:
        return False

    if result.action == DownloadAction.REDIRECT:
        # Redirect to new URL
        return _download_data_requests(
            str(result.extra),
            folder=folder,
            file_name=file_name,
            client=client,
            follow_redirects=follow_redirects,
            retry=retry,
            authorize_from_browser=authorize_from_browser,
            _max_retries=_max_retries,
        )

    if result.action == DownloadAction.RETRY:
        # Retryable error
        if retry > 0:
            status_code = int(result.extra)
            wait_time = _get_retry_wait_time(r, status_code)

            current_attempt = _max_retries - retry + 1
            remaining = retry - 1

            if remaining <= 3:  # Warning when few attempts left
                logger.warning(
                    ">>> Retrying %s for %s (%s attempts remaining)",
                    status_code,
                    url,
                    remaining,
                )
            else:
                logger.info(
                    ">>> Retrying %s (attempt %s/%s)",
                    status_code,
                    current_attempt,
                    _max_retries,
                )

            time.sleep(wait_time)
            return _download_data_requests(
                url,
                folder=folder,
                file_name=file_name,
                client=client,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )

        logger.error(">>> Max retries (%s) exceeded for %s", _max_retries, url)
        return False

    # result.action == DownloadAction.PROCEED
    # Continue with download

    # begin downloading
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None

    r = client.get(url, headers=headers, stream=True, timeout=120, cookies=cj)
    with Path(file_path).open("ab") as f:
        time_start_realtime = time_start = time.time()
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
                if support_resume:
                    pbar.update(size_add)
                else:
                    time_end_realtime = time.time()
                    time_span = time_end_realtime - time_start_realtime
                    if time_span > 1:
                        speed_realtime = size_add / time_span
                        logger.info(
                            "  Downloading %s [Speed: %s | Size: %s]",
                            Path(file_name).name,
                            _unit_formater(speed_realtime, "B/s"),
                            _unit_formater(local_size, "B"),
                        )
                        time_start_realtime = time_end_realtime
        if not support_resume:
            time_cost = time.time() - time_start
            speed = local_size / time_cost if time_cost > 0 else 0
            logger.info(
                "  Finish downloading %s [Speed: %s | Total Size: %s]",
                Path(file_name).name,
                _unit_formater(speed, "B/s"),
                _unit_formater(local_size, "B"),
            )

    r.close()
    return True


async def _aiohttp_head_with_netrc(
    session: aiohttp.ClientSession,
    url: str,
    cookies: Any = None,
    max_redirects: int = 10,
) -> dict[str, Any]:
    """Perform GET request (not HEAD) with aiohttp to get headers, following redirects and applying .netrc auth.

    Note: We use GET instead of HEAD because some servers (like ASF) don't handle HEAD
    requests properly for authentication redirects.

    Parameters
    ----------
    session : aiohttp.ClientSession
        The aiohttp session
    url : str
        URL to fetch
    cookies : Any, optional
        Cookies to include
    max_redirects : int
        Maximum number of redirects to follow

    Returns
    -------
    dict[str, Any]
        Response headers from the final URL

    """
    current_url = url
    for _ in range(max_redirects):
        # Get auth for current URL
        auth_tuple = get_netrc_auth(current_url)
        auth = aiohttp.BasicAuth(*auth_tuple) if auth_tuple else None

        async with session.get(
            current_url, allow_redirects=False, cookies=cookies, auth=auth
        ) as r:
            # Check if it's a redirect
            if r.status in (301, 302, 303, 307, 308):
                # Follow the redirect
                current_url = str(r.headers.get("Location", ""))
                if not current_url:
                    break
                continue
            # Not a redirect, return headers (we got the final response)
            return dict(r.headers)

    # Max redirects exceeded or no location header
    raise ValueError(f"Too many redirects or invalid redirect for {url}")


async def _download_data_async(
    url: str,
    folder: str | None = None,
    file_name: str | None = None,
    client: Any | None = None,
    engine: str = "httpx",
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_url: str | None = None,
    expected_checksum: str | None = None,
) -> bool:
    """Async implementation of download with chunking and resume support.

    Parameters
    ----------
    See download_file() for parameter descriptions

    Returns
    -------
    bool
        True if download succeeded

    """
    # Create client if not provided
    client_created = False
    if client is None:
        client_created = True
        if engine == "httpx":
            client = httpx.AsyncClient(
                timeout=None, verify=False, follow_redirects=True
            )
        if engine == "aiohttp":
            client = aiohttp.ClientSession(trust_env=True)
        else:
            raise ValueError(f"Invalid async engine: {engine}")

    try:
        # Pre-process URL (authentication, cookie priming, etc.)
        extra_headers = await process_url_handlers(url, client, engine)

        # Get file size and check server support
        # IMPORTANT: Always use httpx for range detection because its NetrcAuth
        # properly handles cross-domain redirects (e.g., ASF → Earthdata → S3),
        # while aiohttp's auth doesn't get re-applied on redirects
        cj = _get_cookiejar(authorize_from_browser)

        # Create temporary httpx client if not using httpx engine
        httpx_client_for_head = None
        if engine == "httpx":
            head_client = client
        else:
            # Create httpx client just for HEAD check
            # httpx is imported at the top of this file
            httpx_client_for_head = httpx.AsyncClient()
            head_client = httpx_client_for_head

        try:
            # Use httpx GET with Range to detect file info
            # Retry mechanism for head request
            for attempt in range(retry + 1):
                try:
                    r = await head_client.get(
                        url,
                        headers={"Range": "bytes=0-10"},
                        cookies=cj,
                        follow_redirects=True,
                    )
                    headers = r.headers
                    break
                except httpx.RequestError as e:
                    if attempt == retry:
                        logger.error(
                            "Failed to get file info after %s retries: %s", retry, e
                        )
                        raise
                    wait_time = 0.5 * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Error getting file info (attempt {attempt + 1}/{retry + 1}): {e}. Retrying in {wait_time:.2f}s..."
                    )
                    await asyncio.sleep(wait_time)
        finally:
            # Clean up temporary client if created
            if httpx_client_for_head:
                await httpx_client_for_head.aclose()

        # Extract file info
        file_size = int(headers.get("content-length", 0))
        supports_range = "accept-ranges" in headers or "content-range" in headers

        # Parse file name if not provided
        if file_name is None:
            if engine == "httpx":
                file_name = _parse_file_name(r)
            else:  # aiohttp
                # For aiohttp, parse from URL
                file_name = Path(urlparse(url).path).name
                if not file_name:
                    file_name = "downloaded_file"

        # Determine file path
        if folder is not None:
            Path(folder).mkdir(exist_ok=True, parents=True)
            file_path = Path(folder) / file_name
        else:
            file_path = Path(file_name).absolute()

        # Force restart: delete metadata and part files
        if force_restart:
            metadata = _ChunkedDownloadMetadata.load(file_path)
            if metadata:
                logger.info(
                    "Force restart: cleaning up existing download for %s", file_name
                )
                metadata.cleanup(keep_parts=False)

        # Check for resume
        if file_size > 0 and supports_range:
            actual_chunks, metadata = await _detect_and_resume_download(
                url=url,
                file_path=file_path,
                file_size=file_size,
                chunks=chunks,
                _engine=engine,
                _supports_range=supports_range,
            )
        else:
            # No size info or no range support
            actual_chunks = 1
            metadata = None
            if chunks and chunks > 1:
                logger.warning(
                    "Server doesn't support range requests or file size unknown. "
                    "Using sequential download."
                )

        # Download file
        if actual_chunks == 1:
            # Sequential download (single chunk)
            if metadata:
                # Resume single-chunk download
                logger.info("Resuming single-chunk download for %s", file_name)

            # Use existing sequential download functions
            if engine == "httpx":
                success = await _download_single_file_httpx(
                    client=client,
                    url=url,
                    folder=folder,
                    file_name=file_name,
                    follow_redirects=follow_redirects,
                    retry=retry,
                    authorize_from_browser=authorize_from_browser,
                )
            else:  # aiohttp
                success = await _download_single_file_aiohttp(
                    client=client,
                    url=url,
                    folder=folder,
                    file_name=file_name,
                    follow_redirects=follow_redirects,
                    retry=retry,
                    authorize_from_browser=authorize_from_browser,
                )
        # Chunked download
        elif engine == "httpx":
            success = await _download_data_chunked_httpx(
                client=client,
                url=url,
                file_path=file_path,
                chunks=actual_chunks,
                file_size=file_size,
                retry=retry,
                metadata=metadata,
                authorize_from_browser=authorize_from_browser,
            )
        else:  # aiohttp
            success = await _download_data_chunked_aiohttp(
                session=client,
                url=url,
                file_path=file_path,
                chunks=actual_chunks,
                file_size=file_size,
                retry=retry,
                metadata=metadata,
                authorize_from_browser=authorize_from_browser,
            )

        if not success:
            return False

        # Verify checksum if requested
        if verify_checksum:
            checksum_info = None

            # Try to get checksum from expected_checksum parameter
            if expected_checksum:
                parts = expected_checksum.split(":", 1)
                if len(parts) == 2:
                    checksum_info = {
                        "type": parts[0],
                        "value": parts[1],
                        "reliable": True,
                    }

            # Try to download external checksum file
            if not checksum_info and checksum_url:
                checksum_info = await _download_checksum_file(client, checksum_url)

            # Try to extract from response headers
            if not checksum_info:
                checksum_info = _extract_checksum_from_headers(headers)

            # Verify
            if checksum_info:
                is_valid = _verify_file_checksum(
                    file_path,
                    checksum_info,
                    verify_unreliable=(verify_checksum == "strict"),
                )

                if not is_valid and verify_checksum == "strict":
                    logger.error("Strict checksum verification failed. Deleting file.")
                    file_path.unlink()
                    return False

        return True

    finally:
        # Close client if we created it
        if client_created:
            if engine == "httpx":
                await client.aclose()
            else:  # aiohttp
                await client.close()


# Wrapper functions for single-file async downloads
async def _download_single_file_httpx(
    client: httpx.AsyncClient,
    url: str,
    folder: str | None,
    file_name: str | None,
    follow_redirects: bool,
    retry: int,
    authorize_from_browser: bool,
) -> bool:
    """Download single file using httpx (adapter for existing _download_data)."""
    # Use existing async httpx download function
    return await _download_data(
        client=client,
        url=url,
        folder=folder,
        file_name=file_name,
        follow_redirects=follow_redirects,
        retry=retry,
        authorize_from_browser=authorize_from_browser,
    )


async def _download_single_file_aiohttp(
    client: aiohttp.ClientSession,
    url: str,
    folder: str | None,
    file_name: str | None,
    follow_redirects: bool,
    retry: int,
    authorize_from_browser: bool,
    _max_retries: int | None = None,
) -> bool:
    """Download single file using aiohttp.

    This implements sequential download similar to _download_data (httpx version).
    """
    # Initialize max_retries on first call
    if _max_retries is None:
        _max_retries = retry

    global support_resume, pbar, remote_size

    headers = {"Range": "bytes=0-4"}
    support_resume = False

    cj = _get_cookiejar(authorize_from_browser)
    auth = get_netrc_auth(url)
    if auth:
        auth = aiohttp.BasicAuth(*auth)

    params = {
        "message": "downloading data with aiohttp",
        "url": url,
        "folder": folder,
        "file_name": file_name,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.debug(msg)

    # Check if server supports resume
    try:
        async with client.get(
            url,
            headers=headers,
            allow_redirects=follow_redirects,
            cookies=cj,
            auth=auth,
        ) as r:
            if file_name is None:
                # Parse from URL
                file_name = os.path.basename(urlparse(url).path)
                if not file_name:
                    file_name = "downloaded_file"

            if folder is not None:
                file_path = os.path.join(folder, file_name)
            else:
                file_path = os.path.abspath(file_name)

            local_size = (
                Path(file_path).stat().st_size if Path(file_path).exists() else 0
            )

            # Handle status
            result = _handle_status(r, url, local_size, file_name, file_path)

            # Handle different actions
            if result.action == DownloadAction.COMPLETED:
                return True

            if result.action == DownloadAction.FAIL:
                return False

            if result.action == DownloadAction.REDIRECT:
                # Redirect to new URL
                return await _download_single_file_aiohttp(
                    client,
                    str(result.extra),
                    folder=folder,
                    file_name=file_name,
                    follow_redirects=True,
                    retry=retry,
                    authorize_from_browser=authorize_from_browser,
                    _max_retries=_max_retries,
                )

            if result.action == DownloadAction.RETRY:
                # Retryable error
                if retry > 0:
                    status_code = int(result.extra)
                    wait_time = _get_retry_wait_time(r, status_code)

                    current_attempt = _max_retries - retry + 1
                    remaining = retry - 1

                    if remaining <= 3:  # Warning when few attempts left
                        logger.warning(
                            ">>> Retrying %s for %s (%s attempts remaining)",
                            status_code,
                            url,
                            remaining,
                        )
                    else:
                        logger.info(
                            ">>> Retrying %s (attempt %s/%s)",
                            status_code,
                            current_attempt,
                            _max_retries,
                        )

                    await asyncio.sleep(wait_time)
                    return await _download_single_file_aiohttp(
                        client,
                        url,
                        folder=folder,
                        file_name=file_name,
                        follow_redirects=follow_redirects,
                        retry=retry - 1,
                        authorize_from_browser=authorize_from_browser,
                        _max_retries=_max_retries,
                    )

                logger.error(">>> Max retries (%s) exceeded for %s", _max_retries, url)
                return False

        # result.action == DownloadAction.PROCEED
        # Continue with download

        # Begin download
        if support_resume:
            headers["Range"] = f"bytes={local_size}-{remote_size}"
        else:
            headers = {}

        async with client.get(url, headers=headers, cookies=cj) as r:
            # Get total size for progress bar (if available)
            total_size = int(r.headers.get("Content-Length", 0))

            with Path(file_path).open("ab") as f:
                # Use tqdm for progress regardless of resume support
                from tqdm import tqdm

                with tqdm(
                    total=total_size or None,
                    initial=0,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=Path(file_name).name,
                    leave=True,
                    dynamic_ncols=True,
                ) as pbar_local:
                    async for chunk in r.content.iter_any():
                        if chunk:
                            size_add = len(chunk)
                            local_size += size_add
                            f.write(chunk)
                            f.flush()
                            pbar_local.update(size_add)

            return True

    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        if retry > 0:
            logger.warning(
                ">>> Network error for %s: %s. Retrying (%s/%s)",
                url,
                e,
                _max_retries - retry + 1,
                _max_retries,
            )
            # Randomized exponential backoff
            wait_time = 0.5 * (2 ** (_max_retries - retry)) + random.uniform(0, 1)
            await asyncio.sleep(wait_time)
            return await _download_single_file_aiohttp(
                client,
                url,
                folder=folder,
                file_name=file_name,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )
        logger.error(
            ">>> Max retries (%s) exceeded for %s due to network error: %s",
            _max_retries,
            url,
            e,
        )
        return False


def download_file(
    url: str,
    folder: str | None = None,
    file_name: str | None = None,
    client: Any | None = None,
    engine: Literal["requests", "httpx", "aiohttp"] = "requests",
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_url: str | None = None,
    expected_checksum: str | None = None,
) -> bool:
    """Download a single file with optional chunked download and resume support.

    Parameters
    ----------
    url : str
        URL of web file
    folder : str, optional
        The folder to store output files. Default current folder.
    file_name : str, optional
        The file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client : requests.Session | httpx.Client | httpx.AsyncClient | aiohttp.ClientSession, optional
        Client maintaining connection. Default None
    engine : {"requests", "httpx", "aiohttp"}
        Download engine. Default "requests"
    follow_redirects : bool
        Enables or disables HTTP redirects. Default True
    retry : int
        Number of retries for transient errors (202, 408, 429, 5xx). Default 10
    authorize_from_browser : bool
        Whether to load cookies used by your web browser for authorization.
        Supports Chrome, Firefox, Opera, Edge, Chromium. Default False
    chunks : int | None, optional
        Number of chunks for parallel download (httpx/aiohttp only).
        - None: auto-detect based on file size
        - 1: no chunking (sequential download)
        - >1: download with specified chunks
        Note: requests engine ignores this parameter
    force_restart : bool
        If True, delete existing metadata and restart download. Default False
    verify_checksum : bool | Literal["strict"]
        Checksum verification mode:
        - False: no verification (default)
        - True: verify reliable checksums if available
        - "strict": verify all checksums, fail if mismatch
    checksum_url : str | None
        URL to external checksum file (.md5, .sha256, etc.)
    expected_checksum : str | None
        Expected checksum value (format: "sha256:abc..." or "md5:def...")

    Returns
    -------
    bool
        True if download succeeded, False otherwise

    Examples
    --------
    >>> from data_downloader import downloader
    >>> downloader.download_file("https://example.com/file.zip", folder="/data")

    """
    if engine == "requests":
        # Requests engine doesn't support chunked downloads
        if chunks and chunks > 1:
            logger.warning(
                "Chunked download (chunks=%s) is not supported with 'requests' "
                "engine. Using sequential download. Use engine='httpx' or "
                "'aiohttp' for chunked downloads.",
                chunks,
            )

        return _download_data_requests(
            url,
            folder,
            file_name,
            client,
            follow_redirects,
            retry,
            authorize_from_browser,
        )

    if engine in {"httpx", "aiohttp"}:
        # Async engines support chunked downloads
        # Run async function in event loop
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If we are in a running event loop (e.g. Jupyter), we cannot call asyncio.run()
            # So we run it in a separate thread.
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _download_data_async(
                        url=url,
                        folder=folder,
                        file_name=file_name,
                        client=client,
                        engine=engine,
                        follow_redirects=follow_redirects,
                        retry=retry,
                        authorize_from_browser=authorize_from_browser,
                        chunks=chunks,
                        force_restart=force_restart,
                        verify_checksum=verify_checksum,
                        checksum_url=checksum_url,
                        expected_checksum=expected_checksum,
                    ),
                )
                return future.result()
        else:
            # Not in async context, create new loop
            return asyncio.run(
                _download_data_async(
                    url=url,
                    folder=folder,
                    file_name=file_name,
                    client=client,
                    engine=engine,
                    follow_redirects=follow_redirects,
                    retry=retry,
                    authorize_from_browser=authorize_from_browser,
                    chunks=chunks,
                    force_restart=force_restart,
                    verify_checksum=verify_checksum,
                    checksum_url=checksum_url,
                    expected_checksum=expected_checksum,
                )
            )

    else:
        params = {
            "message": "Invalid engine",
            "engine used": engine,
            "available engines": ["requests", "httpx", "aiohttp"],
        }
        msg = pformat(safe_repr(params), indent=4)
        logger.error(msg)
        raise ValueError(msg)


def download_files(
    urls: Iterable[str],
    folder: str | None = None,
    file_names: Iterable[str] | None = None,
    engine: Literal["requests", "httpx", "aiohttp"] = "requests",
    authorize_from_browser: bool = False,
    desc: str = "",
    client: Any | None = None,
    follow_redirects: bool = True,
    retry: int = 10,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_urls: Iterable[str] | None = None,
    expected_checksums: Iterable[str] | None = None,
) -> None:
    r"""Download data from a list like object which containing urls.

    Parameters
    ----------
    urls:  iterator
        iterator contains urls
    folder: str
        the folder to store output files. Default current folder.
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program to parse
        them from website. file_names can contain the absolute paths if folder is None.
    engine: one of ["requests", "httpx", "aiohttp"]
        engine for downloading. Default "requests".
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logging in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.
    desc: str
        description of data downloading
    client : requests.Session | httpx.Client, optional
        Client maintaining connection. Default None
    follow_redirects : bool
        Enables or disables HTTP redirects. Default True
    retry : int
        Number of retries for transient errors. Default 10
    chunks : int | None
        Number of chunks for parallel download (httpx/aiohttp only).
    force_restart : bool
        If True, delete existing metadata and restart download. Default False
    verify_checksum : bool | Literal["strict"]
        Checksum verification mode
    checksum_urls : iterator, optional
        Iterator containing checksum URLs
    expected_checksums : iterator, optional
        Iterator containing expected checksums

    Examples
    --------
    >>> from data_downloader import downloader

    specify the urls and folder

    >>> urls = ["http://example.com/1.tif", "http://example.com/2.tif"]
    >>> folder = "D:\\data"

    download data from urls and store them in folder

    >>> downloader.download_datas(urls, folder)

    """
    # Create client if not provided and using supported synchronous engines
    # Note: For async engines (httpx/aiohttp) without provided client, download_file
    # creates a new client/loop per file.
    if client is None:
        if engine == "requests":
            client = requests.Session()

    params = {
        "message": "Key parameters for download_datas",
        "urls": urls,
        "folder": folder,
        "file_names": file_names,
        "engine": engine,
        "authorize_from_browser": authorize_from_browser,
        "follow_redirects": follow_redirects,
        "retry": retry,
        "chunks": chunks,
        "force_restart": force_restart,
        "verify_checksum": verify_checksum,
        "checksum_urls": checksum_urls,
        "expected_checksums": expected_checksums,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.info(msg)

    # Convert iterables to lists for safe indexing
    fnames = list(file_names) if file_names else []
    c_urls = list(checksum_urls) if checksum_urls else []
    e_sums = list(expected_checksums) if expected_checksums else []

    desc = ">>> Total | " + desc.title()
    for i, url in enumerate(tqdm(urls, unit="files", dynamic_ncols=True, desc=desc)):
        # Get optional parameters for this specific file
        fname = fnames[i] if i < len(fnames) else None
        c_url = c_urls[i] if i < len(c_urls) else None
        e_sum = e_sums[i] if i < len(e_sums) else None

        download_file(
            url,
            folder,
            file_name=fname,
            client=client,
            engine=engine,
            authorize_from_browser=authorize_from_browser,
            follow_redirects=follow_redirects,
            retry=retry,
            chunks=chunks,
            force_restart=force_restart,
            verify_checksum=verify_checksum,
            checksum_url=c_url,
            expected_checksum=e_sum,
        )


def batch_download_files(
    urls: Iterable[str | Path],
    folder: str | None = None,
    file_names: Iterable[str | Path] | None = None,
    limit: int = 10,
    desc: str = "",
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    engine: Literal["httpx", "aiohttp"] = "httpx",
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_urls: Iterable[str] | None = None,
    expected_checksums: Iterable[str] | None = None,
) -> None:
    """Download multiple files concurrently.

    Parameters
    ----------
    urls : iterator
        Iterator containing URLs
    folder : str, optional
        Destination folder
    file_names : iterator, optional
        Iterator containing file names
    limit : int, optional
        Concurrency limit (max simultaneous downloads). Default 10.
    desc : str, optional
        Description for progress bar
    follow_redirects : bool
        Follow HTTP redirects
    retry : int
        Number of retries
    authorize_from_browser : bool
        Load cookies from browser
    engine : {"requests", "httpx", "aiohttp"}
        Download engine. Default "httpx".
        Note: "requests" engine is not supported for async batch download.
    chunks : int | None
        Chunk count per file
    force_restart : bool
        Force restart downloads
    verify_checksum : bool | str
        Checksum verification mode
    checksum_urls : iterator, optional
        Iterator containing checksum URLs
    expected_checksums : iterator, optional
        Iterator containing expected checksums

    """
    import asyncio

    params = {
        "message": "Key parameters for batch_download_files",
        "urls": urls,
        "folder": folder,
        "file_names": file_names,
        "limit": limit,
        "desc": desc,
        "follow_redirects": follow_redirects,
        "retry": retry,
        "authorize_from_browser": authorize_from_browser,
        "engine": engine,
        "chunks": chunks,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.info(msg)

    if engine not in {"httpx", "aiohttp"}:
        msg = "Batch download requires 'httpx' or 'aiohttp' engine"
        raise ValueError(msg)

    async def _bounded_download(
        sem: asyncio.Semaphore,
        client: Any,
        url: str,
        fname: str | None,
        c_url: str | None,
        exp_sum: str | None,
    ) -> bool:
        async with sem:
            return await _download_data_async(
                url=url,
                folder=folder,
                file_name=fname,
                client=client,
                engine=engine,
                follow_redirects=follow_redirects,
                retry=retry,
                authorize_from_browser=authorize_from_browser,
                chunks=chunks,
                force_restart=force_restart,
                verify_checksum=verify_checksum,
                checksum_url=c_url,
                expected_checksum=exp_sum,
            )

    async def _main() -> None:
        sem = asyncio.Semaphore(limit)

        # Create client
        if engine == "httpx":
            client = httpx.AsyncClient(timeout=None, verify=False)
        else:
            client = aiohttp.ClientSession(trust_env=True)

        try:
            tasks = []

            fnames = list(file_names) if file_names else []
            c_urls = list(checksum_urls) if checksum_urls else []
            e_sums = list(expected_checksums) if expected_checksums else []

            for i, url in enumerate(urls):
                fname = fnames[i] if i < len(fnames) else None
                c_url = c_urls[i] if i < len(c_urls) else None
                e_sum = e_sums[i] if i < len(e_sums) else None

                task = asyncio.create_task(
                    _bounded_download(sem, client, url, fname, c_url, e_sum)
                )
                tasks.append(task)

            desc_text = ">>> Total | " + desc.title() if desc else ">>> Total"

            for f in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc=desc_text,
                unit="files",
            ):
                await f

        finally:
            if engine == "httpx":
                await client.aclose()
            else:
                await client.close()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If we are in a running event loop (e.g. Jupyter), we cannot call asyncio.run()
        # So we run it in a separate thread.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _main())
            future.result()
    else:
        asyncio.run(_main())


async def _download_data(
    client: Any,
    url: str,
    folder: str | None = None,
    file_name: str | None = None,
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    _max_retries: int | None = None,
) -> bool:
    # Initialize max_retries on first call
    if _max_retries is None:
        _max_retries = retry

    global support_resume, pbar, remote_size

    headers = {"Range": "bytes=0-4"}
    support_resume = False

    cj = _get_cookiejar(authorize_from_browser)

    params = {
        "message": "Key parameters for _download_data (async)",
        "url": url,
        "folder": folder,
        "file_name": file_name,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.debug(msg)

    # auth = get_netrc_auth(url)

    async with client.stream(
        "GET",
        url,
        headers=headers,
        timeout=120,
        follow_redirects=follow_redirects,
        cookies=cj,
    ) as r:
        if file_name is None:
            file_name = _parse_file_name(r)

        if folder is not None:
            if not Path(folder).exists():
                Path(folder).mkdir(parents=True)
            file_path = os.path.join(folder, file_name)
        else:
            file_path = os.path.abspath(file_name)

        local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

        result = _handle_status(r, url, local_size, file_name, file_path)

    # Handle different actions
    if result.action == DownloadAction.COMPLETED:
        return True

    if result.action == DownloadAction.FAIL:
        return False

    if result.action == DownloadAction.REDIRECT:
        # Redirect to new URL
        return await _download_data(
            client,
            str(result.extra),
            folder=folder,
            file_name=file_name,
            follow_redirects=True,
            retry=retry,
            authorize_from_browser=authorize_from_browser,
            _max_retries=_max_retries,
        )

    if result.action == DownloadAction.RETRY:
        # Retryable error
        if retry > 0:
            status_code = int(result.extra)
            wait_time = _get_retry_wait_time(r, status_code)

            current_attempt = _max_retries - retry + 1
            remaining = retry - 1

            if remaining <= 3:  # Warning when few attempts left
                logger.warning(
                    ">>> Retrying %s for %s (%s attempts remaining)",
                    status_code,
                    url,
                    remaining,
                )
            else:
                logger.info(
                    ">>> Retrying %s (attempt %s/%s)",
                    status_code,
                    current_attempt,
                    _max_retries,
                )

            await asyncio.sleep(wait_time)
            return await _download_data(
                client,
                url,
                folder=folder,
                file_name=file_name,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )

        logger.error(
            ">>> Max retries (%s) exceeded for %s",
            _max_retries,
            url,
        )
        return False

    # result.action == DownloadAction.PROCEED
    # Continue with download

    # begin download
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None
    auth = get_netrc_auth(url)

    try:
        async with client.stream(
            "GET", url, headers=headers, auth=auth, timeout=None, cookies=cj
        ) as r:
            with Path(file_path).open("ab") as f:
                time_start_realtime = time_start = time.time()

                async for chunk in r.aiter_bytes():
                    size_add = len(chunk)
                    local_size += size_add
                    f.write(chunk)
                    f.flush()
                    if support_resume:
                        pbar.update(size_add)
                    else:
                        time_end_realtime = time.time()
                        time_span = time_end_realtime - time_start_realtime
                        if time_span > 1:
                            speed_realtime = size_add / time_span
                            logger.info(
                                "Downloading %s [Speed: %s | Size: %s]",
                                Path(file_name).name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            )
                            time_start_realtime = time_end_realtime
                if not support_resume:
                    speed = local_size / (time.time() - time_start)
                    logger.info(
                        "Finish downloading %s [Speed: %s | Total Size: %s]",
                        Path(file_name).name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                # r.close()
                return True
    except httpx.RequestError as e:
        if retry > 0:
            logger.warning(
                ">>> Network error for %s: %s. Retrying (%s/%s)",
                url,
                e,
                _max_retries - retry + 1,
                _max_retries,
            )
            # Randomized exponential backoff
            wait_time = 0.5 * (2 ** (_max_retries - retry)) + random.uniform(0, 1)
            await asyncio.sleep(wait_time)
            return await _download_data(
                client,
                url,
                folder=folder,
                file_name=file_name,
                follow_redirects=follow_redirects,
                retry=retry - 1,
                authorize_from_browser=authorize_from_browser,
                _max_retries=_max_retries,
            )
        logger.error(
            ">>> Max retries (%s) exceeded for %s due to network error: %s",
            _max_retries,
            url,
            e,
        )
        return False


async def _is_response_staus_ok(
    client: Any, url: str, authorize_from_browser: bool, timeout: int
) -> bool:
    cj = _get_cookiejar(authorize_from_browser)
    try:
        r = await client.head(url, timeout=timeout, cookies=cj)
        r.close()
        if r.status_code == httpx.codes.OK:
            return True
        return False
    except Exception as e:
        params = {
            "message": "Error for _is_response_staus_ok",
            "url": url,
            "error": str(e),
        }
        msg = pformat(safe_repr(params), indent=4)
        logger.debug(msg)
        return False


async def creat_tasks_status_ok(
    urls: Iterable[str], limit: int, authorize_from_browser: bool, timeout: int
) -> list[bool]:
    limits = httpx.Limits(max_keepalive_connections=limit, max_connections=limit)
    async with httpx.AsyncClient(limits=limits, timeout=None) as client:
        tasks = [
            asyncio.create_task(
                _is_response_staus_ok(client, url, authorize_from_browser, timeout)
            )
            for url in urls
        ]
        status_ok = await asyncio.gather(*tasks)

    return list(status_ok)


def status_ok(
    urls: Iterable[str],
    limit: int = 200,
    authorize_from_browser: bool = False,
    timeout: int = 60,
) -> list[bool]:
    """Simultaneously detecting whether the given links are accessible.

    Parameters
    ----------
    urls: iterator
        iterator contains urls
    limit: int
        the number of urls connecting simultaneously
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logging in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.
    timeout: int
        Request to stop waiting for a response after a given number of seconds

    Return:
    ------
    a list of results (True or False)

    Example:
    -------
    ```python
    from data_downloader import downloader
    import numpy as np

    urls = np.array([
        "https://www.baidu.com",
        "https://www.bai.com/wrongurl",
        "https://cn.bing.com/",
        "https://bing.com/wrongurl",
        "https://bing.com/",
    ])

    status_ok = downloader.status_ok(urls)
    urls_accessible = urls[status_ok]
    print(urls_accessible)
    ```

    """
    # solve the loop close  Error for python 3.8.x in windows platform
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop(selector)
    try:
        status_ok = loop.run_until_complete(
            creat_tasks_status_ok(urls, limit, authorize_from_browser, timeout)
        )
    # Zero-sleep to allow underlying connections to close
    finally:
        loop.close()

    return status_ok


def download_data(
    url: str,
    folder: str | None = None,
    file_name: str | None = None,
    client: Any | None = None,
    engine: Literal["requests", "httpx", "aiohttp"] = "requests",
    follow_redirects: bool = True,
    retry: int = 10,
    authorize_from_browser: bool = False,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_url: str | None = None,
    expected_checksum: str | None = None,
) -> bool:
    """Download a single file with optional chunked download and resume support."""
    warn_msg = (
        "download_data() is deprecated and will be removed in future versions. "
        "Please use download_file() instead."
    )
    logger.warning(warn_msg)
    return download_file(
        url=url,
        folder=folder,
        file_name=file_name,
        client=client,
        engine=engine,
        follow_redirects=follow_redirects,
        retry=retry,
        authorize_from_browser=authorize_from_browser,
        chunks=chunks,
        force_restart=force_restart,
        verify_checksum=verify_checksum,
        checksum_url=checksum_url,
        expected_checksum=expected_checksum,
    )


def download_datas(
    urls: Iterable[str],
    folder: str | None = None,
    file_names: Iterable[str] | None = None,
    engine: Literal["requests", "httpx", "aiohttp"] = "requests",
    authorize_from_browser: bool = False,
    desc: str = "",
    client: Any | None = None,
    follow_redirects: bool = True,
    retry: int = 10,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_urls: Iterable[str] | None = None,
    expected_checksums: Iterable[str] | None = None,
) -> None:
    """Download data from a list like object which containing urls."""
    warn_msg = (
        "download_datas() is deprecated and will be removed in future versions. "
        "Please use download_files() instead."
    )
    logger.warning(warn_msg)
    return download_files(
        urls=urls,
        folder=folder,
        file_names=file_names,
        engine=engine,
        authorize_from_browser=authorize_from_browser,
        desc=desc,
        client=client,
        follow_redirects=follow_redirects,
        retry=retry,
        chunks=chunks,
        force_restart=force_restart,
        verify_checksum=verify_checksum,
        checksum_urls=checksum_urls,
        expected_checksums=expected_checksums,
    )
