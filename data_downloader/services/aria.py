from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import asf_search as asf
from shapely.geometry import Point

from data_downloader.logging import setup_logger

from ..utils.baselines import Baselines
from ..utils.pairs import Pairs
from .asf_base import ASFScenesABC

if TYPE_CHECKING:
    import numpy as np

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
    """Abstract Base Class for ARIA scenes within a tile."""

    @property
    def pairs(self) -> Pairs:
        """Pairs corresponding to ASF interferogram scenes."""

        if len(self.gdf) == 0:
            logger.warning("No scenes found for this frame.")
            names = []
        else:
            names = self.gdf.fileID.apply(lambda x: x.split("-")[6]).tolist()
        return Pairs.from_names(names)

    @property
    def perpendicular_baselines(self) -> np.ndarray:
        """Perpendicular baselines corresponding to ASF scenes."""
        return self.gdf.perpendicularBaseline.to_numpy()

    @property
    def baselines(self) -> Baselines:
        """Baselines corresponding to ASF interferogram scenes."""

        return Baselines.from_pair_wise(self.pairs, self.perpendicular_baselines)


class ARIATileCentroidPoint(ARIATileABC):
    """Class for ARIAS scenes within a spatial tile.

    Scenes are searched based on the centroid point of the tile (spatial
    intersection). The flight direction should be specified to determine
    the direction of scenes.
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
        return f"ARIATileCentroidPoint_{self.flightDirection}_{self.centroid})"

    @property
    def centroid(self) -> str:
        """Centroid point of the tile in WKT format."""
        return self._centroid

    @property
    def flightDirection(self) -> Literal["ASCENDING", "DESCENDING"]:
        """Flight direction of the scenes."""
        return self._flightDirection
