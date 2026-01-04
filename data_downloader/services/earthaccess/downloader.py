from typing import Any, List, Optional
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

    def search_data(self, 
                    count: int = -1,
                    **kwargs: Any) -> List[DataGranule]:
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
        List[DataGranule]
            List of found granules.
        """
        logger.info(f"Searching data with params: {kwargs}")
        results = earthaccess.search_data(count=count, **kwargs)
        logger.info(f"Found {len(results)} granules.")
        return results

    def download(self, 
                 granules: List[DataGranule], 
                 local_path: str = "./") -> List[str]:
        """
        Download granules to a local directory.
        
        Parameters
        ----------
        granules : List[DataGranule]
            List of granules to download.
        local_path : str, optional
            Local directory to save files, by default "./".
            
        Returns
        -------
        List[str]
            List of downloaded file paths.
        """
        if not granules:
            logger.warning("No granules to download.")
            return []
            
        logger.info(f"Downloading {len(granules)} granules to {local_path}...")
        files = earthaccess.download(granules, local_path=local_path)
        return files
