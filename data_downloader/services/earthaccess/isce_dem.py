import logging
import os
import shutil
from pathlib import Path
from typing import List, Tuple

# Lazy loading of ISCE2 modules to allow installation checking at runtime
try:
    from isce.components.contrib.demUtils import createDemStitcher, createSWBDStitcher

    ISCE2_AVAILABLE = True
except ImportError:
    ISCE2_AVAILABLE = False

from .downloader import EarthAccessDownloader

logger = logging.getLogger(__name__)


def _check_isce2_available():
    if not ISCE2_AVAILABLE:
        raise ImportError(
            "ISCE2 'contrib.demUtils' not found. "
            "Please ensure ISCE2 is installed and in your PYTHONPATH."
        )


class ISCE2AuxData(EarthAccessDownloader):
    """
    Base class for ISCE2 auxiliary data (DEMs, Water Masks).
    """

    DOI = None
    SHORT_NAME = None

    def __init__(
        self,
        bbox: Tuple[float, float, float, float],
        output_dir: str | os.PathLike = ".",
    ):
        """
        Initialize the downloader.

        Parameters
        ----------
        bbox : Tuple[float, float, float, float]
            Bounding box (west, south, east, north).
        output_dir : str, optional
            Output directory for downloaded files, by default ".".
        """
        super().__init__()
        self.bbox = bbox
        self.output_dir = Path(output_dir)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        self.downloaded_files: List[str] = []

    def download(self) -> List[str]:
        """
        Search and download data for the specified bounding box.

        Returns
        -------
        List[str]
            List of downloaded file paths.
        """
        if self.DOI is None:
            raise ValueError("DOI must be defined in subclass.")

        logger.info(
            f"Searching for {self.__class__.__name__} with DOI {self.DOI} in bbox {self.bbox}"
        )
        results = self.search_data(doi=self.DOI, bounding_box=self.bbox)

        if not results:
            logger.warning("No data found.")
            return []

        self.downloaded_files = super().download(
            results, local_path=str(self.output_dir)
        )
        return self.downloaded_files

    def merge(
        self,
        output_name: str | None = None,
        delete_original: bool = False,
    ) -> str:
        """
        Merge downloaded files into a single file.
        Must be implemented by subclasses.

        Parameters
        ----------
        output_name : str, optional
            Name of the output merged file. If None, uses ISCE2 default naming.
        delete_original : bool, optional
            Whether to delete original files after merge, by default False.

        Returns
        -------
        str
            Path to the merged file.
        """
        raise NotImplementedError("Merge method must be implemented by subclasses.")

    def _cleanup_original(self):
        """Helper to remove original downloaded files."""
        for f in self.downloaded_files:
            if os.path.isdir(f):
                shutil.rmtree(f)
            elif os.path.exists(f):
                os.remove(f)

    def _ensure_vrt(self, output_path: str):
        """
        Ensure a VRT file exists for the output.
        If missing, attempts to create one from the ISCE XML.
        """
        vrt_path = output_path + ".vrt"
        if os.path.exists(vrt_path):
            return

        xml_path = output_path + ".xml"
        if os.path.exists(xml_path):
            logger.info(f"VRT missing. Generating {vrt_path} from {xml_path}...")
            try:
                from osgeo import gdal

                ds = gdal.Open(xml_path)
                if ds:
                    gdal.Translate(vrt_path, ds, format="VRT")
                    logger.info("VRT generated successfully.")
                else:
                    logger.warning(
                        f"Could not open {xml_path} with GDAL to generate VRT."
                    )
            except ImportError:
                logger.warning("osgeo.gdal not found. Cannot generate VRT.")
            except Exception as e:
                logger.warning(f"Failed to generate VRT: {e}")


class SRTMGL1(ISCE2AuxData):
    """
    SRTMGL1 downloader and merger (1 arc-second Global).
    """

    DOI = "10.5067/MEASURES/SRTM/SRTMGL1.003"

    def merge(
        self,
        output_name: str | None = None,
        delete_original: bool = False,
    ) -> str:
        _check_isce2_available()

        st = createDemStitcher("version3")
        st.setUseLocalDirectory(True)
        st.setCreateXmlMetadata(True)
        st._keepAfterFailed = True

        lat = [self.bbox[1], self.bbox[3]]
        lon = [self.bbox[0], self.bbox[2]]

        # Source 1 for SRTMGL1
        source = 1

        if output_name is None:
            # ISCE2 defaultName expects [S, N, W, E]
            # self.bbox is (W, S, E, N) -> [bbox[1], bbox[3], bbox[0], bbox[2]]
            snwe = [self.bbox[1], self.bbox[3], self.bbox[0], self.bbox[2]]
            output_name = st.defaultName(snwe)
            logger.info(f"Using default ISCE2 output name: {output_name}")

        logger.info(f"Stitching SRTMGL1 DEMs to {output_name} in {self.output_dir}")

        # stitchDems returns True on success
        success = st.stitchDems(
            lat,
            lon,
            source,
            os.path.basename(output_name),
            str(self.output_dir),
            keep=not delete_original,
        )

        if not success:
            logger.error("ISCE2 DemStitcher failed to stitch DEMs.")
            return ""

        output_path = str(self.output_dir / output_name)
        self._ensure_vrt(output_path)
        return output_path


class SRTMGL3(ISCE2AuxData):
    """
    SRTMGL3 downloader and merger (3 arc-second Global).
    """

    DOI = "10.5067/MEASURES/SRTM/SRTMGL3.003"

    def merge(
        self, output_name: str | None = None, delete_original: bool = False
    ) -> str:
        _check_isce2_available()

        st = createDemStitcher("version3")
        st.setUseLocalDirectory(True)
        st.setCreateXmlMetadata(True)
        st._keepAfterFailed = True

        lat = [self.bbox[1], self.bbox[3]]
        lon = [self.bbox[0], self.bbox[2]]

        # Source 3 for SRTMGL3
        source = 3

        if output_name is None:
            snwe = [self.bbox[1], self.bbox[3], self.bbox[0], self.bbox[2]]
            output_name = st.defaultName(snwe)
            logger.info(f"Using default ISCE2 output name: {output_name}")

        logger.info(f"Stitching SRTMGL3 DEMs to {output_name} in {self.output_dir}")

        success = st.stitchDems(
            lat,
            lon,
            source,
            os.path.basename(output_name),
            str(self.output_dir),
            keep=not delete_original,
        )

        if not success:
            logger.error("ISCE2 DemStitcher failed to stitch DEMs.")
            return ""

        output_path = str(self.output_dir / output_name)
        self._ensure_vrt(output_path)
        return output_path


class SRTMSWBD(ISCE2AuxData):
    """
    SRTMSWBD downloader and merger (Water Body Data).
    """

    DOI = "10.5067/MEASURES/SRTM/SRTMSWBD.003"

    def merge(
        self, output_name: str | None = None, delete_original: bool = False
    ) -> str:
        _check_isce2_available()

        st = createSWBDStitcher()
        st.configure()  # Initialize inherited DemStitcher attributes like _noFilling
        st.setCreateXmlMetadata(True)
        # SWBDStitcher doesn't have setUseLocalDirectory, set internal attributes directly
        st._useLocalDirectory = True
        st._downloadDir = str(self.output_dir)
        st._keepAfterFailed = True

        lat = [self.bbox[1], self.bbox[3]]
        lon = [self.bbox[0], self.bbox[2]]

        if output_name is None:
            snwe = [self.bbox[1], self.bbox[3], self.bbox[0], self.bbox[2]]
            output_name = st.defaultName(snwe)
            logger.info(f"Using default ISCE2 SWBD output name: {output_name}")

        logger.info(f"Stitching SWBD data to {output_name} in {self.output_dir}")

        try:
            # stitchWbd writes to outname directly, not relative to downloadDir
            full_output_path = os.path.join(
                str(self.output_dir), os.path.basename(output_name)
            )
            st.stitchWbd(
                lat,
                lon,
                full_output_path,
                str(self.output_dir),
                keep=not delete_original,
            )
        except Exception as e:
            logger.error(f"ISCE2 SWBDStitcher failed: {e}")
            return ""

        output_path = str(self.output_dir / output_name)
        self._ensure_vrt(output_path)
        return output_path
