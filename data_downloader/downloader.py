import asyncio
import datetime as dt
import multiprocessing as mp
import os
import selectors
import time
from netrc import netrc
from pathlib import Path
from urllib.parse import urlparse

import browser_cookie3 as bc
import httpx
import nest_asyncio
import requests
from dateutil.parser import parse
from tqdm.auto import tqdm

nest_asyncio.apply()


def get_url_host(url):
    """Returns the url host for a given url"""
    ri = urlparse(url)
    # Strip port numbers from netloc. This weird `if...encode`` dance is
    # used for Python 3.2, which doesn't support unicode literals.
    splitstr = b":"
    if isinstance(url, str):
        splitstr = splitstr.decode("ascii")
    host = ri.netloc.split(splitstr)[0]
    return host


def get_netrc_auth(url):
    """Returns the Requests tuple auth for a given url from .netrc"""
    host = get_url_host(url)
    _netrc = Netrc().authenticators(host)

    if _netrc:
        # Return with login / password
        login_i = 0 if _netrc[0] else 1
        return (_netrc[login_i], _netrc[2])


class Netrc(netrc):
    """add or clear records in .netrc file"""

    def __init__(self, file=None):
        if file is None:
            file = os.path.join(os.path.expanduser("~"), ".netrc")
        self.file = file
        if not os.path.exists(file):
            open(self.file, "w").close()

        netrc.__init__(self, file)

    def _info_to_file(self):
        rep = self.__repr__()
        with open(self.file, "w") as f:
            f.write(rep)

    def _update_info(self):
        with open(self.file) as fp:
            self._parse(self.file, fp, False)

    def add(self, host, login, password, account=None, overwrite=False):
        """add a record

        Will do nothing if host exists in .netrc file unless set overwrite=True
        """
        if host in self.hosts and not overwrite:
            tqdm.write(
                f">>> Warning: {host} existed, nothing will be done."
                + " If you want to overwrite the existed record, set overwrite=True"
            )
        else:
            self.hosts.update({host: (login, account, password)})
            self._info_to_file()
            self._update_info()

    def remove(self, host):
        """remove a record by host"""
        self.hosts.pop(host)
        self._info_to_file()
        self._update_info()

    def clear(self):
        """remove all records"""
        self.hosts = {}
        self._info_to_file()
        self._update_info()


def _parse_file_name(response):
    """parse the file_name from the headers of web response or url"""

    if "Content-disposition" in response.headers:
        file_name = (
            response.headers["Content-disposition"]
            .split("filename=")[1]
            .strip('"')
            .strip("'")
        )
    else:
        file_name = os.path.basename(urlparse(str(response.url)).path)
    return file_name


def _unit_formater(size, suffix):
    prefixs = ["", "k", "M", "G", "T"]
    idx = 0
    while size / 1024 >= 1:
        size = size / 1024
        idx += 1
        if idx == 4:
            break

    return f"{size:.2f}{prefixs[idx]}{suffix}"


def _new_file_from_web(r, file_path):
    """whether have new file from the website"""
    try:
        time_remote = parse(r.headers.get("Last-Modified"))
        time_local = dt.datetime.fromtimestamp(
            os.path.getmtime(file_path), dt.timezone.utc
        )
        return time_remote > time_local
    except:
        return False


def _get_cookiejar(authorize_from_browser):
    cj = None
    if authorize_from_browser:
        try:
            cj = bc.load()
        except:
            raise EnvironmentError(
                "Could not load cookie from browser. "
                "Please login in website via browser before run this code"
                "\n  So far the following browsers are supported: "
                "Chrome,Firefox, Opera, Edge, Chromium"
            )
    return cj


def _handle_status(r, url, local_size, file_name, file_path):
    # returns (True, '') : downloaded entirely
    # returns (False,'') : error! break download
    # returns (False, url) : 301,302
    # returns None: continue to download

    global support_resume, pbar, remote_size

    if r.status_code in [206, 416]:
        support_resume = True
        remote_size = int(r.headers["Content-Range"].rsplit("/")[-1])

        # init process bar
        if _new_file_from_web(r, file_path):
            tqdm.write(
                f"There is a new file from {url}"
                f"{file_name} is ready to be downloaded again"
            )
            os.remove(file_path)
        elif local_size < remote_size:
            pbar = tqdm(
                initial=local_size,
                total=remote_size,
                unit="B",
                unit_scale=True,
                dynamic_ncols=True,
                desc=Path(file_name).name,
            )
        else:
            tqdm.write(f"{file_name} was downloaded entirely. skiping download")
            return True, ""
    elif r.status_code == 200:
        # know the total size, then delete the file that wasn't downloaded entirely and redownload it.
        if "Content-length" in r.headers:
            remote_size = int(r.headers["Content-length"])

            if _new_file_from_web(r, file_path):
                tqdm.write(
                    f"There is a new file from {url}"
                    f"{file_name} is ready to be downloaded again"
                )
                os.remove(file_path)
            elif 0 < local_size < remote_size:
                tqdm.write(f"  Detect {file_name} wasn't downloaded entirely")
                tqdm.write(
                    "  The website not supports resuming breakpoint."
                    " Prepare to remove the local file and redownload..."
                )
                os.remove(file_path)
            elif local_size > remote_size:
                tqdm.write(
                    "Detected the local file is larger than the server file. "
                    " Prepare to remove local the file and redownload..."
                )
                os.remove(file_path)
            elif local_size == remote_size:
                tqdm.write(f"{file_name} was downloaded entirely. skiping download")
                return True, ""
        # don't know the total size, warning user if detect the file was downloaded.
        else:
            if os.path.exists(file_path):
                tqdm.write(
                    f">>> Warning: Detect the {file_name} was downloaded,"
                    " but can't parse the it's size from website\n"
                    f"    If you know it wasn't downloaded entirely, delete "
                    "it and redownload it again. skiping download..."
                )
                return True, ""
    elif r.status_code == 202:
        tqdm.write(
            ">>> The server has accepted your request but has not yet processed it. "
            "Please redownload it later"
        )
        return False, ""
    elif r.status_code in [301, 302]:
        url_new = r.headers["Location"]
        tqdm.write(f">>> Waring: the website has redirected to {url_new}")
        return False, url_new
    elif r.status_code == 401:
        tqdm.write(
            ">>> Authorization failed! Please check your username and password in Netrc "
            "Or authorizing by browser and set the parameter `authorize_from_browser` to `True`"
        )
        return False, ""
    elif r.status_code == 403:
        tqdm.write(
            ">>> Forbidden! Access to the requested resource was denied by the server"
        )
        return False, ""
    else:
        tqdm.write(
            f'  Download file from "{url}" failed,'
            f" The service returns the HTTP Status Code: {r.status_code}"
        )
        return False, ""


def _download_data_httpx(
    url,
    folder=None,
    file_name=None,
    client=None,
    follow_redirects=True,
    retry=0,
    authorize_from_browser=False,
):
    """Download a single file.

    Parameters:
    -----------
    url: str
        url of web file
    folder: str
        the folder to store output files. Default current folder.
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    file_name: str
        the file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client: httpx.Client() object
        client maintaining connection. Default None
    follow_redirects: bool
        Enables or disables HTTP redirects
    retry: int
        number of reconnections when status code is 503
    """
    # init parameters
    global support_resume, pbar, remote_size

    support_resume = False
    headers = {"Range": "bytes=0-4"}
    if not client:
        client = httpx

    cj = _get_cookiejar(authorize_from_browser)

    r = client.get(
        url, headers=headers, timeout=120, follow_redirects=follow_redirects, cookies=cj
    )
    r.close()

    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        file_path = os.path.join(folder, file_name)
    else:
        file_path = os.path.abspath(file_name)

    local_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    result = _handle_status(r, url, local_size, file_name, file_path)
    if result:
        status, url_new = result
        if status:  # downloaded entirely
            return True
        elif status == False:
            if url_new:  # 301,302
                return _download_data_httpx(
                    url_new,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    follow_redirects=True,
                    client=client,
                )
            elif retry > 0:
                return _download_data_httpx(
                    url,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    client=client,
                    retry=retry - 1,
                )
            else:  # error! break download
                return False

    # begin downloading
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None

    with client.stream("GET", url, headers=headers, timeout=120, cookies=cj) as r:
        with open(file_path, "ab") as f:
            time_start_realtime = time_start = time.time()
            for chunk in r.iter_raw():
                if chunk:
                    size_add = len(chunk)
                    local_size += size_add
                    f.write(chunk)
                    f.flush()
                if support_resume:
                    pbar.update(size_add)
                else:
                    time_end_realtime = time.time()
                    time_span = time_end_realtime - time_start_realtime
                    if time_span > 1:
                        speed_realtime = size_add / time_span
                        tqdm.write(
                            "  Downloading {} [Speed: {} | Size: {}]".format(
                                file_name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            ),
                            end="\r",
                        )
                        time_start_realtime = time_end_realtime
            if not support_resume:
                time_cost = time.time() - time_start
                speed = local_size / time_cost if time_cost > 0 else 0
                tqdm.write(
                    "  Finish downloading {} [Speed: {} | Total Size: {}]".format(
                        file_name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                )
    return True


def _download_data_requests(
    url,
    folder=None,
    file_name=None,
    client=None,
    follow_redirects=True,
    retry=0,
    authorize_from_browser=False,
):
    """Download a single file.

    Parameters:
    -----------
    url: str
        url of web file
    folder: str
        the folder to store output files. Default current folder.
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    file_name: str
        the file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client: requests.Session() object
        client maintaining connection. Default None
    follow_redirects: bool
        Enables or disables HTTP redirects
    retry: int
        number of reconnections when status code is 503
    """
    # init parameters
    global support_resume, pbar, remote_size

    support_resume = False
    headers = {"Range": "bytes=0-4"}
    if not client:
        client = requests

    cj = _get_cookiejar(authorize_from_browser)

    r = client.get(
        url, headers=headers, timeout=120, allow_redirects=follow_redirects, cookies=cj
    )
    r.close()

    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        file_path = os.path.join(folder, file_name)
    else:
        file_path = os.path.abspath(file_name)

    local_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    result = _handle_status(r, url, local_size, file_name, file_path)
    if result:
        status, url_new = result
        if status:  # downloaded entirely
            return True
        elif status == False:
            if url_new:  # 301,302
                return _download_data_requests(
                    url_new,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    follow_redirects=True,
                    client=client,
                )
            elif retry > 0:
                return _download_data_requests(
                    url,
                    folder=folder,
                    file_name=file_name,
                    authorize_from_browser=authorize_from_browser,
                    client=client,
                    retry=retry - 1,
                )
            else:  # error! break download
                return False

    # begin downloading
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None

    r = client.get(url, headers=headers, stream=True, timeout=120, cookies=cj)
    with open(file_path, "ab") as f:
        time_start_realtime = time_start = time.time()
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
            if support_resume:
                pbar.update(size_add)
            else:
                time_end_realtime = time.time()
                time_span = time_end_realtime - time_start_realtime
                if time_span > 1:
                    speed_realtime = size_add / time_span
                    tqdm.write(
                        "  Downloading {} [Speed: {} | Size: {}]".format(
                            file_name,
                            _unit_formater(speed_realtime, "B/s"),
                            _unit_formater(local_size, "B"),
                        ),
                        end="\r",
                    )
                    time_start_realtime = time_end_realtime
        if not support_resume:
            time_cost = time.time() - time_start
            speed = local_size / time_cost if time_cost > 0 else 0
            tqdm.write(
                "  Finish downloading {} [Speed: {} | Total Size: {}]".format(
                    file_name,
                    _unit_formater(speed, "B/s"),
                    _unit_formater(local_size, "B"),
                )
            )

    r.close()
    return True


def download_data(
    url,
    folder=None,
    file_name=None,
    client=None,
    engine="requests",
    follow_redirects=True,
    retry=0,
    authorize_from_browser=False,
):
    """Download a single file.

    Parameters:
    -----------
    url: str
        url of web file
    folder: str
        the folder to store output files. Default current folder.
    file_name: str
        the file name. If None, will parse from web response or url.
        file_name can be the absolute path if folder is None.
    client: requests.Session() for `requests` engine or httpx.Client() for `httpx` engine
        client maintaining connection. Default None
    engine: one of ["requests","httpx"]
        engine for downloading
    follow_redirects: bool
        Enables or disables HTTP redirects
    retry: int
        number of reconnections when status code is 503
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    """

    if engine == "requests":
        _download_data_requests(
            url,
            folder,
            file_name,
            client,
            follow_redirects,
            retry,
            authorize_from_browser,
        )
    elif engine == "httpx":
        _download_data_httpx(
            url,
            folder,
            file_name,
            client,
            follow_redirects,
            retry,
            authorize_from_browser,
        )
    else:
        raise ValueError('engine must be one of ["requests","httpx"]')


def download_datas(
    urls,
    folder=None,
    file_names=None,
    engine="requests",
    authorize_from_browser=False,
    desc="",
):
    """download data from a list like object which containing urls.
    This function will download files one by one.

    Parameters:
    -----------
    urls:  iterator
        iterator contains urls
    folder: str
        the folder to store output files. Default current folder.
    engine: one of ["requests","httpx"]
        engine for downloading
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program to parse
        them from website. file_names can cantain the absolute paths if folder is None.
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    desc: str
        description of data downloading

    Examples:
    ---------
    ```python
    from data_downloader import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif']

    folder = 'D:\\data'
    downloader.download_datas(urls,folder)
    ```
    """
    if engine == "requests":
        client = requests.Session()
    elif engine == "httpx":
        client = httpx.Client(timeout=None)
    else:
        raise ValueError('engine must be one of ["requests","httpx"]')
    
    desc = ">>> Total | " + desc.title()
    for i, url in enumerate(tqdm(urls, unit="files", dynamic_ncols=True, desc=desc)):
        if file_names is not None:
            download_data(
                url,
                folder,
                file_name=file_names[i],
                client=client,
                engine=engine,
                authorize_from_browser=authorize_from_browser,
            )
        else:
            download_data(
                url,
                folder,
                client=client,
                engine=engine,
                authorize_from_browser=authorize_from_browser,
            )


def _mp_download_data(args):
    return download_data(*args)


def mp_download_datas(
    urls,
    folder=None,
    file_names=None,
    ncore=None,
    desc="",
    follow_redirects=True,
    retry=0,
    engine="requests",
    authorize_from_browser=False,
):
    """download data from a list like object which containing urls.
    This function will download multiple files simultaneously using multiprocess.

    Parameters:
    -----------
    urls:  iterator
        iterator contains urls
    folder: str
        the folder to store output files. Default current folder.
    engine: one of ["requests","httpx"]
        engine for downloading
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program to parse
        them from website. file_names can contain the absolute paths if folder is None.
    ncore: int
        Number of cores for parallel processing. If ncore is None then the number returned
        by os.cpu_count() is used. Default None.
    desc: str
        description of data downloading
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very useful when website doesn't support
        "HTTP Basic Auth". Default is False.

    Examples:
    ---------
    ```python
    from data_downloader import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif']

    folder = 'D:\\data'
    downloader.mp_download_datas(urls,folder)
    ```
    """
    if ncore == None:
        ncore = os.cpu_count()
    else:
        ncore = int(ncore)
    tqdm.write(f">>> {ncore} parallel downloading")

    desc = ">>> Total | " + desc.title()
    pbar = tqdm(total=len(urls), desc=desc, dynamic_ncols=True)

    with mp.Pool(ncore) as pool:
        if file_names is not None:
            args = [
                (
                    urls[i],
                    folder,
                    file_names[i],
                    None,
                    engine,
                    follow_redirects,
                    retry,
                    authorize_from_browser,
                )
                for i in range(len(urls))
            ]  # Need to put other parameters in right places
        else:
            args = [
                (
                    urls[i],
                    folder,
                    file_names,
                    None,
                    engine,
                    follow_redirects,
                    retry,
                    authorize_from_browser,
                )
                for i in range(len(urls))
            ]

        for i in pool.imap_unordered(_mp_download_data, args):
            pbar.update()


async def _download_data(
    client,
    url,
    folder=None,
    file_name=None,
    follow_redirects=True,
    retry=0,
    authorize_from_browser=False,
):
    global support_resume, pbar, remote_size

    headers = {"Range": "bytes=0-4"}
    support_resume = False

    cj = _get_cookiejar(authorize_from_browser)
    # auth = get_netrc_auth(url)

    r = await client.get(
        url, headers=headers, timeout=120, follow_redirects=follow_redirects, cookies=cj
    )
    # r.close()
    # r = await client.head(url, headers=headers, auth=auth, timeout=120)
    if file_name is None:
        file_name = _parse_file_name(r)

    if folder is not None:
        if not os.path.exists(folder):
            os.makedirs(folder)
        file_path = os.path.join(folder, file_name)
    else:
        file_path = os.path.abspath(file_name)

    local_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    result = _handle_status(r, url, local_size, file_name, file_path)
    if result:
        status, url_new = result
        if status:  # downloaded entirely
            return True
        elif status == False:
            if url_new:  # 301,302
                return await _download_data(
                    client,
                    url_new,
                    folder=folder,
                    authorize_from_browser=authorize_from_browser,
                    file_name=file_name,
                    follow_redirects=True,
                )
            elif retry > 0:
                return await _download_data(
                    client,
                    url,
                    folder=folder,
                    authorize_from_browser=authorize_from_browser,
                    file_name=file_name,
                    retry=retry - 1,
                )
            else:  # error! break download
                return False

    # begin download
    if support_resume:
        headers["Range"] = f"bytes={local_size}-{remote_size}"
    else:
        headers = None
    auth = get_netrc_auth(get_url_host(url))
    async with client.stream(
        "GET", url, headers=headers, auth=auth, timeout=None, cookies=cj
    ) as r:
        with open(file_path, "ab") as f:
            time_start_realtime = time_start = time.time()

            async for chunk in r.aiter_bytes():
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
                if support_resume:
                    pbar.update(size_add)
                else:
                    time_end_realtime = time.time()
                    time_span = time_end_realtime - time_start_realtime
                    if time_span > 1:
                        speed_realtime = size_add / time_span
                        tqdm.write(
                            "Downloading {} [Speed: {} | Size: {}]".format(
                                file_name,
                                _unit_formater(speed_realtime, "B/s"),
                                _unit_formater(local_size, "B"),
                            ),
                            end="\r",
                        )
                        time_start_realtime = time_end_realtime
            if not support_resume:
                speed = local_size / (time.time() - time_start)
                tqdm.write(
                    "Finish downloading {} [Speed: {} | Total Size: {}]".format(
                        file_name,
                        _unit_formater(speed, "B/s"),
                        _unit_formater(local_size, "B"),
                    )
                )
            # r.close()
            return True


async def creat_tasks(
    urls,
    folder,
    authorize_from_browser,
    file_names,
    limit,
    desc,
    follow_redirects,
    retry,
):
    limits = httpx.Limits(max_keepalive_connections=limit, max_connections=limit)
    async with httpx.AsyncClient(limits=limits, timeout=None, verify=False) as client:
        if file_names is not None:
            tasks = [
                asyncio.ensure_future(
                    _download_data(
                        client,
                        url,
                        folder,
                        authorize_from_browser=authorize_from_browser,
                        file_name=file_names[i],
                        follow_redirects=follow_redirects,
                        retry=retry,
                    )
                )
                for i, url in enumerate(urls)
            ]
        else:
            tasks = [
                asyncio.ensure_future(
                    _download_data(
                        client,
                        url,
                        folder,
                        authorize_from_browser=authorize_from_browser,
                        follow_redirects=follow_redirects,
                        retry=retry,
                    )
                )
                for url in urls
            ]

        # Total process bar
        tasks_iter = asyncio.as_completed(tasks)
        desc = ">>> Total | " + desc.title()
        pbar = tqdm(tasks_iter, total=len(urls), desc=desc, dynamic_ncols=True)
        for coroutine in pbar:
            await coroutine


def async_download_datas(
    urls,
    folder=None,
    file_names=None,
    limit=30,
    desc="",
    follow_redirects=True,
    retry=0,
    authorize_from_browser=False,
):
    """Download multiple files simultaneously.

    Parameters:
    -----------
    urls:  iterator
        iterator contains urls
    folder: str
        the folder to store output files. Default current folder.
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program
        to parse them from website. file_names can cantain the absolute paths if folder is None.
    limit: int
        the number of files downloading simultaneously
    desc: str
        description of datas downloading
    follow_redirects: bool
        Enables or disables HTTP redirects
    retry: int
        number of reconnections when status code is 503

    Example:
    ---------

    from data_downloader import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif']

    folder = 'D:\\data'
    downloader.async_download_datas(urls,folder,None,desc='interferograms')
    """
    # solve the loop close  Error for python 3.8.x in windows platform
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop(selector)
    try:
        loop.run_until_complete(
            creat_tasks(
                urls,
                folder,
                authorize_from_browser,
                file_names,
                limit,
                desc,
                follow_redirects,
                retry,
            )
        )
    finally:
        loop.close()


async def _is_response_staus_ok(client, url, authorize_from_browser, timeout):
    cj = _get_cookiejar(authorize_from_browser)
    try:
        r = await client.head(url, timeout=timeout, cookies=cj)
        r.close()
        if r.status_code == httpx.codes.OK:
            return True
        else:
            return False
    except:
        return False


async def creat_tasks_status_ok(urls, limit, authorize_from_browser, timeout):
    limits = httpx.Limits(max_keepalive_connections=limit, max_connections=limit)
    async with httpx.AsyncClient(limits=limits, timeout=None) as client:
        tasks = [
            asyncio.create_task(
                _is_response_staus_ok(client, url, authorize_from_browser, timeout)
            )
            for url in urls
        ]
        status_ok = await asyncio.gather(*tasks)

    return status_ok


def status_ok(urls, limit=200, authorize_from_browser=False, timeout=60):
    """Simultaneously detecting whether the given links are accessable.

    Parameters
    ----------
    urls: iterator
        iterator contains urls
    limit: int
        the number of urls connecting simultaneously
    authorize_from_browser: bool
        Whether to load cookies used by your web browser for authorization.
        This means you can use python to download data by logining in to website
        via browser (So far the following browsers are supported: Chrome,Firefox,
        Opera, Edge, Chromium"). It will be very usefull when website doesn't support
        "HTTP Basic Auth". Default is False.
    timeout: int
        Request to stop waiting for a response after a given number of seconds

    Return:
    ------
    a list of results (True or False)

    Example:
    -------
    ```python
    from data_downloader import downloader
    import numpy as np

    urls = np.array(['https://www.baidu.com',
    'https://www.bai.com/wrongurl',
    'https://cn.bing.com/',
    'https://bing.com/wrongurl',
    'https://bing.com/'] )

    status_ok = downloader.status_ok(urls)
    urls_accessable = urls[status_ok]
    tqdm.write(urls_accessable)
    ```
    """
    # solve the loop close  Error for python 3.8.x in windows platform
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop(selector)
    try:
        status_ok = loop.run_until_complete(
            creat_tasks_status_ok(urls, limit, authorize_from_browser, timeout)
        )
    # Zero-sleep to allow underlying connections to close
    finally:
        loop.close()

    return status_ok
