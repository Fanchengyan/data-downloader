"""Module for parsing URLs from various sources."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from xml.dom.minidom import parse

import requests
from bs4 import BeautifulSoup

from data_downloader.downloader import get_netrc_auth, get_url_host
from data_downloader.logging import setup_logger

logger = setup_logger(__name__)


def from_file(url_file: str | Path) -> list:
    """Parse urls from a file which only contains urls.

    .. versionadded:: 1.2

    Parameters
    ----------
    url_file: str
        path to file which only contains urls

    Return:
    -------
    a list contains urls

    """
    with Path(url_file).open() as f:
        return [i.strip() for i in f]


def from_urls_file(url_file: str | Path) -> list:
    """Parse urls from a file which only contains urls.

    .. warning::
        This function will be deprecated in the future. Please use :func:`from_file` instead.

    .. seealso:: :func:`from_file`

    Parameters
    ----------
    url_file: str
        path to file which only contains urls

    Return:
    -------
    a list contains urls

    """
    warnings.warn(
        "from_urls_file will be deprecated in the future. Please use from_file instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return from_file(url_file)


def from_sentinel_meta4(url_file: str | Path) -> list:
    """Parse urls from sentinel `products.meta4` file downloaded from https://scihub.copernicus.eu/dhus.

    Parameters
    ----------
    url_file: str
        path to products.meta4

    Return:
    -------
    a list contains urls

    """
    data = parse(str(url_file)).documentElement
    return [i.childNodes[0].nodeValue for i in data.getElementsByTagName("url")]


def from_html(
    url: str,
    suffix: list[str] | None = None,
    suffix_depth: int = 0,
    url_depth: int = 0,
) -> list:
    """Parse urls from html website.

    Parameters
    ----------
    url: str
        the website contains data
    suffix: list[str] | None, optional
        data format. suffix should be a list contains multipart.
        if suffix_depth is 0, all '.' will parsed.
    suffix_depth: int
        Number of suffixes
    url_depth: int
        depth of url in website will parsed

    Examples
    --------
        - when set 'suffix_depth=0':
            - suffix of 'xxx8.1_GLOBAL.nc' should be ['.1_GLOBAL', '.nc']
            - suffix of 'xxx.tar.gz' should be ['.tar', '.gz']
        - when set 'suffix_depth=1':
            - suffix of 'xxx8.1_GLOBAL.nc' should be ['.nc']
            - suffix of 'xxx.tar.gz' should be ['.gz']

    Return:
    -------
    a list contains urls

    Example:
    --------
    >>> from downloader import parse_urls

    >>> url = "https://cds-espri.ipsl.upmc.fr/espri/pubipsl/iasib_CH4_2014_uk.jsp"
    >>> urls = parse_urls.from_html(url, suffix=[".nc"], suffix_depth=1)
    >>> urls_all = parse_urls.from_html(
    ...     url, suffix=[".nc"], suffix_depth=1, url_depth=1
    ... )
    >>> print(len(urls_all) - len(urls))

    """
    r_h = requests.head(url)
    if "text/html" in r_h.headers["Content-Type"]:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        a = soup.find_all("a")
        urls_all = [urljoin(url, i["href"]) for i in a if i.has_attr("href")]
        urls = [i for i in urls_all if match_suffix(i, suffix, suffix_depth)]
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
    msg = f"URL {url} is not a HTML page"
    logger.warning(msg)
    return []


def _retrieve_all_orders(
    url_host: str, email: str, auth: tuple[str, str] | None
) -> list[Any]:
    filters = {"status": "complete"}
    url = urljoin(url_host, f"/api/v1/list-orders/{email}")
    r = requests.get(url, params=filters, auth=auth)
    r.raise_for_status()
    all_orders = r.json()

    return all_orders


def _retrieve_urls_from_order(
    url_host: str, orderid: str, auth: tuple[str, str] | None
) -> list[str]:
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
    username: str | None = None,
    passwd: str | None = None,
    email: str | None = None,
    order: str | dict | None = None,
    url_host: str | None = None,
) -> dict:
    r"""Parse urls from orders in earthexplorer.

    Reference: [bulk-downloader](https://code.usgs.gov/espa/bulk-downloader)

    Parameters
    ----------
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
    >>> folder_out = Path("D:\\data")
    >>> urls_info = parse_urls.from_EarthExplorer_order("your username", "your passwd")
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
    if auth in (username, passwd):
        msg = (
            "username and passwd neither be found in netrc or be assigned in parameter"
        )
        raise ValueError(msg)
    if not auth:
        auth = (username, passwd)  # type: ignore

    # refine oders
    if not order:
        orders = _retrieve_all_orders(url_host, email, auth)  # type: ignore
    elif isinstance(order, str):
        orders = [order]
    else:
        try:
            orders = list(order)
        except Exception:
            msg = "order must be str or list of str"
            raise ValueError(msg) from None

    urls_info = {}
    for odr in orders:
        urls = _retrieve_urls_from_order(url_host, odr, auth)  # type: ignore
        if urls:
            urls_info.update({odr: urls})
        else:
            logger.warning(
                ">>> Warning: Data for order id %s have expired. "
                "Please reorder it again if you want to use it anymore",
                odr,
            )
    return urls_info


def match_suffix(href: str, suffix: list[str] | None, suffix_depth: int) -> bool:
    """Match the suffix of the href with the suffix.

    Parameters
    ----------
    href : str

    """
    if suffix is not None:
        sf = Path(href).suffixes[-suffix_depth:]
        return suffix == sf
    return True
