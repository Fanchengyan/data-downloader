.. _example_licsar:

======================================
LiCSAR Interferogram Download Tutorial
======================================

This tutorial demonstrates how to download LiCSAR interferograms from the LiCSAR online service.

:class:`LiCSARService <data_downloader.services.LiCSARService>` provides a simple interface to the LiCSAR online service for the retrieval of Sentinel-1 interferograms. The service is provided by Centre for the Observation and Modelling of Earthquakes, Volcanoes and Tectonics (COMET) and is available at: https://comet.nerc.ac.uk/COMET-LiCS-portal/

Following is a simple example of how to use the service to retrieve interferograms for a given frame "106D_05248_131313".

.. code-block:: python

    from pathlib import Path
    import pandas as pd
    from data_downloader import downloader, services

    # specify the folder to save data
    home_dir = Path("/Volumes/Data/LiCSAR/106D_05248_131313/")
    pair_dir = home_dir / "GEOC"

    # init LiCSARService by frame id
    licsar = services.LiCSARService("106D_05248_131313")

Get URLs 
~~~~~~~~

Once LiCSARService is initialized, the urls of the interferograms, coherence, and metadata will be available in attributes ``pair_urls``, ``coh_urls``, and ``meta_urls`` respectively. 

Consequently, you can download the data by calling the :func:`downloader.download_datas() <data_downloader.downloader.download_datas>` method.

Download metadata
~~~~~~~~~~~~~~~~~

For example, to download the metadata of the frame:

.. code-block:: python

    downloader.download_datas(licsar.meta_urls, folder=home_dir, desc="Metadata")

Download all pairs
~~~~~~~~~~~~~~~~~~

To download all interferogram and coherence data, you can 
directly specify the urls and download them by calling the :func:`downloader.download_datas() <data_downloader.downloader.download_datas>` method.

.. code-block:: python

    downloader.download_datas(licsar.pair_urls, folder=pair_dir, desc="Interferograms")
    downloader.download_datas(licsar.coh_urls, folder=pair_dir, desc="Coherence")

Download selected pairs
~~~~~~~~~~~~~~~~~~~~~~~ 

LiCSARService provides a convenient way to filter the interferograms by providing the :attr:`LiCSARService.pairs <data_downloader.services.LiCSARService.pairs>` attribute, which is a instance of :class:`~data_downloader.utils.Pairs` containing the primary dates, secondary dates, and days span of the pairs.

Therefore, you can filter the urls by specifying the primary dates, secondary dates and day span of pairs.

For example, to download the interferograms of the frame from "2019-01-01" to "2019-12-31" with a temporal baseline less than 60 days:

.. code-block:: python

    # generate mask data by primary_dates, secondary_dates and day span of pairs
    pairs = licsar.pairs
    mask = (pairs.primary>pd.to_datetime("2019-01-01")) & (pairs.primary<pd.to_datetime("2019-12-31")) & (pairs.days <= 60)

    # download interferogram and coherence files filtered by mask
    downloader.download_datas(licsar.ifg_urls[mask].values, folder=pair_dir, desc="Interferogram")
    downloader.download_datas(licsar.coh_urls[mask], folder=pair_dir, desc="Coherence")



