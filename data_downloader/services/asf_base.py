"""Abstract Base Class for handling Scenes from ASF."""

from __future__ import annotations

import json
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import asf_search as asf
import geopandas as gpd
import pandas as pd

from data_downloader import downloader
from data_downloader.logging import setup_logger
from data_downloader.utils.tools import safe_repr

if TYPE_CHECKING:
    from collections.abc import Iterator
    from os import PathLike

    from typing_extensions import Protocol, Self

    from data_downloader.utils.baselines import Baselines
    from data_downloader.utils.pairs import Pairs

    class ASFSearchResultsLike(Protocol):
        """Protocol for ASF search-like results."""

        def geojson(self) -> dict[str, Any]:
            """Return GeoJSON as a dictionary."""


logger = setup_logger(__name__)


class ASFScenes:
    """Abstract Base Class handling ASF scenes."""

    @staticmethod
    def _validate_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
        """Validate GeoJSON input format.

        Parameters
        ----------
        geojson : dict[str, Any]
            GeoJSON dictionary expected to contain a ``features`` list.

        Returns
        -------
        dict[str, Any]
            Validated GeoJSON dictionary.

        Raises
        ------
        TypeError
            If ``geojson`` is not a dictionary, or ``features`` is not a list.
        ValueError
            If ``features`` does not exist in ``geojson``.

        """
        if not isinstance(geojson, dict):
            msg = "The input `geojson` must be a dictionary."
            logger.error("%s Got type: %s", msg, type(geojson).__name__, stacklevel=2)
            raise TypeError(msg)

        if "features" not in geojson:
            msg = "The input `geojson` must contain the `features` field."
            logger.error(
                "%s Available keys: %s",
                msg,
                safe_repr(list(geojson.keys())),
                stacklevel=2,
            )
            raise ValueError(msg)

        if not isinstance(geojson["features"], list):
            msg = "The `features` field in `geojson` must be a list."
            logger.error(
                "%s Got type: %s",
                msg,
                type(geojson["features"]).__name__,
                stacklevel=2,
            )
            raise TypeError(msg)

        return geojson

    def __init__(self, geojson: dict[str, Any], sort: bool = True) -> None:
        """Initialize ASFScenes with given geojson.

        Parameters
        ----------
        geojson : dict[str, Any]
            The GeoJSON representation of the scenes from
            asf_search.
        sort : bool, optional
            Whether to sort the scenes by datetime. Default is True.

        Raises
        ------
        TypeError
            If ``geojson`` is not a dictionary, or ``features`` is not a list.
        ValueError
            If ``features`` does not exist in ``geojson``.

        """
        geojson = self._validate_geojson(geojson)

        if sort:
            try:
                gdf = gpd.GeoDataFrame.from_features(geojson["features"])
            except Exception:
                logger.exception(
                    "Failed to parse GeoJSON features when initializing %s.",
                    self.__class__.__name__,
                    stacklevel=2,
                )
                raise

            if "startTime" in gdf.columns:
                gdf.sort_values(by="startTime", inplace=True)
                geojson = json.loads(gdf.to_json())
            else:
                logger.warning(
                    "Column `startTime` not found for %s. Skip sorting.",
                    self.__class__.__name__,
                    stacklevel=2,
                )
        self._geojson = geojson

    @classmethod
    def from_asf_search(
        cls,
        results: ASFSearchResultsLike,
        sort: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Initialize ASFScenes from asf_search.ASFSearchResults.

        Parameters
        ----------
        results : ASFSearchResultsLike
            The ASF search results object from asf_search.
        sort : bool, optional
            Whether to sort the scenes by datetime. Default is True.
        **kwargs : Any, optional
            Additional keyword arguments passed to class constructor.

        Returns
        -------
        Self
            An instance of ASFScenes (or subclass) initialized from the
            search results.

        Raises
        ------
        TypeError
            If ``results`` does not provide a callable ``geojson`` method.

        Examples
        --------
        >>> import asf_search as asf
        >>> results = asf.search(
        ...     platform=asf.PLATFORM.SENTINEL1A,
        ...     processingLevel=asf.PRODUCT_TYPE.SLC,
        ...     intersectsWith="POINT(-100 40)",
        ... )
        >>> scenes = ASFScenes.from_asf_search(results)

        """
        geojson_func = getattr(results, "geojson", None)
        if not callable(geojson_func):
            msg = "The input `results` must provide a callable `geojson()` method."
            logger.error("%s Got: %s", msg, safe_repr(results), stacklevel=2)
            raise TypeError(msg)

        try:
            geojson = geojson_func()
        except Exception:
            logger.exception(
                "Failed to convert ASF search results to GeoJSON. Results: %s",
                safe_repr(results),
                stacklevel=2,
            )
            raise

        return cls(geojson=geojson, sort=sort, **kwargs)

    @classmethod
    def from_gdf(
        cls,
        gdf: gpd.GeoDataFrame,
        sort: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Initialize ASFScenes from a geopandas.GeoDataFrame.

        Parameters
        ----------
        gdf : gpd.GeoDataFrame
            The GeoDataFrame containing ASF scene data. Must have a
            'startTime' column for sorting.
        sort : bool, optional
            Whether to sort the scenes by datetime. Default is True.
        **kwargs : Any, optional
            Additional keyword arguments passed to class constructor.

        Returns
        -------
        Self
            An instance of ASFScenes (or subclass) initialized from the
            GeoDataFrame.

        Raises
        ------
        TypeError
            If ``gdf`` is not a ``geopandas.GeoDataFrame``.

        Examples
        --------
        >>> import geopandas as gpd
        >>> gdf = gpd.read_file("scenes.geojson")
        >>> scenes = ASFScenes.from_gdf(gdf)

        """
        if not isinstance(gdf, gpd.GeoDataFrame):
            msg = "The input `gdf` must be a geopandas.GeoDataFrame."
            logger.error("%s Got type: %s", msg, type(gdf).__name__, stacklevel=2)
            raise TypeError(msg)

        try:
            geojson = json.loads(gdf.to_json())
        except Exception:
            logger.exception(
                "Failed to convert GeoDataFrame to GeoJSON. Columns: %s",
                safe_repr(list(gdf.columns)),
                stacklevel=2,
            )
            raise

        return cls(geojson=geojson, sort=sort, **kwargs)

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
        return repr(self)

    def __scenes_repr__(self) -> str:
        """Return a string representation of the ASFScenes instance."""
        return self.__class__.__name__

    @property
    def scenes_repr(self) -> str:
        """String representation of the ASFScenes instance."""
        return self.__scenes_repr__()

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

    @property
    def dates(self) -> pd.DatetimeIndex:
        """Acquisition dates for the Scenes."""
        # dates format in df_asf are mixed, convert them to standard date format
        dates_str = (
            pd.to_datetime(self.gdf.startTime, format="mixed")
            .map(lambda x: x.strftime("%F"))
            .values
        )
        return pd.to_datetime(dates_str)

    @property
    def granules(self) -> pd.Series:
        """List of granules for downloading Scenes."""
        return pd.Series(self.gdf.fileID.values, index=self.dates)

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
        out_file = folder / (filename or self.boundary_file)
        self.gdf.to_file(out_file, driver="GeoJSON")
        logger.info("Saved %s boundaries to %s", self.repr, out_file)

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
        if urls is not None and len(urls) == 0:
            msg = f"No URLs found for {self.scenes_repr}, skipping."
            logger.warning(msg, stacklevel=2)
            return

        out_dir = folder / self.scenes_repr
        if not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Saving {self.scenes_repr} to {out_dir}")

        self.save_boundaries(folder=out_dir, filename=self.boundary_file)
        downloader.download_datas(urls, folder=out_dir)
        msg = f"Successfully downloaded {self.scenes_repr} to {out_dir}"
        logger.success(msg, stacklevel=2)


class ASFBurstScenes(ASFScenes):
    """Abstract Base Class handling ASF burst scenes."""

    def __post_init__(self) -> None:
        """Post-initialization for burst columns."""
        if "burst" not in self.gdf.columns:
            msg = "The input geojson does not contain 'burst' column."
            raise ValueError(msg)

    @property
    def gdf_burst(self) -> pd.DataFrame:
        """Return the burst information as a DataFrame."""
        gdf = super().gdf
        return pd.DataFrame(gdf.burst.to_list(), index=gdf.index)

    @property
    def gdf(self) -> gpd.GeoDataFrame:
        """Return the GeoDataFrame with burst information."""
        return super().gdf.join(self.gdf_burst)

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


class ASFTileScenesABC(ASFScenes):
    """Abstract Base Class for handling ASF scenes within a tile."""

    _frame: int | None = None
    _path: int | None = None
    _flightDirection: Literal["ASCENDING", "DESCENDING"] | None = None

    def __init__(
        self,
        geojson: dict[str, Any],
        path: int | None = None,
        frame: int | None = None,
        sort: bool = True,
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
        sort : bool, optional
            Whether to sort the scenes by datetime. Default is True.
        flightDirection : Literal["ASCENDING", "DESCENDING"], optional
            The flight direction of the scenes. If None, the flight direction will
            be inferred from the GeoJSON. Default is None.

        """
        super().__init__(geojson=geojson, sort=sort)
        self._parse_scenes_info(path=path, frame=frame)

    def _parse_scenes_info(
        self,
        path: int | None = None,
        frame: int | None = None,
    ) -> None:
        """Parse the frame and path from the GeoJSON."""
        if frame is not None:
            self._frame = frame
        elif len(self.gdf) > 0 and "frameNumber" in self.gdf.columns:
            self._frame = self.gdf.iloc[0]["frameNumber"]

        if path is not None:
            self._path = path
        elif len(self.gdf) > 0 and "pathNumber" in self.gdf.columns:
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
    def granules(self) -> pd.Series:
        """Return the granules of the scenes."""
        return pd.Series(self.gdf.sceneName.values, index=self.datetime)

    @classmethod
    def from_reference_granule(cls, granule: str) -> Self:
        scenes = asf.baseline_search.stack_from_id(granule)
        return cls.from_asf_search(scenes)


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
