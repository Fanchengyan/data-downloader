"""Chunked download implementation with resume support."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from .logging import setup_logger, tqdm_handler

if TYPE_CHECKING:
    import aiohttp
    import httpx

    from ._metadata import _ChunkedDownloadMetadata

logger = setup_logger(__name__, handler=tqdm_handler)


# ============================================================================
# Resume Detection
# ============================================================================


async def _detect_and_resume_download(
    url: str,
    file_path: Path,
    file_size: int,
    chunks: int | None,
    engine: str,
    supports_range: bool,
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
                f"You requested {chunks} chunks, but found existing download with "
                f"{metadata.chunks} chunks"
            )
            logger.info(
                f"Using existing {metadata.chunks} chunks to resume download "
                f"(compatibility mode)"
            )
            logger.info(
                f"To restart with {chunks} chunks, delete: {file_path} and "
                f"{metadata.meta_file}"
            )

    # Compatible or using compatibility mode - check progress
    resume_info = metadata.get_resume_info()

    if resume_info["progress_percent"] >= 100:
        logger.info(f"Download already completed: {file_path.name}")
        metadata.cleanup()
        return metadata.chunks, None

    # Log resume information
    logger.info(f"Detected incomplete download for {file_path.name}")
    logger.info(
        f"Resuming with {metadata.chunks} chunks "
        f"({len(resume_info['completed_parts'])} completed, "
        f"{len(resume_info['partial_parts'])} partial, "
        f"{len(resume_info['pending_parts'])} pending)"
    )
    logger.info(
        f"Progress: {resume_info['progress_percent']:.1f}% already downloaded "
        f"({resume_info['total_downloaded'] / 1024 / 1024:.1f}MB / "
        f"{file_size / 1024 / 1024:.1f}MB)"
    )

    return metadata.chunks, metadata


def _cleanup_orphaned_parts(file_path: Path) -> None:
    """Clean up orphaned part files without metadata.

    Parameters
    ----------
    file_path : Path
        Target file path

    """
    orphaned = []
    for part_file in file_path.parent.glob(f"{file_path.name}.part*"):
        orphaned.append(part_file)

    if orphaned:
        logger.warning(
            f"Found {len(orphaned)} orphaned .part files for {file_path.name} "
            f"without metadata"
        )
        logger.info("These may be from a previous interrupted download")
        logger.info(
            f"Cleaning up orphaned files: {', '.join(p.name for p in orphaned)}"
        )

        for part_file in orphaned:
            part_file.unlink()


# ============================================================================
# Async Chunked Download (HTTPX)
# ============================================================================


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

    Returns
    -------
    bool
        True if successful

    """
    from . import downloader

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
    cj = downloader._get_cookiejar(authorize_from_browser)

    try:
        async with client.stream("GET", url, headers=headers, cookies=cj) as response:
            response.raise_for_status()

            # Open file in append mode
            mode = "ab" if current_size > 0 else "wb"
            with Path(part_path).open(mode) as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

                    # Update metadata periodically
                    if f.tell() % (10 * 1024 * 1024) == 0:  # Every 10MB
                        metadata.update_part_progress(part_index)

        # Mark as completed
        metadata.mark_part_completed(part_index)
        return True

    except Exception as e:
        logger.error("Error downloading part %s: %s", part_index, e)
        # Save current progress
        if part_path.exists():
            metadata.update_part_progress(part_index)
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
    else:
        logger.info(f"Downloading {len(parts_to_download)} parts concurrently...")

        # Create download tasks
        tasks = []
        for part_idx in parts_to_download:
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
            )
            tasks.append(task)

        # Download all parts concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Part {parts_to_download[i]} failed: {result}")
                metadata.status = "failed"
                metadata.save()
                return False
            if not result:
                logger.error(f"Part {parts_to_download[i]} download failed")
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


# ============================================================================
# Async Chunked Download (AIOHTTP)
# ============================================================================


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

    Returns
    -------
    bool
        True if successful

    """
    from . import downloader

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
    cj = downloader._get_cookiejar(authorize_from_browser)

    try:
        async with session.get(url, headers=headers, cookies=cj) as response:
            response.raise_for_status()

            # Open file in append mode
            mode = "ab" if current_size > 0 else "wb"
            with Path(part_path).open(mode) as f:
                async for chunk in response.content.iter_any():
                    f.write(chunk)

                    # Update metadata periodically
                    if f.tell() % (10 * 1024 * 1024) == 0:  # Every 10MB
                        metadata.update_part_progress(part_index)

        # Mark as completed
        metadata.mark_part_completed(part_index)
        return True

    except Exception as e:
        logger.error("Error downloading part %s: %s", part_index, e)
        # Save current progress
        if part_path.exists():
            metadata.update_part_progress(part_index)
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
    else:
        logger.info(f"Downloading {len(parts_to_download)} parts concurrently...")

        # Create download tasks
        tasks = []
        for part_idx in parts_to_download:
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
            )
            tasks.append(task)

        # Download all parts concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Part {parts_to_download[i]} failed: {result}")
                metadata.status = "failed"
                metadata.save()
                return False
            if not result:
                logger.error(f"Part {parts_to_download[i]} download failed")
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
