==========================
GPM Data Download Tutorial
==========================

This tutorial demonstrates how to download GPM data from the GES DISC website.

1. Finding Data
---------------

You can find and download GPM data on GES DISC: https://disc.gsfc.nasa.gov/datasets?keywords=GPM&page=1

Many datasets are now available on the GPM official website. To quickly locate data, we can use filtering options such as ``Measurement``, ``Project``, ``Spatial Resolution``, etc.

.. image:: /_static/images/gpm/filter.png
    :width: 90%
    :align: center

Select the dataset with the desired temporal and spatial resolution, then click ``Subset/Get Data``.

.. image:: /_static/images/gpm/subset.png
    :width: 90%
    :align: center

Choose the desired time range, spatial range (West, South, East, North), variables, output file format, etc., and click ``Get Data`` in the bottom right corner to retrieve the data.

.. note::
    
    - The first method can only download data in the global range.
    - The second methods can download data in a specific region.

.. image:: /_static/images/gpm/meth_option.png
    :width: 90%
    :align: center


In the pop-up interface, click ``Download links list`` to download the file containing image URLs.

.. image:: /_static/images/gpm/link_list.png
    :width: 90%
    :align: center

2. Download data
----------------

2.1. Authorization
^^^^^^^^^^^^^^^^^^

Downloading GPM data requires a NASA account. If you don't have one, please register at the https://urs.earthdata.nasa.gov/users/new. 
**GPM uses NASA accounts that require authorization.** Please follow the official tutorial for authorization: https://disc.gsfc.nasa.gov/earthdata-login


.. tip::

    Creating ``.netrc`` file allows you to save the account and password information for websites. When the program downloads, it will automatically read the corresponding account and password from this file, eliminating the need for repeated user input.

Replace ``your_username`` and ``your_password`` in the code below with your own username and password registered on the NASA official website, and execute it in a Python editor.

.. code-block:: python

    from data_downloader import downloader

    netrc = downloader.Netrc()
    netrc.add('urs.earthdata.nasa.gov','your_username','your_password')


After execution, a ``.netrc`` file will be created in the user's directory. 

.. note::

    If the account or password is entered incorrectly, set ``overwrite=True`` in the code above to overwrite the account and password in the ``.netrc`` file.

    .. code-block:: python

        netrc.add('urs.earthdata.nasa.gov', 'your_username','your_password', overwrite=True)


2.2. Bulk Download
^^^^^^^^^^^^^^^^^^

Create a Python file, copy the code below, change the ``folder_out`` and ``url_file`` paths according to your situation, and execute to download files in bulk.

.. tip::

    - ``DataDownloader`` can **automatically skip already downloaded files** and **supports breakpoint resume** (currently only ``Download Method 1`` supports breakpoint resume). Therefore, if the download is interrupted and some files are incompletely downloaded, you can directly re-execute the script to continue downloading.
    -  If the script indicates that it cannot get file size information from the website (opendap, ``Download Method 2`` may have this issue), you need to manually judge whether the file is completely downloaded and manually delete incompletely downloaded files.


.. code-block:: python

    from data_downloader import downloader, parse_urls

    # File output directory
    folder_out = '/media/fancy/gpm'
    # Path of the file containing URLs
    url_file = "/media/fancy/gpm/subset_GPM_3IMERGM_06_20200513_134318.txt"

    urls = parse_urls.from_file(url_file)
    downloader.download_datas(urls, folder_out)