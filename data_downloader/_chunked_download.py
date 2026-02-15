"""Chunked download implementation with resume support."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .logging import setup_logger, tqdm_handler

if TYPE_CHECKING:
    import aiohttp
    import httpx

    from ._metadata import _ChunkedDownloadMetadata

logger = setup_logger(__name__, handler=tqdm_handler)


async def _detect_and_resume_download(
    url: str,
    file_path: Path,
    file_size: int,
    chunks: int | None,
    _engine: str,
    _supports_range: bool,
) -> tuple[int, _ChunkedDownloadMetadata | None]:
    """Detect incomplete download and determine resume strategy.

    Parameters
    ----------
    url : str
        Download URL
    file_path : Path
        Target file path
    file_size : int
        Total file size
    chunks : int | None
        Requested chunks (None = auto-detect)
    engine : str
        Download engine
    supports_range : bool
        Whether server supports Range requests

    Returns
    -------
    tuple[int, _ChunkedDownloadMetadata | None]
        (actual_chunks_to_use, metadata_or_none)

    Notes
    -----
    - If metadata exists and is compatible: resume with existing chunks
    - If metadata exists but incompatible: use existing chunks (compatibility mode)
    - If no metadata: use requested chunks or auto-detect

    """
    from ._metadata import _ChunkedDownloadMetadata

    # Try to load existing metadata
    metadata = _ChunkedDownloadMetadata.load(file_path)

    if metadata is None:
        # No metadata found - check for orphaned part files
        _cleanup_orphaned_parts(file_path)

        # Use requested chunks or auto-detect
        if chunks is None or chunks == 0:
            from . import downloader

            actual_chunks = downloader._auto_detect_chunks(file_size)
        else:
            actual_chunks = chunks

        return actual_chunks, None

    # Metadata exists - check compatibility
    if not metadata.is_compatible(chunks, url):
        # Incompatible: different URL
        if metadata.url != url:
            logger.warning("Found metadata for different URL. Starting fresh download.")
            metadata.cleanup(keep_parts=False)
            actual_chunks = chunks or 1
            return actual_chunks, None

        # Incompatible: different chunks (but same URL)
        # Use compatibility mode: keep existing chunks
        if chunks and chunks != metadata.chunks:
            logger.warning(
                "You requested %s chunks, but found existing download with %s chunks",
                chunks,
                metadata.chunks,
            )
            logger.info(
                "Using existing %s chunks to resume download (compatibility mode)",
                metadata.chunks,
            )
            logger.info(
                "To restart with %s chunks, delete: %s and %s",
                chunks,
                file_path,
                metadata.meta_file,
            )

    # Compatible or using compatibility mode - check progress
    resume_info = metadata.get_resume_info()

    if resume_info["progress_percent"] >= 100:
        logger.info("Download already completed: %s", file_path.name)
        metadata.cleanup()
        return metadata.chunks, None

    # Log resume information
    logger.info("Detected incomplete download for %s", file_path.name)
    logger.info(
        "Resuming with %s chunks (%s completed, %s partial, %s pending)",
        metadata.chunks,
        len(resume_info["completed_parts"]),
        len(resume_info["partial_parts"]),
        len(resume_info["pending_parts"]),
    )
    logger.info(
        "Progress: %.1f%% already downloaded (%.1fMB / %.1fMB)",
        resume_info["progress_percent"],
        resume_info["total_downloaded"] / 1024 / 1024,
        file_size / 1024 / 1024,
    )

    return metadata.chunks, metadata


def _cleanup_orphaned_parts(file_path: Path) -> None:
    """Clean up orphaned part files without metadata.

    Parameters
    ----------
    file_path : Path
        Target file path

    """
    orphaned = list(file_path.parent.glob(f"{file_path.name}.part*"))

    if orphaned:
        logger.warning(
            "Found %s orphaned .part files for %s without metadata",
            len(orphaned),
            file_path.name,
        )
        logger.info("These may be from a previous interrupted download")
        logger.info(
            "Cleaning up orphaned files: %s", ", ".join(p.name for p in orphaned)
        )

        for part_file in orphaned:
            part_file.unlink()


async def _download_range_httpx(
    client: httpx.AsyncClient,
    url: str,
    start: int,
    end: int,
    part_path: Path,
    metadata: _ChunkedDownloadMetadata,
    part_index: int,
    retry: int = 10,
    authorize_from_browser: bool = False,
    pbar: Any | None = None,
) -> bool:
    """Download a specific byte range using httpx.

    Parameters
    ----------
    client : httpx.AsyncClient
        HTTP client
    url : str
        Download URL
    start : int
        Start byte position
    end : int
        End byte position (inclusive)
    part_path : Path
        Path to save this chunk
    metadata : _ChunkedDownloadMetadata
        Metadata object
    part_index : int
        Part index
    retry : int
        Number of retries
    authorize_from_browser : bool
        Load cookies from browser
    pbar : Any | None
        Optional tqdm progress bar to update

    Returns
    -------
    bool
        True if successful

    """
    from . import downloader

    cj = downloader._get_cookiejar(authorize_from_browser)
    auth = downloader.get_netrc_auth(url)

    for attempt in range(retry + 1):
        # Check if part already exists (resume)
        current_size = part_path.stat().st_size if part_path.exists() else 0

        if current_size > 0:
            # Resume from current position
            actual_start = start + current_size
            if actual_start > end:
                # Part already complete
                logger.debug("Part %s already complete", part_index)
                return True

            logger.debug(
                "Resuming part %s from byte %s (range: %s-%s)",
                part_index,
                current_size,
                actual_start,
                end,
            )
        else:
            actual_start = start

        headers = {"Range": f"bytes={actual_start}-{end}"}

        try:
            async with client.stream(
                "GET", url, headers=headers, cookies=cj, auth=auth
            ) as response:
                response.raise_for_status()

                # Open file in append mode
                mode = "ab" if current_size > 0 else "wb"
                with Path(part_path).open(mode) as f:
                    async for chunk in response.aiter_bytes():
                        chunk_size = len(chunk)
                        f.write(chunk)

                        # Update progress bar if provided
                        if pbar is not None:
                            pbar.update(chunk_size)

                        # Update metadata periodically (reduced frequency)
                        if f.tell() % (50 * 1024 * 1024) == 0:  # Every 50MB
                            metadata.update_part_progress(part_index)

            # Mark as completed
            metadata.mark_part_completed(part_index)

        except Exception as e:
            if attempt < retry:
                logger.warning(
                    "Error downloading part %s (attempt %s/%s): %s. Retrying...",
                    part_index,
                    attempt + 1,
                    retry + 1,
                    e,
                )
                await asyncio.sleep(1 + random.random() * 2)
                continue

            logger.exception("Error downloading part %s", part_index)
            # Save current progress
            if part_path.exists():
                metadata.update_part_progress(part_index)
            return False
        else:
            return True
    return False


async def _download_data_chunked_httpx(
    client: httpx.AsyncClient,
    url: str,
    file_path: Path,
    chunks: int,
    file_size: int,
    retry: int,
    metadata: _ChunkedDownloadMetadata | None = None,
    authorize_from_browser: bool = False,
) -> bool:
    """Download file using multiple concurrent chunks with httpx.

    Parameters
    ----------
    client : httpx.AsyncClient
        HTTP client
    url : str
        Download URL
    file_path : Path
        Target file path
    chunks : int
        Number of chunks
    file_size : int
        Total file size
    retry : int
        Number of retries
    metadata : _ChunkedDownloadMetadata | None
        Existing metadata for resume, or None for new download
    authorize_from_browser : bool
        Load cookies from browser

    Returns
    -------
    bool
        True if successful

    """
    from ._metadata import _ChunkedDownloadMetadata

    # Create or use existing metadata
    if metadata is None:
        metadata = _ChunkedDownloadMetadata(
            file_path=file_path,
            url=url,
            file_size=file_size,
            chunks=chunks,
            engine="httpx",
            supports_range=True,
        )
        metadata.status = "downloading"
        metadata.save()

    # Determine which parts need downloading
    resume_info = metadata.get_resume_info()
    parts_to_download = resume_info["partial_parts"] + resume_info["pending_parts"]

    if not parts_to_download:
        logger.info("All parts already downloaded, merging...")
        progress_bars = []
    else:
        logger.info("Downloading %s parts concurrently...", len(parts_to_download))

        # Create progress bars for each chunk
        from tqdm import tqdm

        progress_bars = []
        for i, part_idx in enumerate(parts_to_download):
            part = metadata.parts[part_idx]
            chunk_size = part["end"] - part["start"] + 1

            # Get current size for resume support
            part_path = metadata.get_part_path(part_idx)
            current_size = part_path.stat().st_size if part_path.exists() else 0

            pbar = tqdm(
                total=chunk_size,
                initial=current_size,
                unit="B",
                unit_scale=True,
                desc=f"{file_path.name} part {part_idx + 1}/{chunks}",
                position=i,
                leave=False,
                dynamic_ncols=True,
            )
            progress_bars.append(pbar)

        # Create download tasks with progress bars
        tasks = []
        for i, part_idx in enumerate(parts_to_download):
            part = metadata.parts[part_idx]
            part_path = metadata.get_part_path(part_idx)

            task = _download_range_httpx(
                client=client,
                url=url,
                start=part["start"],
                end=part["end"],
                part_path=part_path,
                metadata=metadata,
                part_index=part_idx,
                retry=retry,
                authorize_from_browser=authorize_from_browser,
                pbar=progress_bars[i],
            )
            tasks.append(task)

        # Download all parts concurrently
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Close all progress bars
            for pbar in progress_bars:
                pbar.close()

        # Check for failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Part %s failed: %s", parts_to_download[i], result)
                metadata.status = "failed"
                metadata.save()
                return False
            if not result:
                logger.error("Part %s download failed", parts_to_download[i])
                metadata.status = "failed"
                metadata.save()
                return False

    # All parts downloaded - merge if multiple chunks
    if chunks > 1:
        from . import downloader

        downloader._merge_chunks(file_path, chunks)

    # Mark as completed and cleanup
    metadata.status = "completed"
    metadata.save()
    metadata.cleanup()

    return True


async def _download_range_aiohttp(
    session: aiohttp.ClientSession,
    url: str,
    start: int,
    end: int,
    part_path: Path,
    metadata: _ChunkedDownloadMetadata,
    part_index: int,
    retry: int = 10,
    authorize_from_browser: bool = False,
    pbar: Any | None = None,
) -> bool:
    """Download a specific byte range using aiohttp.

    Parameters
    ----------
    session : aiohttp.ClientSession
        HTTP session
    url : str
        Download URL
    start : int
        Start byte position
    end : int
        End byte position (inclusive)
    part_path : Path
        Path to save this chunk
    metadata : _ChunkedDownloadMetadata
        Metadata object
    part_index : int
        Part index
    retry : int
        Number of retries
    authorize_from_browser : bool
        Load cookies from browser
    pbar : Any | None
        Optional tqdm progress bar to update

    Returns
    -------
    bool
        True if successful

    """
    from . import downloader

    cj = downloader._get_cookiejar(authorize_from_browser)
    auth = downloader.get_netrc_auth(url)
    if auth:
        import aiohttp

        auth = aiohttp.BasicAuth(*auth)

    for attempt in range(retry + 1):
        # Check if part already exists (resume)
        current_size = part_path.stat().st_size if part_path.exists() else 0

        if current_size > 0:
            # Resume from current position
            actual_start = start + current_size
            if actual_start > end:
                # Part already complete
                logger.debug("Part %s already complete", part_index)
                return True

            logger.debug(
                "Resuming part %s from byte %s (range: %s-%s)",
                part_index,
                current_size,
                actual_start,
                end,
            )
        else:
            actual_start = start

        headers = {"Range": f"bytes={actual_start}-{end}"}

        try:
            async with session.get(
                url, headers=headers, cookies=cj, auth=auth
            ) as response:
                response.raise_for_status()

                # Open file in append mode
                mode = "ab" if current_size > 0 else "wb"
                with Path(part_path).open(mode) as f:
                    async for chunk in response.content.iter_any():
                        chunk_size = len(chunk)
                        f.write(chunk)

                        # Update progress bar if provided
                        if pbar is not None:
                            pbar.update(chunk_size)

                        # Update metadata periodically (reduced frequency)
                        if f.tell() % (50 * 1024 * 1024) == 0:  # Every 50MB
                            metadata.update_part_progress(part_index)

            # Mark as completed
            metadata.mark_part_completed(part_index)

        except Exception as e:
            if attempt < retry:
                logger.warning(
                    "Error downloading part %s (attempt %s/%s): %s. Retrying...",
                    part_index,
                    attempt + 1,
                    retry + 1,
                    e,
                )
                await asyncio.sleep(1 + random.random() * 2)
                continue

            logger.exception("Error downloading part %s", part_index)
            # Save current progress
            if part_path.exists():
                metadata.update_part_progress(part_index)
            return False
        else:
            return True
    return False


async def _download_data_chunked_aiohttp(
    session: aiohttp.ClientSession,
    url: str,
    file_path: Path,
    chunks: int,
    file_size: int,
    retry: int,
    metadata: _ChunkedDownloadMetadata | None = None,
    authorize_from_browser: bool = False,
) -> bool:
    """Download file using multiple concurrent chunks with aiohttp.

    Parameters
    ----------
    session : aiohttp.ClientSession
        HTTP session
    url : str
        Download URL
    file_path : Path
        Target file path
    chunks : int
        Number of chunks
    file_size : int
        Total file size
    retry : int
        Number of retries
    metadata : _ChunkedDownloadMetadata | None
        Existing metadata for resume, or None for new download
    authorize_from_browser : bool
        Load cookies from browser

    Returns
    -------
    bool
        True if successful

    """
    from ._metadata import _ChunkedDownloadMetadata

    # Create or use existing metadata
    if metadata is None:
        metadata = _ChunkedDownloadMetadata(
            file_path=file_path,
            url=url,
            file_size=file_size,
            chunks=chunks,
            engine="aiohttp",
            supports_range=True,
        )
        metadata.status = "downloading"
        metadata.save()

    # Determine which parts need downloading
    resume_info = metadata.get_resume_info()
    parts_to_download = resume_info["partial_parts"] + resume_info["pending_parts"]

    if not parts_to_download:
        logger.info("All parts already downloaded, merging...")
        progress_bars = []
    else:
        logger.info("Downloading %s parts concurrently...", len(parts_to_download))

        # Create progress bars for each chunk
        from tqdm import tqdm

        progress_bars = []
        for i, part_idx in enumerate(parts_to_download):
            part = metadata.parts[part_idx]
            chunk_size = part["end"] - part["start"] + 1

            # Get current size for resume support
            part_path = metadata.get_part_path(part_idx)
            current_size = part_path.stat().st_size if part_path.exists() else 0

            pbar = tqdm(
                total=chunk_size,
                initial=current_size,
                unit="B",
                unit_scale=True,
                desc=f"{file_path.name} part {part_idx + 1}/{chunks}",
                position=i,
                leave=False,
                dynamic_ncols=True,
            )
            progress_bars.append(pbar)

        # Create download tasks with progress bars
        tasks = []
        for i, part_idx in enumerate(parts_to_download):
            part = metadata.parts[part_idx]
            part_path = metadata.get_part_path(part_idx)

            task = _download_range_aiohttp(
                session=session,
                url=url,
                start=part["start"],
                end=part["end"],
                part_path=part_path,
                metadata=metadata,
                part_index=part_idx,
                retry=retry,
                authorize_from_browser=authorize_from_browser,
                pbar=progress_bars[i],
            )
            tasks.append(task)

        # Download all parts concurrently
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Close all progress bars
            for pbar in progress_bars:
                pbar.close()

        # Check for failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Part %s failed: %s", parts_to_download[i], result)
                metadata.status = "failed"
                metadata.save()
                return False
            if not result:
                logger.error("Part %s download failed", parts_to_download[i])
                metadata.status = "failed"
                metadata.save()
                return False

    # All parts downloaded - merge if multiple chunks
    if chunks > 1:
        from . import downloader

        downloader._merge_chunks(file_path, chunks)

    # Mark as completed and cleanup
    metadata.status = "completed"
    metadata.save()
    metadata.cleanup()

    return True
