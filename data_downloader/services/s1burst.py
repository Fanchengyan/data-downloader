"""Module for handling Sentinel-1 burst scenes from ASF."""

from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import asf_search as asf
import numpy as np
import pandas as pd
from tqdm import tqdm

from data_downloader import downloader
from data_downloader.logging import setup_logger
from data_downloader.services.asf_base import ASFScenes
from data_downloader.services.hyp3 import HyP3JobsBurst, HyP3JobsMultiBurst, HyP3Service

try:
    from burst2safe.safe import Safe
    from burst2safe.utils import BurstInfo
except ImportError as e:
    msg = (
        "burst2safe is required for data_downloader.services. "
        "Please install it via 'pip install data_downloader[services]'."
    )
    raise ImportError(msg) from e

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from geopandas import GeoDataFrame
    from matplotlib.axes import Axes
    from numpy.typing import NDArray
    from shapely.geometry.base import BaseGeometry

    from data_downloader.utils import Pairs


logger = setup_logger(__name__)


class S1BurstScenes(ASFScenes):
    """Class for handling Sentinel-1 burst scenes from ASF.

    This class inherits from the ASFBurstScenes class and adds functionality for
    converting burst scenes to SAFE format and submitting jobs to HyP3.
    """

    def __repr__(self) -> str:
        """Return the string representation of the object."""
        num_safes = []
        for burst_id in self.full_burst_ids:
            gdf_burst = self.gdf_burst[self.gdf_burst.fullBurstID == burst_id]
            num_safes.append(len(gdf_burst))
        return (
            f"S1Burst2SafeScenes(\n"
            f"  scenes={len(self.gdf)},\n"
            f"  bursts={len(self.full_burst_ids)},\n"
            f"  safes={max(num_safes)},\n"
            ")"
        )

    def __post_init__(self) -> None:
        """Post-initialization for burst columns."""
        if "fullBurstID" not in self.gdf_burst.columns:
            msg = "The input geojson does not contain burst information 'fullBurstID'."
            raise ValueError(msg)

    @classmethod
    def _convert_intersects_with(cls, intersectsWith: Any) -> str:
        """Convert various geometry types to WKT string.

        Parameters
        ----------
        intersectsWith : str, BaseGeometry, or GeoDataFrame
            A WKT string, shapely geometry, or GeoDataFrame to convert.

        Returns
        -------
        str
            WKT string representation of the geometry.

        Raises
        ------
        TypeError
            If the input type is not supported.

        """
        if isinstance(intersectsWith, str):
            return intersectsWith
        if hasattr(intersectsWith, "wkt"):
            # shapely BaseGeometry
            return intersectsWith.wkt
        if hasattr(intersectsWith, "unary_union"):
            # GeoDataFrame / GeoSeries
            return intersectsWith.unary_union.wkt
        msg = (
            f"Unsupported type for intersectsWith: {type(intersectsWith).__name__}. "
            "Expected str (WKT), shapely geometry, or GeoDataFrame."
        )
        raise TypeError(msg)

    @classmethod
    def from_search(
        cls,
        *,
        intersectsWith: str | BaseGeometry | GeoDataFrame | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        flightDirection: Literal["ASCENDING", "DESCENDING"] | None = None,
        polarization: Literal["VV", "VV+VH", "HH", "HH+HV"] | None = None,
        relativeOrbit: int | None = None,
        fullBurstID: str | None = None,
        maxResults: int = 10000,
    ) -> S1BurstScenes:
        """Create an S1BurstScenes instance by searching ASF.

        Wraps ``asf_search.search()`` with ``platform=SENTINEL1`` and
        ``processingLevel=BURST`` pre-configured.

        Parameters
        ----------
        intersectsWith : str, BaseGeometry, GeoDataFrame, or None, optional
            Area of interest as a WKT string, shapely geometry, or
            GeoDataFrame. Automatically converted to WKT. Default is None.
        start : str, datetime, or None, optional
            Start date for temporal filtering. Default is None.
        end : str, datetime, or None, optional
            End date for temporal filtering. Default is None.
        flightDirection : {'ASCENDING', 'DESCENDING'}, optional
            Satellite flight direction. Default is None.
        polarization : {'VV', 'VV+VH', 'HH', 'HH+HV'}, optional
            Polarization mode. Default is None.
        relativeOrbit : int or None, optional
            Relative orbit number. Default is None.
        fullBurstID : str or None, optional
            Full burst ID to search for. Default is None.
        maxResults : int, optional
            Maximum number of results. Default is 10000.

        Returns
        -------
        S1BurstScenes
            An instance initialized from the search results.

        Examples
        --------
        >>> scenes = S1BurstScenes.from_search(
        ...     intersectsWith="POINT(-118.2 34.0)",
        ...     start="2023-01-01",
        ...     end="2023-06-01",
        ...     flightDirection="ASCENDING",
        ... )

        """
        kwargs: dict[str, Any] = {
            "platform": asf.PLATFORM.SENTINEL1,
            "processingLevel": asf.PRODUCT_TYPE.BURST,
            "maxResults": maxResults,
        }

        if intersectsWith is not None:
            kwargs["intersectsWith"] = cls._convert_intersects_with(intersectsWith)
        if start is not None:
            kwargs["start"] = start
        if end is not None:
            kwargs["end"] = end
        if flightDirection is not None:
            kwargs["flightDirection"] = flightDirection
        if polarization is not None:
            kwargs["polarization"] = polarization
        if relativeOrbit is not None:
            kwargs["relativeOrbit"] = relativeOrbit
        if fullBurstID is not None:
            kwargs["fullBurstID"] = fullBurstID

        results = asf.search(**kwargs)
        logger.info("%d burst results found.", len(results))
        return cls.from_search_results(results)

    @property
    def gdf_burst(self) -> pd.DataFrame:
        """Return DataFrame with burst information in columns."""
        gdf = super().gdf
        df_burtst = pd.DataFrame(gdf.burst.to_list(), index=gdf.index)
        return pd.merge(gdf, df_burtst, left_index=True, right_index=True)

    @property
    def full_burst_ids(self) -> NDArray[np.str_]:
        """Return the full burst IDs."""
        return self.gdf_burst.fullBurstID.unique().astype(str)

    @property
    def absolute_orbit(self) -> NDArray[np.uint32]:
        """Return the absolute orbits."""
        return self.gdf_burst.orbit.unique().astype(np.uint32)

    @property
    def relative_orbit(self) -> NDArray[np.uint32]:
        """Return the relative orbits."""
        return self.gdf_burst.pathNumber.unique().astype(np.uint32)

    def sel(self, full_burst_ids: str | Iterable[str]) -> S1BurstScenes:
        """Select scenes by fullBurstID, returning a new instance.

        Parameters
        ----------
        full_burst_ids : str or Iterable[str]
            One or more fullBurstID values to keep
            (e.g. ``"018_038438_IW2"`` or
            ``["018_038438_IW2", "018_038439_IW1"]``).

        Returns
        -------
        Self
            A new ``S1BurstScenes`` containing only the selected bursts.

        Raises
        ------
        ValueError
            If none of the specified burst IDs exist in the scenes.

        """
        if isinstance(full_burst_ids, str):
            full_burst_ids = [full_burst_ids]
        full_burst_ids = set(full_burst_ids)

        mask = self.gdf_burst.fullBurstID.isin(full_burst_ids)
        if not mask.any():
            msg = (
                f"None of the specified burst IDs found. "
                f"Available: {list(self.full_burst_ids)}"
            )
            raise ValueError(msg)

        return type(self).from_gdf(self.gdf[mask], sort=False)

    def drop_incomplete(self) -> S1BurstScenes:
        """Drop dates with incomplete burst coverage.

        Groups scenes by acquisition date and counts the number of bursts
        per date. Dates whose burst count differs from the mode (most
        common count) are dropped.

        Returns
        -------
        Self
            A new ``S1BurstScenes`` with incomplete dates removed.

        """
        gdf = self.gdf
        dates = self.dates

        counts = gdf.groupby(dates).size()
        expected = counts.mode().iloc[0]

        if (counts == expected).all():
            return self

        valid_dates = counts[counts == expected].index
        mask = dates.isin(valid_dates)

        dropped = counts[counts != expected]
        logger.debug(
            "Dropped %d date(s) with incomplete bursts (expected %d per date): %s",
            len(dropped),
            expected,
            dropped.to_dict(),
        )
        return type(self).from_gdf(self.gdf[mask], sort=False)

    def submit_burst_jobs(
        self,
        pairs: Pairs,
        granules: pd.Series | None = None,
        service: HyP3Service | None = None,
        skip_existing: bool = True,
        name: str | None = None,
        apply_water_mask: bool = False,
        looks: Literal["20x4", "10x2", "5x1"] = "20x4",
    ) -> None:
        """Submit burst jobs to the HyP3 service.

        Parameters
        ----------
        pairs : Pairs
            Date pairs to submit.
        granules : pd.Series, optional
            Granules Series (index=date, values=fileID). If None, uses
            ``self.granules``.
        service : HyP3Service, optional
            HyP3 service instance. If None, creates a new one.
        skip_existing : bool, optional
            Skip pairs already submitted on the service, by default True.
        name : str, optional
            A name for the job.
        apply_water_mask : bool, optional
            Sets pixels over coastal waters and large inland waterbodies
            as invalid for phase unwrapping, by default False.
        looks : {'20x4', '10x2', '5x1'}, optional
            Number of looks to take in range and azimuth,
            by default '20x4'.

        """
        if service is None:
            service = HyP3Service()
        granules = granules if granules is not None else self.granules

        if len(granules.index.unique()) < len(granules.index):
            msg = "Granules must be unique. Try to use submit_multi_burst_jobs instead."
            logger.error(msg, stacklevel=2)
            raise ValueError(msg)

        job_parameters = {
            "name": name,
            "apply_water_mask": apply_water_mask,
            "looks": looks,
        }
        hyp3_jobs = HyP3JobsBurst(service, granules=granules)
        hyp3_jobs.job_parameters = job_parameters
        hyp3_jobs.submit_jobs(pairs, skip_existing=skip_existing)

    def submit_multi_burst_jobs(
        self,
        pairs: Pairs,
        granules: pd.Series | None = None,
        service: HyP3Service | None = None,
        skip_existing: bool = True,
        name: str | None = None,
        apply_water_mask: bool = False,
        looks: Literal["20x4", "10x2", "5x1"] = "20x4",
    ) -> None:
        """Submit multi-burst jobs to the HyP3 service.

        Each date pair is submitted as a single ``INSAR_ISCE_MULTI_BURST``
        job containing all burst granules for that date. Requires that
        granules have duplicated dates (multiple burst IDs per date) and
        that each date has the same number of bursts.

        If granule dates are unique (only one burst per date), falls back
        to ``submit_burst_jobs`` automatically.

        Parameters
        ----------
        pairs : Pairs
            Date pairs to submit.
        granules : pd.Series, optional
            Granules Series (index=date, values=fileID). If None, uses
            ``self.granules``.
        service : HyP3Service, optional
            HyP3 service instance. If None, creates a new one.
        skip_existing : bool, optional
            Skip pairs already submitted on the service, by default True.
        name : str, optional
            A name for the job.
        apply_water_mask : bool, optional
            Sets pixels over coastal waters and large inland waterbodies
            as invalid for phase unwrapping, by default False.
        looks : {'20x4', '10x2', '5x1'}, optional
            Number of looks to take in range and azimuth,
            by default '20x4'.

        """
        if service is None:
            service = HyP3Service()
        granules = granules if granules is not None else self.granules

        if len(granules.index.unique()) == len(granules.index):
            msg = "Granules are unique. Using submit_burst_jobs instead."
            logger.warning(msg)
            self.submit_burst_jobs(
                pairs,
                granules,
                service,
                skip_existing,
                name=name,
                apply_water_mask=apply_water_mask,
                looks=looks,
            )
            return

        # Validate that each date has the same number of bursts
        counts = granules.groupby(granules.index).count()
        if counts.nunique() != 1:
            msg = (
                "Each date must have the same number of bursts for "
                "multi-burst submission. "
                f"Got burst counts per date: {counts.to_dict()}"
            )
            raise ValueError(msg)

        job_parameters = {
            "name": name,
            "apply_water_mask": apply_water_mask,
            "looks": looks,
        }
        hyp3_jobs = HyP3JobsMultiBurst(service, granules=granules)
        hyp3_jobs.job_parameters = job_parameters
        hyp3_jobs.submit_jobs(pairs, skip_existing=skip_existing)

    def to_gdf(self, crs: int | str | None = None) -> GeoDataFrame:
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
        gdf = self.gdf_burst
        if crs is not None:
            gdf.set_crs(crs=crs, inplace=True)
        return gdf

    def plot(self, crs: str = "EPSG:4326", ax: Axes | None = None, **kwargs) -> Axes:
        """Plot the burst scenes.

        Parameters
        ----------
        crs : str, optional
            The coordinate reference system to use for plotting.
            Default is "EPSG:4326".
        ax : Axes, optional
            The matplotlib Axes to plot on. If None, a new Axes will be created.
            Default is None.
        **kwargs :
            Additional keyword arguments to pass to the plotting function.

        """
        ec = kwargs.pop("edgecolor", "C0")
        fc = kwargs.pop("facecolor", "none")
        lw = kwargs.pop("linewidth", 1)
        ax = kwargs.pop("ax", ax)
        gdf = self.to_gdf("EPSG:4326").to_crs(crs)

        # ignore UserWarnings from geopandas during plotting
        warnings.filterwarnings("ignore", category=UserWarning)
        for burst_id in self.full_burst_ids:
            burst_gdf = gdf[gdf.fullBurstID == burst_id]

            # use minimum rotated rectangle to determine burst orientation
            geom = burst_gdf.geometry.values[0]
            min_rect = geom.minimum_rotated_rectangle
            coords = list(min_rect.exterior.coords)
            # calculate the angle of the burst
            edge1 = np.array(coords[1]) - np.array(coords[0])
            edge2 = np.array(coords[2]) - np.array(coords[1])
            # select the longer edge as the main direction
            if np.linalg.norm(edge1) > np.linalg.norm(edge2):
                angle = np.degrees(np.arctan2(edge1[1], edge1[0]))
            else:
                angle = np.degrees(np.arctan2(edge2[1], edge2[0]))
            # get the centroid of the burst
            centroid = burst_gdf.geometry.centroid.values[0]

            ax = burst_gdf.plot(
                ax=ax, edgecolor=ec, facecolor=fc, linewidth=lw, **kwargs
            )
            ax = cast("Axes", ax)
            ax.annotate(
                f"{burst_id} ({len(burst_gdf)})",
                xy=(centroid.x, centroid.y),
                ha="center",
                fontsize=8,
                rotation=angle,
                rotation_mode="anchor",
                color=ec,
            )  # 'anchor' to rotate around the center

        return ax

    def download_to_safe(
        self,
        folder: PathLike | str,
        all_anns: bool = False,
        keep_files: bool = False,
        full_burst_ids: Iterable[str] | None = None,
        limit: int = 10,
        retry: int = 50,
        quick_check: bool = True,
    ) -> None:
        """Download the burst scenes and convert to SAFE format.

        Parameters
        ----------
        folder : PathLike  | str
            The folder where the Scenes will be saved.
        all_anns : bool, optional
            Whether to include all annotation files for all swaths, regardless of
            included bursts. Useful for ISCE3 processing. Default is False.
        keep_files : bool, optional
            Whether to keep the original downloaded files after conversion.
            Default is False.
        full_burst_ids : Iterable[str] | None, optional
            List of full burst IDs to download. If None, all bursts will be
            downloaded.
        limit : int | None, optional
            Limit the number of bursts to download parallely. Default is 10.
        retry : int, optional
            Number of retries to wait for the server to prepare the data.
            Default is 50.
        quick_check : bool, optional
            Whether to check the safe files have been downloaded. Default is True.

            .. note::
                This will only check SAFE names roughly. It should be set to False
                if more full_burst_ids are provided when re-downloading.

        """
        # create the output folders
        folder = Path(folder)
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            logger.info("Created folder %s", folder)
        original_dir = folder / "original"
        if not original_dir.exists():
            original_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created folder %s", original_dir)
        safe_dir = folder / "SAFE"
        if not safe_dir.exists():
            safe_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created folder %s", safe_dir)

        # mask the full_burst_ids to download
        if full_burst_ids is None:
            full_burst_ids = self.full_burst_ids
        else:
            full_burst_ids = np.array(full_burst_ids, dtype=str).flatten()
            intersected_ids = np.intersect1d(full_burst_ids, self.full_burst_ids)
            if len(intersected_ids) == 0:
                logger.warning("No matching full burst IDs found in the scenes.")
                return
            full_burst_ids = intersected_ids

        # filter the gdf to only the selected burst IDs
        gdf = self.gdf_burst[self.gdf_burst.fullBurstID.isin(full_burst_ids)]
        absolute_orbit = gdf.orbit.unique().astype(np.uint32)

        burst_infos = create_burst_info_list(gdf, original_dir)
        logger.info(
            "Found %d burst(s), comprising %d SAFE(s).",
            len(burst_infos),
            len(absolute_orbit),
        )

        logger.info("Check burst group validities...")
        burst_sets = [
            [bi for bi in burst_infos if bi.absolute_orbit == orbit]
            for orbit in absolute_orbit
        ]
        # Checking burst group validities before download to fail faster
        for burst_set in burst_sets:
            Safe.check_group_validity(burst_set)

        safe_names = [safe.name for safe in safe_dir.glob("*.SAFE")]

        for burst_set in tqdm(burst_sets):
            if quick_check:
                safe_path = quick_match_safe(safe_names, burst_set)
                if safe_path:
                    logger.info("Safe %s already exists, skipping...", safe_path)
                    continue

            urls_burst = [bi.data_url for bi in burst_set]
            paths_burst = [bi.data_path for bi in burst_set]

            # get the unique metadata urls and paths
            arr_meta = pd.DataFrame({
                "url": [bi.metadata_url for bi in burst_set],
                "path": [bi.metadata_path for bi in burst_set],
            })

            arr_meta = arr_meta.groupby("path").first().reset_index()
            paths_burst_metadata = arr_meta.path.to_list()
            urls_burst_metadata = arr_meta.url.to_list()
            logger.info("Processing burst group %s...", burst_set[0].absolute_orbit)

            logger.info("  Downloading bursts...")
            downloader.batch_download_files(
                urls=urls_burst + urls_burst_metadata,
                file_names=paths_burst + paths_burst_metadata,
                retry=retry,
                engine="aiohttp",
                limit=limit,
            )
            logger.info("  Merging bursts into SAFE...")
            [info.add_shape_info() for info in burst_set]
            [info.add_start_stop_utc() for info in burst_set]
            safe = Safe(burst_set, all_anns, safe_dir)
            safe_path = safe.create_safe()
            logger.info("  Created SAFE at %s", safe_path)
            if not keep_files:
                safe.cleanup()
                logger.info("  Cleaned up original files for burst group")

        if not keep_files:
            try:
                original_dir.rmdir()
                logger.info("Removed empty original directory %s.", original_dir)
            except OSError:
                logger.debug(
                    "Original directory %s not empty, not removed.", original_dir
                )

        logger.success("All bursts are downloaded and converted to SAFE format.")


def quick_match_safe(safe_names: list[str], burst_set: list[BurstInfo]) -> str:
    """Quick match if the SAFE file is valid."""
    prefix = burst_set[0].slc_granule.split("_")[:3]
    min_date = min(cast("datetime", x.date) for x in burst_set).strftime("%Y%m%d")
    max_date = max(cast("datetime", x.date) for x in burst_set).strftime("%Y%m%d")
    date_pair = f"{min_date}_{max_date}"

    suffix = burst_set[0].slc_granule.split("_")[-3:-1]

    for safe_name in safe_names:
        prefix_safe = safe_name.split("_")[:3]
        suffix_safe = safe_name.split("_")[-3:-1]
        date_pair_safe = "_".join(
            pd.to_datetime(safe_name.split("_")[-5:-3]).strftime("%Y%m%d").tolist()
        )
        if (
            prefix_safe == prefix
            and suffix_safe == suffix
            and date_pair_safe == date_pair
        ):
            return safe_name
    return ""


def create_burst_info(product: pd.Series, work_dir: Path) -> BurstInfo:
    """Create a BurstInfo object given a granule.

    Parameters
    ----------
    product: Series
        DataFrame representing the burst product from ASF search.
    work_dir: Path
        The directory to save the data to.

    """
    burst_granule = product["fileID"]
    direction = product["flightDirection"].upper()
    polarization = product["polarization"].upper()
    absolute_orbit = int(product["orbit"])
    relative_orbit = int(product["pathNumber"])
    data_url = product["url"]
    metadata_url = product["additionalUrls"][0]

    slc_granule = Path(data_url).parent.parent.parent.name

    swath = product["burst"]["subswath"].upper()
    burst_id = int(product["burst"]["relativeBurstID"])
    burst_index = int(product["burst"]["burstIndex"])

    date_format = "%Y%m%dT%H%M%S"
    burst_time_str = burst_granule.split("_")[3]
    burst_time = datetime.strptime(burst_time_str, date_format)
    data_path = work_dir / f"{burst_granule}.tiff"
    # metadata_path = data_path.with_suffix(".xml")
    metadata_path = work_dir / f"{slc_granule}_{polarization}.xml"

    return BurstInfo(
        burst_granule,
        slc_granule,
        swath,
        polarization,
        burst_id,
        burst_index,
        direction,
        absolute_orbit,
        relative_orbit,
        burst_time,
        data_url,
        data_path,
        metadata_url,
        metadata_path,
    )


def create_burst_info_list(products: pd.DataFrame, work_dir: Path) -> list[BurstInfo]:
    """Convert the scenes to a list of BurstInfo objects.

    Parameters
    ----------
    products : pd.DataFrame
        DataFrame representing the burst products from ASF search.
    work_dir : Path
        The directory to save the data to.

    Returns
    -------
    list[BurstInfo]
        A list of BurstInfo objects representing the burst scenes.

    """
    burst_info_list = []
    for _, product in products.iterrows():
        burst_info = create_burst_info(product, work_dir)
        burst_info_list.append(burst_info)
    return burst_info_list
