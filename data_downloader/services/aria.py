from __future__ import annotations

from typing import Literal

import asf_search as asf
from pandas._typing import ArrayLike
from shapely.geometry import Point

from data_downloader.logging import setup_logger

from ..utils.baselines import Baselines
from ..utils.pairs import Pairs
from .asf_base import ASFScenesABC

logger = setup_logger(__name__)


class ARIAScenesSTD(ASFScenesABC):
    """Class for ARIA scenes with processingLevel of GUNW_STD from ASF.

    Scenes are searched based on the ASF scene IDs.
    """

    def __init__(self, scenes: list[str]) -> None:
        """Initialize ARIAScenesSTD object with ASF scenes.

        Parameters
        ----------
        scenes: list[str]
            List of ASF scene IDs.

        """
        self.scenes = scenes
        geojson = asf.granule_search(
            scenes,
            asf.ASFSearchOptions(
                processingLevel="GUNW_STD",
            ),
        ).geojson()
        if len(geojson) == 0:
            msg = f"No scenes found for given scenes: {scenes}."
            logger.error(msg, stacklevel=2)
            raise ValueError(msg)
        super().__init__(geojson)

    def __repr__(self) -> str:
        return f"ARIAScenesSTD(scenes={len(self.gdf)})"

    def __scene_repr__(self) -> str:
        return "ARIAScenesSTD"

class ARIATileABC(ASFScenesABC):
    """Abstract Base Class for ARIA scenes within a tile.

    Scenes are searched based on the centroid point of the tile (spatial intersection).
    Therefore, the flight direction should be specified to determine the direction
    of the scenes.
    """

    @property
    def pairs(self) -> Pairs:
        """faninsar.Pairs corresponding to ASF scenes."""
        if len(self.gdf) == 0:
            logger.warning("No scenes found for this frame.")
            return Pairs([])
        try:
            from faninsar import Pairs
        except ImportError:
            msg = "faninsar is not installed. Please install it to use ARIAFrame.pairs."
            logger.error(msg, stacklevel=2)
            raise ImportError(msg)
        return Pairs.from_names(self.gdf.fileID.apply(lambda x: x.split("-")[6]))

    @property
    def perpendicular_baselines(self) -> ArrayLike:
        """Perpendicular baselines corresponding to ASF scenes."""
        return self.gdf.perpendicularBaseline.values

    @property
    def baselines(self) -> Baselines:
        """faninsar.Baselines corresponding to ASF scenes."""
        try:
            from faninsar import Baselines
        except ImportError:
            msg = "faninsar is not installed. Please install it to use ARIAFrame.baselines."
            logger.error(msg, stacklevel=2)
            raise ImportError(msg)
        return Baselines.from_pair_wise(self.pairs, self.perpendicular_baselines)


class ARIASpatialTile(ARIATileABC):
    """Class for ARIAS scenes within a spatial tile.

    Scenes are searched based on the centroid point of the tile (spatial intersection).
    Therefore, the flight direction should be specified to determine the direction
    of the scenes.
    """

    def __init__(
        self,
        centroid_point: list[float],
        flightDirection: Literal["ASCENDING", "DESCENDING"] = "ASCENDING",
        maxResults: int = 10000,
    ) -> None:
        """Initialize ARIAFrame object with given centroid point and flight direction.

        Parameters
        ----------
        centroid_point: list[float]
            Centroid point of frame in [lon, lat] format in WGS84.
        flightDirection: Literal["ASCENDING", "DESCENDING"]
            Flight direction of ASF scenes.
        maxResults: int
            Maximum number of results to return.

        """
        self._centroid = Point(centroid_point).wkt
        self._flightDirection: Literal["ASCENDING", "DESCENDING"] = flightDirection
        geojson = asf.geo_search(
            intersectsWith=self.centroid,
            opts=asf.ASFSearchOptions(
                flightDirection=flightDirection,
                processingLevel="GUNW_STD",
                maxResults=maxResults,
            ),
        ).geojson()
        super().__init__(geojson)

    def __repr__(self) -> str:
        if len(self.gdf) == 0:
            return "ARIASpatialTile(\n  p\n)"
        return (
            "ARIASpatialTile(\n"
            f"  centroid={self.centroid},\n"
            f"  flightDirection={self.flightDirection},\n"
            f"  pairs={len(self.pairs)},\n"
            ")"
        )

    def __scene_repr__(self) -> str:
        return f"ARIASpatialTile_{self.flightDirection}_{self.centroid})"

    @property
    def centroid(self) -> str:
        """Centroid point of the tile in WKT format."""
        return self._centroid

    @property
    def flightDirection(self) -> Literal["ASCENDING", "DESCENDING"]:
        """Flight direction of the scenes."""
        return self._flightDirection
