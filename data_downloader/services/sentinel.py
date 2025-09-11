from __future__ import annotations

import asf_search as asf

from data_downloader.logging import setup_logger
from data_downloader.services.asf_base import ASFTileScenesTimeseries

logger = setup_logger(__name__)


class Sentinel1TileScenes(ASFTileScenesTimeseries):
    """Class for handling Sentinel-1 stackable scenes from ASF."""

    @classmethod
    def from_path_frame(
        cls, path: int, frame: int, maxResults=10000
    ) -> Sentinel1TileScenes:
        """Create a SentinelScenes instance from a frame and path."""
        cls._frame = frame
        cls._path = path
        results = asf.search(
            platform=asf.PLATFORM.SENTINEL1,
            relativeOrbit=path,
            asfFrame=frame,
            maxResults=maxResults,
        )
        msg = f"{len(results)} results found for (frame={frame}, path={path})"
        logger.info(msg, stacklevel=2)
        return cls(geojson=results.geojson(), path=path, frame=frame)

class Sentinel1BurstTileScenes(ASFTileScenesTimeseries):
    """Class for handling Sentinel-1 stackable scenes from ASF."""

    @classmethod
    def from_path_frame(
        cls, path: int, frame: int, maxResults=10000
    ) -> Sentinel1TileScenes:
        """Create a SentinelScenes instance from a frame and path."""
        cls._frame = frame
        cls._path = path
        results = asf.search(
            platform=asf.PLATFORM.SENTINEL1,
            relativeOrbit=cls.path,
            asfFrame=cls.frame,
            maxResults=maxResults,
        )
        msg = f"{len(results)} results found for (frame={cls.frame}, path={cls.path})"
        logger.info(msg, stacklevel=2)
        return cls(geojson=results.geojson(), path=path, frame=frame)