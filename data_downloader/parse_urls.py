from __future__ import annotations

from pathlib import Path
from typing import Optional, Union
from urllib.parse import urljoin
from xml.dom.minidom import parse

import requests
from bs4 import BeautifulSoup

from data_downloader.downloader import get_netrc_auth, get_url_host


def from_file(url_file: str | Path) -> list:
    """parse urls from a file which only contains urls

    .. versionadded:: 1.2

    Parameters:
    -----------
    url_file: str
        path to file which only contains urls

    Return:
    -------
    a list contains urls
    """
    with open(url_file) as f:
        urls = [i.strip() for i in f.readlines()]
    return urls


def from_urls_file(url_file: str | Path) -> list:
    """parse urls from a file which only contains urls

    .. warning::
        This function will be deprecated in the future. Please use :func:`from_file` instead.

    .. seealso:: :func:`from_file`

    Parameters:
    -----------
    url_file: str
        path to file which only contains urls

    Return:
    -------
    a list contains urls
    """
    return from_file(url_file)


def from_sentinel_meta4(url_file: str | Path) -> list:
    """parse urls from sentinel `products.meta4` file downloaded from
    https://scihub.copernicus.eu/dhus

    Parameters:
    -----------
    url_file: str
        path to products.meta4

    Return:
    -------
    a list contains urls
    """
    data = parse(url_file).documentElement
    urls = [i.childNodes[0].nodeValue for i in data.getElementsByTagName("url")]
    return urls


def from_html(
    url: str,
    suffix: Optional[str] = None,
    suffix_depth: int = 0,
    url_depth: int = 0,
) -> list:
    """parse urls from html website

    Parameters:
    -----------
    url: str
        the website contains data
    suffix: list, optional
        data format. suffix should be a list contains multipart.
        if suffix_depth is 0, all '.' will parsed.
        Examples:

        - when set 'suffix_depth=0':
            - suffix of 'xxx8.1_GLOBAL.nc' should be ['.1_GLOBAL', '.nc']
            - suffix of 'xxx.tar.gz' should be ['.tar', '.gz']
        - when set 'suffix_depth=1':
            - suffix of 'xxx8.1_GLOBAL.nc' should be ['.nc']
            - suffix of 'xxx.tar.gz' should be ['.gz']
    suffix_depth: int
        Number of suffixes
    url_depth: int
        depth of url in website will parsed

    Return:
    -------
    a list contains urls

    Example:
    --------
    >>> from downloader import parse_urls

    >>> url = 'https://cds-espri.ipsl.upmc.fr/espri/pubipsl/iasib_CH4_2014_uk.jsp'
    >>> urls = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1)
    >>> urls_all = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1, url_depth=1)
    >>> print(len(urls_all)-len(urls))
    """

    def match_suffix(href, suffix):
        if suffix:
            sf = Path(href).suffixes[-suffix_depth:]
            return suffix == sf
        else:
            return True

    r_h = requests.head(url)
    if "text/html" in r_h.headers["Content-Type"]:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        a = soup.find_all("a")
        urls_all = [urljoin(url, i["href"]) for i in a if i.has_attr("href")]
        urls = [i for i in urls_all if match_suffix(i, suffix)]
        if url_depth > 0:
            urls_notdata = sorted(set(urls_all) - set(urls))
            urls_depth = [
                from_html(_url, suffix, suffix_depth, url_depth - 1)
                for _url in urls_notdata
            ]

            for u in urls_depth:
                if isinstance(u, list):
                    urls.extend(u)

        return sorted(set(urls))


def _retrieve_all_orders(url_host, email, auth):
    filters = {"status": "complete"}
    url = urljoin(url_host, f"/api/v1/list-orders/{email}")
    r = requests.get(url, params=filters, auth=auth)
    r.raise_for_status()
    all_orders = r.json()

    return all_orders


def _retrieve_urls_from_order(url_host, orderid, auth):
    filters = {"status": "complete"}
    url = urljoin(url_host, f"/api/v1/item-status/{orderid}")
    r = requests.get(url, params=filters, auth=auth)
    r.raise_for_status()
    urls_info = r.json()
    if isinstance(urls_info, dict):
        messages = urls_info.pop("messages", dict())
        if messages.get("errors"):
            raise Exception("{}".format(messages.get("errors")))
        if messages.get("warnings"):
            print(">>> Warning: {}".format(messages.get("warnings")))

    if orderid not in urls_info:
        raise ValueError(f"Order ID{orderid} not found")
    urls = [
        i.get("product_dload_url")
        for i in urls_info[orderid]
        if i.get("product_dload_url") != ""
    ]

    return urls


def from_EarthExplorer_order(
    username: Optional[str] = None,
    passwd: Optional[str] = None,
    email: Optional[str] = None,
    order: Optional[Union[str, dict]] = None,
    url_host: Optional[str] = None,
) -> dict:
    """parse urls from orders in earthexplorer.

    Reference: [bulk-downloader](https://code.usgs.gov/espa/bulk-downloader)

    Parameters:
    -----------
    username, passwd: str, optional
        your username and passwd to login in EarthExplorer. Could be
        None when you have save them in .netrc
    email: str, optional
        email address for the user that submitted the order
    order: str or dict
        which order to download. If None, all orders retrieved from
        EarthExplorer will be used.
    url_host: str
        if host is not USGS ESPA

    Return:
    -------
    a dict in format of {orderid: urls}

    Example:
    --------
    >>> from pathlib import Path
    >>> from data_downloader import downloader, parse_urls
    >>> folder_out = Path('D:\\data')
    >>> urls_info = parse_urls.from_EarthExplorer_order('your username', 'your passwd')
    >>> for odr in urls_info.keys():
    >>>     folder = folder_out.joinpath(odr)
    >>>     if not folder.exists():
    >>>         folder.mkdir()
    >>>     urls = urls_info[odr]
    >>>     downloader.download_datas(urls, folder)
    """
    # init parameters
    email = email if email else ""
    if url_host is None:
        url_host = "https://espa.cr.usgs.gov"
    host = get_url_host(url_host)

    auth = get_netrc_auth(host)
    if (auth == username) or (auth == passwd):
        raise ValueError(
            "username and passwd neither be found in netrc or"
            " be assigned in parameter"
        )
    elif not auth:
        auth = (username, passwd)

    # refine oders
    if not order:
        orders = _retrieve_all_orders(url_host, email, auth)
    else:
        if isinstance(order, str):
            orders = [order]
        else:
            try:
                orders = list(order)
            except:
                raise ValueError("order must be str or list of str")

    urls_info = {}
    for odr in orders:
        urls = _retrieve_urls_from_order(url_host, odr, auth)
        if urls:
            urls_info.update({odr: urls})
        else:
            print(
                f">>> Warning: Data for order id {odr} have expired."
                " Please reorder it again if you want to use it anymore"
            )
    return urls_info
