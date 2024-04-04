import datetime as dt
from pathlib import Path

import pandas as pd

from data_downloader import parse_urls


class SentinelOrbit:
    """a class to retrieve Sentinel-1 orbit data links.

    Examples:
    ----------
    >>> from data_downloader import downloader, services
    >>> from pathlib import Path

    >>> folder_cal = Path("/media/data/aux_cal")  # specify the folder to save aux_cal
    >>> folder_preorb = Path("/media/data/poeorb")  # specify the folder to save aux_poeorb

    init SentinelOrbit:

    >>> s1_orbit = services.SentinelOrbit()

    Get all aux_cal data links of S1A and S1B and download them:

    >>> urls_cal = s1_orbit.cal_urls(platform='all')
    >>> downloader.async_download_datas(urls_cal, folder=folder_cal)

    Get all precise orbit data links of S1A during 20210101-20220301 and download them:

    >>> urls_preorb = s1_orbit.poeorb_urls(
    >>>    date_start="20210101", date_end="20220301", platform="S1A"
    >>> )
    >>> downloader.download_datas(urls_preorb, folder=folder_preorb)
    """

    def __init__(
        self,
        home_aux_cal: str = "https://s1qc.asf.alaska.edu/aux_cal/",
        home_preorb: str = "https://s1qc.asf.alaska.edu/aux_poeorb/",
    ) -> None:
        """init SentinelOrbit.

        Parameters:
        -----------
        home_aux_cal : str
            home url of aux_cal, default is "https://s1qc.asf.alaska.edu/aux_cal/".
        home_preorb : str
            home url of aux_poeorb, default is "https://s1qc.asf.alaska.edu/aux_poeorb/".
        """
        self.home_aux_cal = home_aux_cal
        self.home_preorb = home_preorb

    def cal_urls(self, platform="all"):
        """filter files from urls of aux_cal by platform.

        Parameters:
        -----------
        platform : str, one of ['S1A', 'S1B','all']
            platform of satellite. should be one of ['S1A', 'S1B','all']
        """
        urls = parse_urls.from_html(self.home_aux_cal)
        if platform in ["S1A", "S1B", "all"]:
            if platform == "all":
                platform = ["S1A", "S1B"]
            else:
                platform = [platform]
        else:
            raise ValueError("platform must be one of ['S1A', 'S1B','all']")

        _urls = [i for i in urls if Path(i).suffix == ".SAFE"]
        urls_filter = [i for i in _urls if Path(i).stem[:3] in platform]

        return urls_filter

    def poeorb_urls(
        self,
        date_start: str,
        date_end: str,
        platform: str = "all",
    ):
        """filter files from urls of aux_poeorb (precise orbit) by date and platform.

        Parameters:
        -----------
        date_start, date_end : str
            start/end date to filter, can be any format that can be converted by
            pd.to_datetime (e.g. '20210101', '2021-01-01', '2021/01/01').
        platform : str, one of ['S1A', 'S1B','all']
            platform of satellite. should be one of ['S1A', 'S1B','all']
        """
        if platform in ["S1A", "S1B", "all"]:
            if platform == "all":
                platform = ["S1A", "S1B"]
            else:
                platform = [platform]
        else:
            raise ValueError("platform must be one of ['S1A', 'S1B','all']")

        date_start = pd.to_datetime(date_start).date()
        date_end = pd.to_datetime(date_end).date()

        urls = parse_urls.from_html(self.home_preorb)
        _urls = [i for i in urls if Path(i).suffix == ".EOF"]
        urls_filter = []
        for i in _urls:
            name = Path(i).stem
            dt_i = pd.to_datetime(name.split("_")[-1]).date() - dt.timedelta(days=1)

            if name[:3] in platform and date_start <= dt_i <= date_end:
                urls_filter.append(i)

        return urls_filter
