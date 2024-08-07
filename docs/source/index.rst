==========================================
Welcome to DataDownloader's documentation!
==========================================

.. image:: https://static.pepy.tech/badge/data_downloader
    :target: https://pepy.tech/project/data_downloader
    :alt: Downloads

.. image:: https://img.shields.io/pypi/v/data_downloader
    :target: https://pypi.org/project/data_downloader/
    :alt: PyPI

.. image:: https://readthedocs.org/projects/data-downloader/badge/?version=latest
    :target: https://data-downloader.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

Make downloading scientific data much easier

Introduction
------------

DataDownloader is a user-friendly package for downloading files using HTTP/HTTPS. It currently includes a :ref:`downloader` module for downloading files, a :ref:`parse_urls` module for parsing URLs, and a :ref:`services` module for managing well-known online services.

Highlight Features
------------------

DataDownloader has several features to make retrieving files easy, including:

* **Resumable**: You can resume aborted downloads automatically when you re-execute the code if website support resuming (status code is 216 or 416 when send a HEAD request to the server supplying a Range header)
* **Asynchronous**: Can download multiple files at the same time when download a single file very slow. 
* **Convenient**: Provide a easy way to manage your username and password and parse urls from different sources:

  * **netrc**: Provide a convenient way to manage your username and password via ``.netrc`` file, avoiding providing your login information over and over again. See sections :ref:`netrc` for more details.
  * **parse_urls**: Provide various methods to parse urls from different sources. See sections :ref:`parse_urls` for more details
  * **services**: Provide a convenient way to manage well-known online services, currently support: HyP3, LiCSAR, Sentinel-1 orbit data. See sections :ref:`services` for more details


.. https://sphinx-design.readthedocs.io/en/latest/cards.html

.. .. grid:: 2
..     :gutter: 1

..     .. grid-item-card::

..         A

..     .. grid-item-card::

..         B

.. .. grid:: 2
..     :gutter: 3 3 4 5

..     .. grid-item-card::

..         A

..     .. grid-item-card::

..         B

.. toctree::
    :maxdepth: 2
    :caption: Contents of Documentation

    install
    user_guide/index
    Tutorials/index
    API Reference <api/index>
    changelog
