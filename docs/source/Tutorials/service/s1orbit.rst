.. _example_s1orbit:

=======================================
Sentinel-1 Orbit Data Download Tutorial
=======================================

This tutorial demonstrates how to download Sentinel-1 orbit data from the ASF DAAC.

:class:`~data_downloader.services.SentinelOrbit` is a class used to download Sentinel-1 orbit data from the ASF DAAC. It provides two methods to get the download links of the auxiliary calibration data and precise orbit data, respectively:

- :meth:`~data_downloader.services.SentinelOrbit.cal_urls` for retrieval of the auxiliary calibration data links.
- :meth:`~data_downloader.services.SentinelOrbit.poeorb_urls` for retrieval of the precise orbit data links.

Following is a simple example of how to use the service to retrieve the auxiliary calibration data and precise orbit data of Sentinel-1.

.. note::

    The ``platform`` here is an optional parameter to specify the satellite platform, which can be "S1A", "S1B", or "all". If not specified, the default value is "all".

.. code-block:: python

    from data_downloader import downloader, services
    from pathlib import Path

    # specify the folder to save aux_cal
    folder_cal = Path("/media/data/aux_cal")  
    # specify the folder to save aux_poeorb
    folder_preorb = Path("/media/data/poeorb")  

    # init SentinelOrbit:
    s1_orbit = services.SentinelOrbit()

    # Get all aux_cal data links of S1A and S1B and download them:
    urls_cal = s1_orbit.cal_urls(platform="all")
    downloader.async_download_datas(urls_cal, folder=folder_cal)

    # Get all precise orbit data links of S1A during 20210101-20220301 and download them:
    urls_preorb = s1_orbit.poeorb_urls(
        date_start="20210101", date_end="20220301", platform="S1A"
    )
    downloader.download_datas(urls_preorb, folder=folder_preorb)

