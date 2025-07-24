"""Abstract Base Class for handling Scenes from ASF."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Literal

import geopandas as gpd
import pandas as pd

from data_downloader import downloader
from data_downloader.logging import setup_logger
from data_downloader.utils.baselines import Baselines
from data_downloader.utils.pairs import Pairs

if TYPE_CHECKING:
    from os import PathLike

logger = setup_logger(__name__)


class ASFScenesABC(ABC):
    """Abstract Base Class handling ASF scenes."""

    @abstractmethod
    def __init__(self, geojson: dict) -> None:
        """Initialize ASFScenes with given GeoJSON."""
        self._geojson = geojson

    def __repr__(self) -> str:
        """Return a string representation of the ASFScenes instance."""
        return f"{self.__class__.__name__}(len={len(self)})"

    def __len__(self) -> int:
        """Return the number of scenes in the ASFScenes instance."""
        return len(self.gdf)

    def __getitem__(self, index: int) -> pd.Series:
        """Return the scene at the given index."""
        return self.gdf.iloc[index]

    def __iter__(self) -> Iterator[pd.Series]:
        """Return an iterator over the scenes in the ASFScenes instance."""
        return iter(self.gdf)

    @property
    def repr(self) -> str:
        """String representation of the ASFScenes instance."""
        return self.__repr__()

    @property
    def boundary_file(self) -> str:
        """Boundary file name for saving downloaded scenes."""
        return f"{self.__class__.__name__}.geojson"

    @property
    def geojson(self) -> dict:
        """GeoJSON representation of Scenes."""
        return self._geojson

    @property
    def gdf(self) -> gpd.GeoDataFrame:
        """geopandas.GeoDataFrame representation of Scenes."""
        gdf = gpd.GeoDataFrame.from_features(self.geojson["features"])
        return gdf

    @property
    def url(self) -> pd.Series:
        """List of URLs for downloading Scenes."""
        return self.gdf.loc[:, "url"]

    def to_gdf(self, crs: int | str | None = None) -> gpd.GeoDataFrame:
        """Convert the GeoJSON to a geopandas.GeoDataFrame.

        Parameters
        ----------
        crs : int, str, or None, optional
            The CRS to set for the GeoDataFrame. If None, the CRS will not be
            set. Default is None.

        Returns
        -------
        gpd.GeoDataFrame
            The GeoDataFrame representation of the Scenes.
        """
        gdf = self.gdf
        if crs is not None:
            gdf.set_crs(crs=crs, inplace=True)
        return gdf

    def save_boundaries(
        self,
        folder: PathLike,
        filename: str | None = None,
    ) -> None:
        """Save the boundaries of Scenes to a GeoJSON file.

        Parameters
        ----------
        folder : PathLike
            The folder where the GeoJSON file will be saved.
        filename : str, optional
            The name of the output GeoJSON file. If None, it will use the
            default boundary file name. Default is None.
        """
        folder = Path(folder)
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
        out_file = folder / (filename if filename else self.boundary_file)
        self.gdf.to_file(out_file, driver="GeoJSON")
        logger.info(f"Saved {self.repr} boundaries to {out_file}")

    def download(
        self,
        folder: PathLike,
        urls: list[str] | None = None,
    ) -> None:
        """Download Scenes to the specified folder.

        ..hint::
            The data will be saved in a subfolder named
            `frame_{frame}_path_{path}`. You can specify a parent folder,
            and the subfolder will be created automatically.

        Parameters
        ----------
        folder : PathLike
            The folder where the Scenes will be saved.
        urls : list[str] or None, optional
             List of URLs to download. If None, all URLs will be used.
        """
        folder = Path(folder)
        if urls is None:
            urls = self.url.tolist()
            msg = f"No URLs provided, using all URLs for {self.repr}"
            logger.info(msg, stacklevel=2)
        if not urls or len(urls) == 0:
            msg = f"No URLs found for {self.repr}, skipping."
            logger.warning(msg, stacklevel=2)
            return

        out_dir = folder / self.repr
        if not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Saving {self.repr} to {out_dir}")

        self.save_boundaries(folder=out_dir, filename=self.boundary_file)
        downloader.download_datas(urls, folder=out_dir)
        msg = f"Successfully downloaded {self.repr} to {out_dir}"
        logger.success(msg, stacklevel=2)


class ASFTileScenesABC(ASFScenesABC):
    """Abstract Base Class for handling ASF scenes within a tile."""

    _frame: int | None = None
    _path: int | None = None
    _flightDirection: Literal["ASCENDING", "DESCENDING"] | None = None

    def __init__(
        self,
        geojson: dict,
        path: int | None = None,
        frame: int | None = None,
    ) -> None:
        """Initialize ASFTileScenes with given GeoJSON, frame, and path.

        Parameters
        ----------
        geojson : dict
            The GeoJSON representation of the scenes.
        path : int, optional
            The path of the scenes. If None, the path will be inferred from the
            GeoJSON. Default is None.
        frame : int, optional
            The frame of the scenes. If None, the frame will be inferred from the
            GeoJSON. Default is None.
        flightDirection : Literal["ASCENDING", "DESCENDING"], optional
            The flight direction of the scenes. If None, the flight direction will
            be inferred from the GeoJSON. Default is None.
        """
        super().__init__(geojson=geojson)
        self._parse_scenes_info(path=path, frame=frame)

    def _parse_scenes_info(
        self,
        path: int | None = None,
        frame: int | None = None,
    ) -> None:
        """Parse the frame and path from the GeoJSON."""
        if frame is not None:
            self._frame = frame
        else:
            if len(self.gdf) > 0 and "frameNumber" in self.gdf.columns:
                self._frame = self.gdf.iloc[0]["frameNumber"]

        if path is not None:
            self._path = path
        else:
            if len(self.gdf) > 0 and "pathNumber" in self.gdf.columns:
                self._path = self.gdf.iloc[0]["pathNumber"]

        if len(self.gdf) > 0 and "flightDirection" in self.gdf.columns:
            self._flightDirection = self.gdf.iloc[0]["flightDirection"]

    def __repr__(self) -> str:
        """Return a sting representation of the ASFTileScenesABC instance."""
        return (
            f"{self.__class__.__name__}(\n"
            f"    path={self.path},\n"
            f"    frame={self.frame},\n"
            f"    flightDirection={self.flightDirection},\n"
            f"    len={len(self)},\n"
            ")"
        )

    def __scenes_repr__(self) -> str:
        """Return a string representation of the ASFScenes instance."""
        return (
            f"{self.__class__.__name__}_{self.flightDirection}_{self.path}_{self.frame}"
        )

    @property
    def scenes_repr(self) -> str:
        """String representation of the ASFScenes instance."""
        return self.__scenes_repr__()

    @property
    def boundary_file(self) -> str:
        """Boundary file name for saving downloaded scenes."""
        return f"{self.scenes_repr}.geojson"

    @property
    def frame(self) -> int | None:
        """Return the frame of the Sentinel1Scenes instance."""
        return self._frame

    @property
    def path(self) -> int | None:
        """Return the path of the Sentinel1Scenes instance."""
        return self._path

    @property
    def flightDirection(self) -> Literal["ASCENDING", "DESCENDING"] | None:
        """Return the flight direction of the Sentinel1Scenes instance."""
        return self._flightDirection


class ASFTileScenesTimeseries(ASFTileScenesABC):
    """Abstract Base Class for handling ASF scenes within a tile as a timeseries."""

    def _parse_datetime(self) -> pd.DatetimeIndex:
        """Add datetime to the scenes."""
        dates_str = (
            pd.to_datetime(self.gdf.startTime, format="mixed")
            .map(lambda x: x.strftime("%F"))
            .values
        )
        return pd.to_datetime(dates_str)

    @property
    def datetime(self) -> pd.DatetimeIndex:
        """Return the datetime of the scenes."""
        return self._parse_datetime()

    @property
    def granules(self) -> list[str]:
        """Return the granules of the scenes."""
        return pd.Series(self.gdf.sceneName.values, index=self.datetime)


class ASFTileScenesPairs(ASFTileScenesABC):
    """Abstract Base Class for handling ASF scenes within a tile as a pairs of dates."""

    @abstractmethod
    def _parse_pairs(self) -> Pairs:
        """Add pairs of dates to the scenes."""

    @abstractmethod
    def _parse_baselines(self) -> Baselines:
        """Add baselines to the scenes."""

    @property
    def pairs(self) -> Pairs:
        """Return the pairs of dates of the scenes."""
        return self._parse_pairs()

    @property
    def baselines(self) -> Baselines:
        """Return the baselines of the scenes."""
        return self._parse_baselines()
