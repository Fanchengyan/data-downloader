"""Metadata management for chunked downloads with resume support."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .logging import setup_logger, tqdm_handler

logger = setup_logger(__name__, handler=tqdm_handler)


class _ChunkedDownloadMetadata:
    """Manage metadata for chunked downloads with resume support.

    This class handles .download_meta/{filename}.json files that track
    download progress for both single-chunk and multi-chunk downloads.

    Parameters
    ----------
    file_path : Path
        Target file path
    url : str
        Download URL
    file_size : int
        Total file size in bytes
    chunks : int
        Number of chunks (1 for non-chunked downloads)
    engine : str
        Download engine ("requests", "httpx", "aiohttp")
    supports_range : bool
        Whether server supports Range requests

    Attributes
    ----------
    meta_dir : Path
        Hidden directory for metadata (.download_meta)
    meta_file : Path
        Path to metadata JSON file

    """

    def __init__(
        self,
        file_path: Path,
        url: str,
        file_size: int,
        chunks: int,
        engine: str,
        supports_range: bool = True,
    ):
        self.file_path = Path(file_path)
        self.url = url
        self.file_size = file_size
        self.chunks = chunks
        self.engine = engine
        self.supports_range = supports_range

        # Metadata storage location
        self.meta_dir = self.file_path.parent / ".download_meta"
        self.meta_file = self.meta_dir / f"{self.file_path.name}.json"

        # Initialize parts info
        chunk_size = file_size // chunks if chunks > 0 else file_size
        self.parts = []
        for i in range(chunks):
            start = i * chunk_size
            end = file_size - 1 if i == chunks - 1 else (i + 1) * chunk_size - 1
            self.parts.append({
                "index": i,
                "start": start,
                "end": end,
                "status": "pending",
                "size": 0,
            })

        self.status = "pending"
        self.checksum = None
        self.started_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.updated_at = self.started_at

    def save(self) -> None:
        """Save metadata to JSON file."""
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.updated_at = dt.datetime.now(dt.timezone.utc).isoformat()

        data = {
            "version": "1.0",
            "url": self.url,
            "file_name": self.file_path.name,
            "file_size": self.file_size,
            "chunks": self.chunks,
            "engine": self.engine,
            "supports_range": self.supports_range,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "parts": self.parts,
            "checksum": self.checksum,
        }

        with Path(self.meta_file).open("w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> _ChunkedDownloadMetadata | None:
        """Load metadata from JSON file.

        Parameters
        ----------
        file_path : Path
            Target file path

        Returns
        -------
        _ChunkedDownloadMetadata | None
            Loaded metadata object or None if not found

        """
        meta_dir = file_path.parent / ".download_meta"
        meta_file = meta_dir / f"{file_path.name}.json"

        if not meta_file.exists():
            return None

        try:
            with Path(meta_file).open() as f:
                data = json.load(f)

            # Create instance
            obj = cls(
                file_path=file_path,
                url=data["url"],
                file_size=data["file_size"],
                chunks=data["chunks"],
                engine=data["engine"],
                supports_range=data.get("supports_range", True),
            )

            # Restore saved state
            obj.parts = data["parts"]
            obj.status = data["status"]
            obj.checksum = data.get("checksum")
            obj.started_at = data["started_at"]
            obj.updated_at = data["updated_at"]

            return obj

        except Exception as e:
            logger.warning(f"Failed to load metadata for {file_path.name}: {e}")
            return None

    def is_compatible(self, new_chunks: int | None, new_url: str) -> bool:
        """Check if new download parameters are compatible.

        Parameters
        ----------
        new_chunks : int | None
            New chunks parameter
        new_url : str
            New URL

        Returns
        -------
        bool
            True if compatible (can resume), False otherwise

        """
        # URL must match
        if new_url != self.url:
            return False

        # If chunks not specified, always compatible
        if new_chunks is None:
            return True

        # Chunks must match
        return new_chunks == self.chunks

    def get_part_path(self, part_index: int) -> Path:
        """Get path for a part file.

        Parameters
        ----------
        part_index : int
            Part index

        Returns
        -------
        Path
            Path to part file (e.g., file.zip.part0)

        """
        if self.chunks == 1:
            # Single chunk uses the target file directly
            return self.file_path
        return self.file_path.parent / f"{self.file_path.name}.part{part_index}"

    def mark_part_completed(self, part_index: int) -> None:
        """Mark a part as completed.

        Parameters
        ----------
        part_index : int
            Part index

        """
        self.parts[part_index]["status"] = "completed"
        part_path = self.get_part_path(part_index)
        if part_path.exists():
            self.parts[part_index]["size"] = part_path.stat().st_size
        self.save()

    def update_part_progress(self, part_index: int) -> None:
        """Update progress for a part.

        Parameters
        ----------
        part_index : int
            Part index

        """
        part_path = self.get_part_path(part_index)
        if part_path.exists():
            self.parts[part_index]["size"] = part_path.stat().st_size
            if self.parts[part_index]["status"] == "pending":
                self.parts[part_index]["status"] = "partial"

    def get_resume_info(self) -> dict:
        """Get information needed for resuming download.

        Returns
        -------
        dict
            {
                "completed_parts": [0, 1, ...],
                "partial_parts": [2, ...],
                "pending_parts": [3, 4, ...],
                "total_downloaded": bytes,
                "progress_percent": 0-100
            }

        """
        completed = []
        partial = []
        pending = []
        total_downloaded = 0

        for part in self.parts:
            total_downloaded += part["size"]
            if part["status"] == "completed":
                completed.append(part["index"])
            elif part["status"] == "partial":
                partial.append(part["index"])
            else:
                pending.append(part["index"])

        return {
            "completed_parts": completed,
            "partial_parts": partial,
            "pending_parts": pending,
            "total_downloaded": total_downloaded,
            "progress_percent": (total_downloaded / self.file_size * 100)
            if self.file_size > 0
            else 0,
        }

    def cleanup(self, keep_parts: bool = False) -> None:
        """Clean up metadata and optionally part files.

        Parameters
        ----------
        keep_parts : bool
            If True, keep part files (only remove metadata)

        """
        # Remove metadata file
        if self.meta_file.exists():
            self.meta_file.unlink()

        # Remove part files if requested
        if not keep_parts and self.chunks > 1:
            for i in range(self.chunks):
                part_path = self.get_part_path(i)
                if part_path.exists():
                    part_path.unlink()

        # Remove meta_dir if empty
        if self.meta_dir.exists() and not any(self.meta_dir.iterdir()):
            self.meta_dir.rmdir()
