from __future__ import annotations

import asyncio
import datetime as dt
import os
import random
import selectors
import time
from netrc import netrc
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Literal
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
from .utils.tools import safe_repr

if TYPE_CHECKING:
    from os import PathLike

logger = setup_logger(__name__, handler=tqdm_handler)

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


# ============================================================================
# Checksum Extraction and Verification
# ============================================================================


def _extract_checksum_from_headers(headers) -> dict | None:
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
            return {"type": "md5", "value": md5_hex, "reliable": True}
        except Exception:
            pass

    # 2. Digest header (RFC 3230)
    if "digest" in headers:
        digest = headers["digest"]
        if "SHA-256=" in digest:
            try:
                hash_b64 = digest.split("SHA-256=")[1].split(",")[0]
                hash_hex = base64.b64decode(hash_b64).hex()
                return {"type": "sha256", "value": hash_hex, "reliable": True}
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
    checksum_info: dict | None,
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
        return False
    except Exception as e:
        logger.error("Error during checksum verification: %s", e)
        return False


async def _download_checksum_file(
    client, checksum_url: str, timeout: int = 30
) -> dict | None:
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

        return {"type": algo, "value": checksum, "reliable": True}

    except Exception as e:
        logger.debug("Failed to download checksum file %s: %s", checksum_url, e)
        return None


# ============================================================================
# Helper Functions (imported from modules, keeping here for backward compatibility)
# ============================================================================


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
    logger.info(f"Merging {chunks} chunks into {file_path.name}...")

    with Path(file_path).open("wb") as target:
        for i in range(chunks):
            part_path = file_path.parent / f"{file_path.name}.part{i}"
            if not part_path.exists():
                msg = f"Missing part file: {part_path.name}"
                logger.error(msg)
                raise FileNotFoundError(msg)

            with Path(part_path).open("rb") as part:
                target.write(part.read())

    # Delete part files after successful merge
    for i in range(chunks):
        part_path = file_path.parent / f"{file_path.name}.part{i}"
        part_path.unlink()

    logger.info("Successfully merged %s chunks", chunks)


def _get_retry_wait_time(response, status_code):
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
                        f"Server requested wait until {retry_after} ({wait_time:.1f}s)"
                    )
                return wait_time
            except Exception:
                pass  # Parse failed, use default

    # No Retry-After header, use default strategy
    if status_code == 429:  # Rate limiting
        return random.uniform(2, 10)
    # 202, 408, 5xx
    return random.uniform(0.5, 5)


def get_url_host(url):
    """Returns the url host for a given url"""
    ri = urlparse(url)
    # Strip port numbers from netloc. This weird `if...encode`` dance is
    # used for Python 3.2, which doesn't support unicode literals.
    splitstr = b":"
    if isinstance(url, str):
        splitstr = splitstr.decode("ascii")
    host = ri.netloc.split(splitstr)[0]
    return host


def get_netrc_auth(url):
    """Returns the Requests tuple auth for a given url from .netrc"""
    host = get_url_host(url)
    _netrc = Netrc().authenticators(host)

    if _netrc:
        # Return with login / password
        login_i = 0 if _netrc[0] else 1
        return (_netrc[login_i], _netrc[2])


class Netrc(netrc):
    """a class managing records in .netrc file"""

    def __init__(self, file: str | PathLike | None = None):
        if file is None:
            file = Path("~/.netrc").expanduser()
        else:
            file = Path(file)
        self.file = file
        if not file.exists():
            Path(self.file).open("w").close()

        super().__init__(file)

    def _info_to_file(self):
        rep = self.__repr__()
        Path(self.file).write_text(rep)

    def _update_info(self):
        with Path(self.file).open() as fp:
            self._parse(self.file, fp, False)

    def add(self, host, login, password, account=None, overwrite=False):
        """Add a record

        Will do nothing if host exists in .netrc file unless set overwrite=True
        """
        if host in self.hosts and not overwrite:
            logger.warning(
                ">>> Warning: %s existed, nothing will be done. If you want to overwrite the existed record, set overwrite=True",
                host,
            )
        else:
            self.hosts.update({host: (login, account, password)})
            self._info_to_file()
            self._update_info()

    def remove(self, host):
        """Remove a record by host"""
        self.hosts.pop(host)
        self._info_to_file()
        self._update_info()

    def clear(self):
        """Remove all records"""
        self.hosts = {}
        self._info_to_file()
        self._update_info()


def _parse_file_name(response):
    """Parse the file_name from the headers of web response or url"""
    if "Content-disposition" in response.headers:
        file_name = (
            response.headers["Content-disposition"]
            .split("filename=")[1]
            .strip('"')
            .strip("'")
        )
    else:
        file_name = os.path.basename(urlparse(str(response.url)).path)
    return file_name


def _unit_formater(size, suffix):
    prefixs = ["", "k", "M", "G", "T"]
    idx = 0
    while size / 1024 >= 1:
        size = size / 1024
        idx += 1
        if idx == 4:
            break

    return f"{size:.2f}{prefixs[idx]}{suffix}"


def _new_file_from_web(r, file_path):
    """Whether have new file from the website"""
    try:
        if not Path(file_path).exists():
            return False
        time_remote = parse(r.headers.get("Last-Modified"))
        time_local = dt.datetime.fromtimestamp(
            Path(file_path).stat().st_mtime, dt.timezone.utc
        )
        return time_remote > time_local
    except Exception as e:
        params = {
            "message": "Error for _new_file_from_web",
            "url": file_path,
            "error": str(e),
        }
        msg = pformat(safe_repr(params), indent=4)
        logger.debug(msg)
        return False


def _get_cookiejar(authorize_from_browser):
    cj = None
    if authorize_from_browser:
        try:
            cj = bc.load()
        except Exception as e:
            params = {
                "message": "Error for _get_cookiejar",
                "error": str(e),
                "info": "Could not load cookie from browser. "
                "Please login in website via browser before run this code"
                "\n  So far the following browsers are supported: "
                "Chrome,Firefox, Opera, Edge, Chromium",
            }
            msg = pformat(safe_repr(params), indent=4)
            logger.error(msg)
    return cj


def _handle_status(r, url, local_size, file_name, file_path):
    # returns (True, '') : downloaded entirely
    # returns (False,'') : error! break download
    # returns (False, url) : 301,302 redirect
    # returns (None, status_code): retryable error

    global support_resume, pbar, remote_size

    if r.status_code in [206, 416]:
        support_resume = True
        remote_size = int(r.headers["Content-Range"].rsplit("/")[-1])

        # init process bar
        if _new_file_from_web(r, file_path):
            msg = f"There is a new file from {url}. {Path(file_name).name} is ready to be downloaded again"
            logger.info(msg)
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
            msg = f"{Path(file_name).name} was downloaded entirely. skiping download"
            logger.info(msg)
            return True, ""
    elif r.status_code == 200:
        # know the total size, then delete the file that wasn't downloaded entirely and redownload it.
        if "Content-length" in r.headers:
            remote_size = int(r.headers["Content-length"])

            if _new_file_from_web(r, file_path):
                logger.info(
                    f"There is a new file from {url}. {Path(file_name).name} is ready to be downloaded again"
                )
                Path(file_path).unlink()
            elif 0 < local_size < remote_size:
                msg = (
                    f"  Detect {Path(file_name).name} wasn't downloaded entirely"
                    " Prepare to remove the local file and redownload since the "
                    "server not supports resuming breakpoint"
                )
                logger.info(msg)
                Path(file_path).unlink()
            elif local_size > remote_size:
                msg = (
                    f"Detected the local file ({Path(file_name).name}) is larger than the server file. "
                    " Prepare to remove local the file and redownload..."
                )
                logger.info(msg)
                Path(file_path).unlink()
            elif local_size == remote_size:
                msg = (
                    f"{Path(file_name).name} was downloaded entirely. skiping download"
                )
                logger.info(msg)
                return True, ""
        # don't know the total size, warning user if detect the file was downloaded.
        elif Path(file_path).exists():
            msg = (
                f">>> Warning: Detect the {Path(file_name).name} was downloaded,"
                " but can't parse the it's size from website\n"
                f"    If you know it wasn't downloaded entirely, delete "
                "it and redownload it again. skiping download..."
            )
            logger.warning(msg)
            return True, ""
    elif r.status_code in RETRYABLE_STATUS_CODES:
        # Unified handling of retryable errors
        reason = RETRYABLE_STATUS_CODES[r.status_code]
        msg = f">>> Server returned {r.status_code} ({reason}), will retry..."
        logger.info(msg)
        return None, r.status_code  # Return status code for retry logic
    elif r.status_code in [301, 302]:
        url_new = r.headers["Location"]
        msg = f">>> Warning: the website has redirected to {url_new}"
        logger.warning(msg)
        return False, url_new
    elif r.status_code == 401:
        netrc_file = Path("~/.netrc").expanduser()
        msg = (
            f">>> Authorization failed! Please check your username and password in {netrc_file}. "
            "More details about .netrc file: https://data-downloader.readthedocs.io/en/latest/user_guide/netrc.html"
            "\n Or authorizing by browser and set the parameter `authorize_from_browser` to `True`"
        )
        logger.error(msg)
        return False, ""
    elif r.status_code == 403:
        msg = ">>> Forbidden! Access to the requested resource was denied by the server"
        logger.error(msg)
        return False, ""
    else:
        msg = f'  Download file from "{url}" failed,  The service returns the HTTP Status Code: {r.status_code}'
        logger.error(msg)
        return False, ""


def _download_data_httpx(
    url,
    folder=None,
    file_name=None,
    client=None,
    follow_redirects=True,
    retry=10,
    authorize_from_browser=False,
):
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

    """
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

    r = client.get(
        url, headers=headers, timeout=120, follow_redirects=follow_redirects, cookies=cj
    )
    r.close()

    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        file_path = os.path.join(folder, file_name)
    else:
        file_path = os.path.abspath(file_name)

    local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

    result = _handle_status(r, url, local_size, file_name, file_path)
    if result:
        status, extra = result
        if status is True:  # downloaded entirely
            return True
        if status is False:
            if extra:  # 301/302 redirect, extra is new URL
                return _download_data_httpx(
                    extra,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    follow_redirects=True,
                    client=client,
                    retry=retry,
                )
            # permanent error
            return False
        if status is None:  # retryable error, extra is status_code
            status_code = extra

            if retry > 0:
                # Get wait time (with Retry-After support)
                wait_time = _get_retry_wait_time(r, status_code)

                # Improved logging
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
                        f">>> Retrying {status_code} (attempt {10 - remaining + 1}/10)"
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
                )
            logger.error(">>> Max retries exceeded for %s", url)
            return False

    # begin downloading
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None

    with client.stream("GET", url, headers=headers, timeout=120, cookies=cj) as r:
        with Path(file_path).open("ab") as f:
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
                            "  Downloading {} [Speed: {} | Size: {}]".format(
                                Path(file_name).name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            )
                        )
                        time_start_realtime = time_end_realtime
            if not support_resume:
                time_cost = time.time() - time_start
                speed = local_size / time_cost if time_cost > 0 else 0
                logger.info(
                    "  Finish downloading {} [Speed: {} | Total Size: {}]".format(
                        Path(file_name).name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                )
    return True


def _download_data_requests(
    url,
    folder=None,
    file_name=None,
    client=None,
    follow_redirects=True,
    retry=10,
    authorize_from_browser=False,
):
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

    """
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
        file_path = os.path.join(folder, file_name)
    else:
        file_path = os.path.abspath(file_name)

    local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

    result = _handle_status(r, url, local_size, file_name, file_path)
    if result:
        status, extra = result
        if status is True:  # downloaded entirely
            return True
        if status is False:
            if extra:  # 301/302 redirect, extra is new URL
                return _download_data_requests(
                    extra,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    follow_redirects=True,
                    client=client,
                    retry=retry,
                )
            # permanent error
            return False
        if status is None:  # retryable error, extra is status_code
            status_code = extra

            if retry > 0:
                # Get wait time (with Retry-After support)
                wait_time = _get_retry_wait_time(r, status_code)

                # Improved logging
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
                        f">>> Retrying {status_code} (attempt {10 - remaining + 1}/10)"
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
                )
            logger.error(">>> Max retries exceeded for %s", url)
            return False

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
                            "  Downloading {} [Speed: {} | Size: {}]".format(
                                Path(file_name).name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            )
                        )
                        time_start_realtime = time_end_realtime
        if not support_resume:
            time_cost = time.time() - time_start
            speed = local_size / time_cost if time_cost > 0 else 0
            logger.info(
                "  Finish downloading {} [Speed: {} | Total Size: {}]".format(
                    Path(file_name).name,
                    _unit_formater(speed, "B/s"),
                    _unit_formater(local_size, "B"),
                )
            )

    r.close()
    return True


async def _download_data_async(
    url: str,
    folder: str | None = None,
    file_name: str | None = None,
    client=None,
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
    See download_data() for parameter descriptions

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
            client = httpx.AsyncClient(timeout=None, verify=False)
        elif engine == "aiohttp":
            client = aiohttp.ClientSession()
        else:
            raise ValueError(f"Invalid async engine: {engine}")

    try:
        # Get file size and check server support
        cj = _get_cookiejar(authorize_from_browser)

        if engine == "httpx":
            r = await client.head(url, follow_redirects=follow_redirects, cookies=cj)
            headers = r.headers
        else:  # aiohttp
            async with client.head(
                url, allow_redirects=follow_redirects, cookies=cj
            ) as r:
                headers = r.headers

        # Extract file info
        file_size = int(headers.get("content-length", 0))
        supports_range = "accept-ranges" in headers or "content-range" in headers

        # Parse file name if not provided
        if file_name is None:
            if engine == "httpx":
                file_name = _parse_file_name(r)
            else:  # aiohttp
                # For aiohttp, parse from URL
                file_name = os.path.basename(urlparse(url).path)
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
                engine=engine,
                supports_range=supports_range,
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
) -> bool:
    """Download single file using aiohttp.

    This implements sequential download similar to _download_data (httpx version).
    """
    global support_resume, pbar, remote_size

    headers = {"Range": "bytes=0-4"}
    support_resume = False

    cj = _get_cookiejar(authorize_from_browser)

    params = {
        "message": "downloading data with aiohttp",
        "url": url,
        "folder": folder,
        "file_name": file_name,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.debug(msg)

    # Check if server supports resume
    async with client.get(
        url, headers=headers, allow_redirects=follow_redirects, cookies=cj
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

        local_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

        # Handle status
        result = _handle_status(r, url, local_size, file_name, file_path)
        if result:
            status, extra = result
            if status is True:
                return True
            if status is False:
                if extra:  # redirect
                    return await _download_single_file_aiohttp(
                        client,
                        extra,
                        folder=folder,
                        file_name=file_name,
                        follow_redirects=True,
                        retry=retry,
                        authorize_from_browser=authorize_from_browser,
                    )
                return False
            if status is None:  # retryable
                status_code = extra
                if retry > 0:
                    wait_time = _get_retry_wait_time(r, status_code)
                    await asyncio.sleep(wait_time)
                    return await _download_single_file_aiohttp(
                        client,
                        url,
                        folder=folder,
                        file_name=file_name,
                        follow_redirects=follow_redirects,
                        retry=retry - 1,
                        authorize_from_browser=authorize_from_browser,
                    )
                logger.error(">>> Max retries exceeded for %s", url)
                return False

    # Begin download
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = {}

    async with client.get(url, headers=headers, cookies=cj) as r:
        with Path(file_path).open("ab") as f:
            time_start_realtime = time_start = time.time()

            async for chunk in r.content.iter_any():
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
                                "  Downloading {} [Speed: {} | Size: {}]".format(
                                    Path(file_name).name,
                                    _unit_formater(speed_realtime, "B/s"),
                                    _unit_formater(local_size, "B"),
                                )
                            )
                            time_start_realtime = time_end_realtime

            if not support_resume:
                time_cost = time.time() - time_start
                speed = local_size / time_cost if time_cost > 0 else 0
                logger.info(
                    "  Finish downloading {} [Speed: {} | Total Size: {}]".format(
                        Path(file_name).name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                )

    return True


def download_data(
    url,
    folder=None,
    file_name=None,
    client=None,
    engine="requests",
    follow_redirects=True,
    retry=10,
    authorize_from_browser=False,
    chunks: int | None = None,
    force_restart: bool = False,
    verify_checksum: bool | Literal["strict"] = False,
    checksum_url: str | None = None,
    expected_checksum: str | None = None,
):
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
    Basic download:
    >>> download_data("https://example.com/file.zip", folder="/data")

    Chunked download with 8 chunks:
    >>> download_data(
    ...     "https://example.com/large.zip", folder="/data", engine="httpx", chunks=8
    ... )

    Auto-resume interrupted download:
    >>> download_data("https://example.com/file.zip", folder="/data")
    # Interrupted...
    >>> download_data("https://example.com/file.zip", folder="/data")
    # Automatically resumes from where it left off

    With checksum verification:
    >>> download_data(
    ...     "https://example.com/file.zip",
    ...     folder="/data",
    ...     verify_checksum=True,
    ...     checksum_url="https://example.com/file.zip.sha256",
    ... )

    """
    if engine == "requests":
        # Requests engine doesn't support chunked downloads
        if chunks and chunks > 1:
            logger.warning(
                "Chunked download (chunks=%s) is not supported with 'requests' engine. Using sequential download. Use engine='httpx' or 'aiohttp' for chunked downloads.",
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
            # Already in async context
            raise RuntimeError(
                "download_data() cannot be called from async context. "
                "Use async version directly or call from sync code."
            )
        except RuntimeError:
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


def download_datas(
    urls,
    folder=None,
    file_names=None,
    engine="requests",
    authorize_from_browser=False,
    desc="",
):
    r"""Download data from a list like object which containing urls.

    Parameters
    ----------
    urls:  iterator
        iterator contains urls
    folder: str
        the folder to store output files. Default current folder.
    engine: one of ["requests","httpx"]
        engine for downloading
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program to parse
        them from website. file_names can contain the absolute paths if folder is None.
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logging in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.
    desc: str
        description of data downloading

    Examples
    --------
    >>> from data_downloader import downloader

    specify the urls and folder

    >>> urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif']
    >>> folder = "D:\\data"

    download data from urls and store them in folder

    >>> downloader.download_datas(urls, folder)

    """
    if engine == "requests":
        client = requests.Session()
    elif engine == "httpx":
        client = httpx.Client(timeout=None)
    else:
        msg = 'engine must be one of ["requests","httpx"]'
        raise ValueError(msg)

    params = {
        "message": "Key parameters for download_datas",
        "urls": urls,
        "folder": folder,
        "file_names": file_names,
        "engine": engine,
        "authorize_from_browser": authorize_from_browser,
    }
    msg = pformat(safe_repr(params), indent=4)
    logger.info(msg)

    desc = ">>> Total | " + desc.title()
    for i, url in enumerate(tqdm(urls, unit="files", dynamic_ncols=True, desc=desc)):
        if file_names is not None:
            download_data(
                url,
                folder,
                file_name=file_names[i],
                client=client,
                engine=engine,
                authorize_from_browser=authorize_from_browser,
            )
        else:
            download_data(
                url,
                folder,
                client=client,
                engine=engine,
                authorize_from_browser=authorize_from_browser,
            )


def batch_download_files(
    urls,
    folder=None,
    file_names=None,
    limit=10,
    desc="",
    follow_redirects=True,
    retry=10,
    authorize_from_browser=False,
    engine="httpx",
    chunks=None,
    force_restart=False,
    verify_checksum=False,
    checksum_urls=None,
    expected_checksums=None,
):
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
    engine : str
        Download engine ("httpx" or "aiohttp"). Requests is not supported for async batch.
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

    if engine not in ["httpx", "aiohttp"]:
        raise ValueError("Batch download requires 'httpx' or 'aiohttp' engine")

    async def _bounded_download(sem, client, url, fname, c_url, exp_sum):
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

    async def _main():
        sem = asyncio.Semaphore(limit)

        # Create client
        if engine == "httpx":
            client = httpx.AsyncClient(timeout=None, verify=False)
        else:
            client = aiohttp.ClientSession()

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
        raise RuntimeError(
            "batch_download_files cannot be called from within a running event loop"
        )
    except RuntimeError:
        asyncio.run(_main())


async def _download_data(
    client,
    url,
    folder=None,
    file_name=None,
    follow_redirects=True,
    retry=10,
    authorize_from_browser=False,
):
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

    r = await client.get(
        url, headers=headers, timeout=120, follow_redirects=follow_redirects, cookies=cj
    )
    # r.close()
    # r = await client.head(url, headers=headers, auth=auth, timeout=120)
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
    if result:
        status, extra = result
        if status is True:  # downloaded entirely
            return True
        if status is False:
            if extra:  # 301, 302 redirect
                return await _download_data(
                    client,
                    extra,
                    folder=folder,
                    authorize_from_browser=authorize_from_browser,
                    file_name=file_name,
                    follow_redirects=True,
                    retry=retry,
                )
            # Permanent error (401, 403, 404, etc.)
            return False
        if status is None:  # Retryable error (202, 408, 429, 5xx)
            status_code = extra  # extra contains the status code
            if retry > 0:
                wait_time = _get_retry_wait_time(r, status_code)
                attempts_made = 10 - retry + 1  # Calculate attempt number (starts at 1)

                # Log based on remaining attempts
                if retry > 3:
                    logger.info(
                        f"Received {status_code} for {url}. Retrying in {wait_time:.1f}s... (Attempt {attempts_made}/10)"
                    )
                elif retry > 0:
                    logger.warning(
                        f"Received {status_code} for {url}. Retrying in {wait_time:.1f}s... (Attempt {attempts_made}/10, {retry} retries left)"
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
                )
            logger.error(
                "Max retries (10) exceeded for %s after receiving %s. Download failed.",
                url,
                status_code,
            )
            return False

    # begin download
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None
    auth = get_netrc_auth(get_url_host(url))
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
                            "Downloading {} [Speed: {} | Size: {}]".format(
                                Path(file_name).name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            )
                        )
                        time_start_realtime = time_end_realtime
            if not support_resume:
                speed = local_size / (time.time() - time_start)
                logger.info(
                    "Finish downloading {} [Speed: {} | Total Size: {}]".format(
                        Path(file_name).name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                )
            # r.close()
            return True


async def _is_response_staus_ok(client, url, authorize_from_browser, timeout):
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


async def creat_tasks_status_ok(urls, limit, authorize_from_browser, timeout):
    limits = httpx.Limits(max_keepalive_connections=limit, max_connections=limit)
    async with httpx.AsyncClient(limits=limits, timeout=None) as client:
        tasks = [
            asyncio.create_task(
                _is_response_staus_ok(client, url, authorize_from_browser, timeout)
            )
            for url in urls
        ]
        status_ok = await asyncio.gather(*tasks)

    return status_ok


def status_ok(urls, limit=200, authorize_from_browser=False, timeout=60):
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

    urls = np.array(
        [
            "https://www.baidu.com",
            "https://www.bai.com/wrongurl",
            "https://cn.bing.com/",
            "https://bing.com/wrongurl",
            "https://bing.com/",
        ]
    )

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
