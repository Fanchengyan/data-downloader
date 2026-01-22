from typing import Any, Iterable, Optional
import earthaccess
from earthaccess.search import DataGranule
import logging

logger = logging.getLogger(__name__)


class EarthAccessDownloader:
    """
    Base class for downloading data using earthaccess.
    """

    def __init__(self):
        """
        Initialize the downloader and login to earthaccess.
        """
        self.auth = earthaccess.login(strategy="interactive", persist=True)

    def search_data(self, count: int = -1, **kwargs: Any) -> Iterable[DataGranule]:
        """
        Search for data granules.

        Parameters
        ----------
        count : int, optional
            Number of granules to retrieve, by default -1 (all).
        **kwargs : Any
            Additional arguments passed to earthaccess.search_data.
            Common arguments: doi, bounding_box, temporal.

        Returns
        -------
        Iterable[DataGranule]
            Iterable of found granules.
        """
        logger.info(f"Searching data with params: {kwargs}")
        results = earthaccess.search_data(count=count, **kwargs)
        logger.info(f"Found {len(results)} granules.")
        return results

    def download(
        self, granules: Iterable[DataGranule], local_path: str = "./"
    ) -> Iterable[str]:
        """
        Download granules to a local directory.

        Parameters
        ----------
        granules : Iterable[DataGranule]
            Iterable of granules to download.
        local_path : str, optional
            Local directory to save files, by default "./".

        Returns
        -------
        Iterable[str]
            Iterable of downloaded file paths.
        """
        if not granules:
            logger.warning("No granules to download.")
            return []

        logger.info(f"Downloading {len(granules)} granules to {local_path}...")
        files = earthaccess.download(granules, local_path=local_path)
        return files
