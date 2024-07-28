===========================================
parse_urls: Parse URLs from various sources
===========================================

:ref:`parse_urls` module provides basic functions to parse URLs from different sources. The module provides functions to parse URLs from:

.. csv-table:: Different functions to parse URLs
   :file: ../api/tables/parse_urls.csv
   :header-rows: 1

You can import ``parse_urls`` at the beginning.

.. code-block:: python

    from data_downloader import parse_urls

Following is a brief introduction to those functions.

from_file
---------

This function parses URLs from a given file, which only contains URLs. 

.. tip::

   This function is only useful when the file only contains URLs (one column). 
   If the file contains multiple columns, you are suggested to use ``pandas`` 
   to read the file.

Example:

.. code-block:: python

   from data_downloader import parse_urls, downloader

   url_file = '/media/fancy/gpm/subset_GPM_3IMERGM_06_20200513_134318.txt'
   urls = parse_urls.from_file(url_file)

   downloader.download_datas(urls, folder_out)

Here is an example of use case: :ref:`gpm_example`.

from_html
---------

This function parses URLs from a given HTML websites (url). It can parse URLs with a specific suffix and depth. Following example shows how to parse URLs with suffix ``.nc`` and depth 1.

Example:

.. code-block:: python

   from data_downloader import parse_urls

   url = 'https://cds-espri.ipsl.upmc.fr/espri/pubipsl/iasib_CH4_2014_uk.jsp'
   urls = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1)
   urls_all = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1, url_depth=1)

   print(f"Found {len(urls)} urls, {len(urls_all)} urls in total")

.. code-block:: none

   Found 357 urls, 2903 urls in total

.. currentmodule:: data_downloader.services


.. tip::

   This function is used to parse URLs for the :class:`LiCSARService` and 
   :class:`SentinelOrbit` services. For more details, you can refer to the 
   source code of these services.