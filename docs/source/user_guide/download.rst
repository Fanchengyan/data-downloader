downloader: Download files from urls
====================================

There are several functions in the :ref:`downloader` module. The following table lists all the functions used to download files from urls.

.. currentmodule:: data_downloader.downloader

.. csv-table::
   :file: ../api/tables/downloader.csv
   :header-rows: 1

You can import downloader at the beginning.

.. code-block:: python

    from data_downloader import downloader



Following is a brief introduction to those functions.


.. _example_download_data:

download_data
-------------

This function is design for downloading a single file. 

.. note::
    
    This function can only download one file at a time. If a lot of files need to be downloaded, try to use :ref:`example_download_datas`, :ref:`example_async_download_datas` or :ref:`example_mp_download_datas` functions.

Example:

.. code-block:: python

    In [6]: url = 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_201
       ...: 41211.geo.unw.tif'
       ...:  
       ...: folder = 'D:\\data'
       ...: downloader.download_data(url,folder)

    20141117_20141211.geo.unw.tif:   2%|▌                   | 455k/22.1M [00:52<42:59, 8.38kB/s]

.. _example_download_datas:

download_datas
--------------

Download multiple files from a list like object that contains urls one by one.

Example:

.. code-block:: python

    In [12]: from data_downloader import downloader 
        ...:  
        ...: urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20
        ...: 141211.geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221
        ...: .geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128
        ...: .geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221
        ...: .geo.cc.tif']  
        ...:  
        ...: folder = 'D:\\data'         G, param_names = GC.ftc_model1(t1s, t2s, t3s, t4s, years, ftc)
        ...: downloader.download_datas(urls,folder)

    20141117_20141211.geo.unw.tif:   6%|█           | 1.37M/22.1M [03:09<2:16:31, 2.53kB/s]

.. _example_async_download_datas:

async_download_datas
--------------------

Download files simultaneously with asynchronous mode. 

.. note::
    
    Not all websites support downloading multiple files simultaneously. If the 
    website doesn't allow parallel downloading, the download by this function
    may be incomplete. Try to use :ref:`example_download_datas` instead if you 
    encounter this problem.

Example:

.. code-block:: python

    In [3]: from data_downloader import downloader 
       ...:  
       ...: urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049
       ...: _131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif', 
       ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_13131
       ...: 3/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif']  
       ...:  
       ...: folder = 'D:\\data' 
       ...: downloader.async_download_datas(urls,folder,limit=3,desc='interferograms')

    >>> Total | Interferograms :   0%|                          | 0/7 [00:00<?, ?it/s]
        20141024_20150221.geo.unw.tif:  11%|▌    | 2.41M/21.2M [00:11<41:44, 7.52kB/s]
        20141117_20141211.geo.unw.tif:   9%|▍    | 2.06M/22.1M [00:11<25:05, 13.3kB/s]
        20141024_20150128.geo.cc.tif:  36%|██▏   | 1.98M/5.42M [00:12<04:17, 13.4kB/s] 
        20141117_20150317.geo.cc.tif:   0%|               | 0.00/5.44M [00:00<?, ?B/s]
        20141117_20150221.geo.cc.tif:   0%|               | 0.00/5.47M [00:00<?, ?B/s]
        20141024_20150128.geo.unw.tif:   0%|              | 0.00/23.4M [00:00<?, ?B/s]
        20141211_20150128.geo.cc.tif:   0%|               | 0.00/5.44M [00:00<?, ?B/s]

.. _example_mp_download_datas:

mp_download_datas
-----------------

Download files simultaneously using multiprocessing. 

.. note::
    
    Not all websites support downloading multiple files simultaneously. If the 
    website doesn't allow parallel downloading, the download by this function
    may be incomplete. Try to use :ref:`example_download_datas` instead if you 
    encounter this problem.

Example:

.. code-block:: python

    In [12]: from data_downloader import downloader 
        ...:  
        ...: urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20
        ...: 141211.geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221
        ...: .geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128
        ...: .geo.unw.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317
        ...: .geo.cc.tif', 
        ...: 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221
        ...: .geo.cc.tif']  
        ...:  
        ...: folder = 'D:\\data' 
        ...: downloader.mp_download_datas(urls,folder)

     >>> 12 parallel downloading
     >>> Total | :   0%|                                         | 0/7 [00:00<?, ?it/s]
    20141211_20150128.geo.cc.tif:  15%|██▊                | 803k/5.44M [00:00<?, ?B/s]

.. _example_status_ok:

status_ok
---------

Simultaneously detecting whether the given links are accessible.

Example:

.. code-block:: python

    In [1]: from data_downloader import downloader
       ...: import numpy as np
       ...: 
       ...: urls = np.array(['https://www.baidu.com',
       ...: 'https://www.bai.com/wrongurl',
       ...: 'https://cn.bing.com/',
       ...: 'https://bing.com/wrongurl',
       ...: 'https://bing.com/'] )
       ...: 
       ...: status_ok = downloader.status_ok(urls)
       ...: urls_accessable = urls[status_ok]
       ...: print(urls_accessable)

    ['https://www.baidu.com' 'https://cn.bing.com/' 'https://bing.com/']