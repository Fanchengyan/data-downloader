# data_downloader

[![Downloads](https://static.pepy.tech/badge/data_downloader)](https://pepy.tech/project/data_downloader) [![PyPI](https://img.shields.io/pypi/v/data_downloader)](https://pypi.org/project/data_downloader/) [![Documentation Status](https://readthedocs.org/projects/data-downloader/badge/?version=latest)](https://data-downloader.readthedocs.io/en/latest/?badge=latest)

Make downloading scientific data much easier

## Introduction

`data_downloader` is a very convenient and powerful data download package for retrieving files using HTTP/HTTPS. It current includes download model `downloader` and url parsing model `parse_urls`. As `httpx` was used which provided a method to access website with synchronous and asynchronous way, you can download multiple files at the same time.

## Highlight Features

data_downloader has several features to make retrieving files easy, including:

* **Resumable**: You can resume aborted downloads automatically when you re-execute the code if website support resuming (status code is 216 or 416 when send a HEAD request to the server supplying a Range header)
* **Asynchronous**: Can download multiple files at the same time when download a single file very slow. 
* **Convenient**: Provide a easy way to manage your username and password and parse urls from different sources:
  * **netrc**: Provide a convenient way to manage your username and password via ``.netrc`` file. You don't need to input your username and password every time when you download files from a website which requires authentication. See sections :ref:`netrc` for more details
  * **parse_urls**: Provide various methods to parse urls from different sources. See sections :ref:`parse_urls` for more details

## Installation

You can install `data_downloader` via pip from [PyPI](https://pypi.org/project/data_downloader/):

```bash
pip install data_downloader
```

or you can install the latest version from [GitHub](https://github.com/Fanchengyan/data-downloader):

```bash
pip install git+hhttps://github.com/Fanchengyan/data-downloader.git
```
## Usage

The detailed documentation is available at: <https://data-downloader.readthedocs.io/en/latest/>