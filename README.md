<h1 align="center">
<img src="https://raw.githubusercontent.com/Fanchengyan/data-downloader/master/docs/source/_static/logo/logo.svg" width="300">
</h1><br>


[![Downloads](https://static.pepy.tech/badge/data_downloader)](https://pepy.tech/project/data_downloader) [![PyPI](https://img.shields.io/pypi/v/data_downloader)](https://pypi.org/project/data_downloader/) [![Documentation Status](https://readthedocs.org/projects/data-downloader/badge/?version=latest)](https://data-downloader.readthedocs.io/en/latest/?badge=latest)

Make downloading scientific data much easier

## Introduction

DataDownloader is a user-friendly package for downloading files using HTTP/HTTPS. It currently includes a `downloader` module for downloading files, a `parse_urls` module for parsing URLs, and a `services` module for managing well-known online services.

## Highlight Features

DataDownloader has several features to make retrieving files easy, including:

* **Resumable**: You can resume aborted downloads automatically when you re-execute the code if website support resuming (status code is 216 or 416 when send a HEAD request to the server supplying a Range header)
* **Asynchronous**: Can download multiple files at the same time when download a single file very slow. 
* **Convenient**: Provide a easy way to manage your username and password and parse urls from different sources:
  * **netrc**: Provide a convenient way to manage your username and password via ``.netrc`` file, avoiding providing your login information over and over again.
  * **parse_urls**: Provide various methods to parse urls from different sources. See sections :ref:`parse_urls` for more details
  * **services**: Provide a convenient way to manage well-known online services, currently support: HyP3, LiCSAR, Sentinel-1 orbit. 

## Installation

You can install `DataDownloader` via pip from [PyPI](https://pypi.org/project/data_downloader/):

```bash
pip install data_downloader
```

or you can install the latest version from [GitHub](https://github.com/Fanchengyan/data-downloader):

```bash
pip install git+hhttps://github.com/Fanchengyan/data-downloader.git
```
## Usage

The detailed documentation is available at: <https://data-downloader.readthedocs.io/en/latest/>