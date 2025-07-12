"""Module for handling ALOS-2 scenes from ASF."""

from __future__ import annotations

from typing import TYPE_CHECKING

import asf_search as asf

from data_downloader.logging import setup_logger

from .asf_base import ASFScenesABC

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)


class ALOS2Scenes(ASFScenesABC):
    """Class for handling ALOS-2 scenes from ASF."""

    def __init__(self, frame: int, path: int, maxResults=1000) -> None:
        """Initialize ALOS2Scenes with given frame and path."""
        self.frame = frame
        self.path = path
        results = asf.search(
            platform="ALOS-2",
            asfFrame=self.frame,
            relativeOrbit=self.path,
            maxResults=maxResults,
        )
        msg = f"{len(results)} results found for (frame={self.frame}, path={self.path})"
        logger.info(msg, stacklevel=2)
        
        super().__init__(geojson=results.geojson())


    def __repr__(self) -> str:
        """Return a string representation of the ALOS2Scenes instance."""
        return f"ALOS2Scenes(frame={self.frame}, path={self.path})"

    def __str__(self) -> str:
        """Return a string representation of the ALOS2Scenes instance."""
        return self.repr

    def __scene_repr__(self) -> str:
        return f"ALOS2_{self.frame}_{self.path}"
