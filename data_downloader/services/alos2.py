"""Module for handling ALOS-2 scenes from ASF."""

from __future__ import annotations

from typing import TYPE_CHECKING

import asf_search as asf

from data_downloader.logging import setup_logger

from .asf_base import ASFTileScenesTimeseries

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)


class ALOS2TileScenes(ASFTileScenesTimeseries):
    """Class for handling ALOS-2 scenes from ASF."""

    def __scenes_repr__(self) -> str:
        return f"ALOS2_{self.path}_{self.frame}"

    @classmethod
    def from_path_frame(cls, path: int, frame: int, maxResults=1000) -> ALOS2TileScenes:
        """Create an ALOS2TileScenes instance from a path and frame."""
        cls._path = path
        cls._frame = frame

        results = asf.search(
            platform=asf.PLATFORM.ALOS2,
            relativeOrbit=cls.path,
            asfFrame=cls.frame,
            maxResults=maxResults,
        )
        msg = f"{len(results)} results found for (frame={cls.frame}, path={cls.path})"
        logger.info(msg, stacklevel=2)
        return cls(geojson=results.geojson())
