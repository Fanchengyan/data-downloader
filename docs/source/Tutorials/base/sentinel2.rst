=================================
Sentinel-2 Data Download Tutorial
=================================

This tutorial demonstrates how to download Sentinel-2 data from the `Sentinel official website <https://scihub.copernicus.eu/dhus/#/home>`_.

1. Select data
==============

Go to the Sentinel official website: <https://scihub.copernicus.eu/dhus/#/home>, log in to your account (if you don't have one, register), and select the desired data to add to your cart.


2. Download data 
================

2.1 Download link file
----------------------

Open the cart, do not select any acquisition, and click on the download icon in the bottom right corner. This will download a ``products.meta4`` file containing the download links.

.. image:: /_static/images/sentinel2/cart.png
    :width: 500px
    :align: center


2.2 Create ``.netrc`` file
--------------------------

.. tip::

    Creating ``.netrc`` file allows you to save the account and password information for websites. When the program downloads, it will automatically read the corresponding account and password from this file, eliminating the need for repeated user input.

To download Sentinel data, you need an account and password. If you don't have one, please register on the official website.

Replace ``your_username`` and ``your_password`` in the code below with your own username and password registered on the Sentinel official website, and execute it in a Python editor.

.. code-block:: python

    from data_downloader import downloader

    netrc = downloader.Netrc()
    netrc.add('scihub.copernicus.eu','your_username','your_password')


After execution, a ``.netrc`` file will be created in the user's directory. 

.. note::

    If the account or password is entered incorrectly, set ``overwrite=True`` in the code above to overwrite the account and password in the ``.netrc`` file.

    .. code-block:: python

        netrc.add('scihub.copernicus.eu', 'your_username','your_password', overwrite=True)


2.3 Bulk Download
-----------------

Create a Python file, copy the code below, and modify the ``folder_out`` and ``url_file`` paths according to your situation. Then execute it to download files in bulk.

.. tip::

    ``DataDownloader`` can **automatically skip downloaded files** and **support resumable downloads**. If the download is interrupted and some files are incomplete, simply re-execute this script.

.. code-block:: python

    from data_downloader import downloader, parse_urls

    # File output directory, make sure this folder exists
    folder_out = r'D:\Sentinel-2 Data'
    # The products.meta4 file containing URLs downloaded in the first step
    url_file = r'C:\Users\Your Username\Desktop\products.meta4'

    # Parse the URL file
    urls = parse_urls.from_sentinel_meta4(url_file)

    # Download data
    downloader.download_datas(urls, folder_out)

.. image:: /_static/images/sentinel2/download.png
    :width: 95%
    :align: center
