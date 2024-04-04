import re
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from data_downloader import parse_urls


class LiCSARService:
    """a class to retrieve LiCSAR data 

    Example:
    --------
    >>> from pathlib import Path
    >>> import pandas as pd
    >>> from data_downloader import downloader, services
    >>> # specify the folder to save data
    >>> home_dir = Path("/Volumes/Data/LiCSAR/106D_05248_131313/")
    >>> pair_dir = home_dir / "GEOC"

    init LiCSARService by frame id and download all metadata files

    >>> licsar = services.LiCSARService("106D_05248_131313")
    >>> downloader.download_datas(licsar.meta_urls, folder=home_dir, desc="Metadata")

    generate mask data by primary_dates, secondary_dates and day span

    >>> mask = (licsar.primary_dates>pd.to_datetime("2019-01-01")) & (licsar.primary_dates<pd.to_datetime("2019-12-31")) & (licsar.days < 12 * 5 + 1)

    download interferograms and coherence files filtered by mask

    >>> downloader.download_datas(licsar.ifg_urls[mask].values, folder=pair_dir, desc="Interferogram")
    >>> downloader.download_datas(licsar.coh_urls[mask], folder=pair_dir, desc="Coherence")
    """

    def __init__(
        self,
        frame_id: str,
        root_url: str = "https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products",
    ):
        """init LiCSARService.

        Parameters:
        -----------
        frame_id : str
            frame id of LiCSAR.
        root_url : str
            root url of LiCSAR. default is "https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products".
        """
        self.frame_id = frame_id
        self.track_id = self._parse_track_id()
        self.home_url = f"{root_url}/{self.track_id}/{self.frame_id}"

        self._pairs, self._ifg_urls, self._coh_urls = self._retrieve_pairs_urls()

    def __repr__(self):
        return f"LiCSAR(frame_id={self.frame_id}, count={len(self.pairs)})"

    def __str__(self) -> str:
        return f"LiCSAR(frame_id={self.frame_id}, count={len(self.pairs)})"

    def __len__(self):
        return len(self.pairs)

    def _parse_track_id(self):
        """parse track id from frame id."""
        track_id = str(int(self.frame_id[0:3]))
        return track_id

    def _retrieve_pairs_urls(self):
        """retrieve pairs of LiCSAR."""
        url = f"{self.home_url}/interferograms/"
        page_urls = parse_urls.from_html(url, url_depth=1)
        pairs = []
        ifg_urls = []
        coh_urls = []
        for i in page_urls:
            re_result = re.findall(r"\d{8}_\d{8}", i)
            if re_result:
                pairs.append(re_result[0])
                ifg_urls.append(f"{i}/{re_result[0]}.geo.unw.tif")
                coh_urls.append(f"{i}/{re_result[0]}.geo.cc.tif")
        return pairs, ifg_urls, coh_urls

    @property
    def pairs(self)->np.ndarray:
        """all available pairs of given frame id."""
        return np.array(self._pairs)

    @property
    def ifg_urls(self)->pd.Series:
        """interferogram urls of given frame id."""
        df = pd.Series(self._ifg_urls, name="ifg_urls", index=self._pairs)
        return df

    @property
    def coh_urls(self)->pd.Series:
        """coherence urls of given frame id."""
        df = pd.Series(self._coh_urls, name="coh_urls", index=self._pairs)
        return df

    @property
    def urls(self)->pd.DataFrame:
        """all urls, including interferogram and coherence, of given frame id."""
        urls = pd.concat([self.ifg_urls, self.coh_urls], axis=1)
        return urls

    @property
    def primary_dates(self)->np.ndarray:
        """primary dates of pairs for given frame id."""
        primary_dates = [
            datetime.strptime(i.split("_")[0], "%Y%m%d") for i in self.pairs
        ]
        return np.array(primary_dates, dtype="datetime64[D]")

    @property
    def secondary_dates(self)->np.ndarray:
        """secondary dates of pairs for given frame id."""
        secondary_dates = [
            datetime.strptime(i.split("_")[1], "%Y%m%d") for i in self.pairs
        ]
        return np.array(secondary_dates, dtype="datetime64[D]")

    @property
    def days(self)->np.ndarray:
        """days between primary and secondary dates."""
        days = self.secondary_dates - self.primary_dates
        return days.astype(int)

    @property
    def meta_urls(self)->np.ndarray:
        """metadata urls of LiCSAR. 
        
        metadata includes: 
        
        * E, N, U, hgt 
        * baselines
        * metadata.txt
        * network.png
        * frame_id-poly.txt
        """
        urls = []
        file_names = [
            f"{self.frame_id}.geo.{ENU}.tif" for ENU in ["E", "N", "U", "hgt"]
        ]
        files = file_names + [
            "baselines",
            "metadata.txt",
            "network.png",
            f"{self.frame_id}-poly.txt",
        ]

        for file in files:
            url = f"{self.home_url}/metadata/{file}"
            urls.append(url)

        return np.array(urls)
