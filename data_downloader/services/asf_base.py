"""Abstract Base Class for handling Scenes from ASF."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import geopandas as gpd
import pandas as pd

from data_downloader import downloader
from data_downloader.logging import setup_logger

if TYPE_CHECKING:
    from os import PathLike

logger = setup_logger(__name__)


class ASFScenesABC(ABC):
    """Abstract Base Class handling ASF scenes."""

    @abstractmethod
    def __init__(self, geojson: dict) -> None:
        """Initialize ASFScenes with given GeoJSON."""
        self._geojson = geojson

    @abstractmethod
    def __scene_repr__(self) -> str:
        """Return a string representation of the ASFScenes instance."""
        pass

    def __str__(self) -> str:
        """Return a string representation of the ASFScenes instance."""
        return self.repr

    @property
    def repr(self) -> str:
        """String representation of the ASFScenes instance."""
        return self.__scene_repr__()

    @property
    def boundary_file(self) -> str:
        """Boundary file name for saving downloaded scenes."""
        return f"{self.repr}.geojson"

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
