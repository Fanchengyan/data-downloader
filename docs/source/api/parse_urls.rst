.. _parse_urls:

parse_urls
==========

Functions and Classes for parsing urls from different sources.

* Functions
    * :func:`.from_urls_file`
    * :func:`.from_html`
    * :func:`.from_sentinel_meta4`
    * :func:`.from_EarthExplorer_order`
* Class
    * :class:`.HyP3Service`
    * :class:`.LiCSARService`
    * :class:`.SentinelOrbit`

* Auxiliary Classes
    * :class:`.Jobs`
    * :class:`.JOB_TYPE`
    * :class:`.STATUS_CODE`

Functions
---------

.. autofunction:: data_downloader.parse_urls.from_urls_file

.. autofunction:: data_downloader.parse_urls.from_html

.. autofunction:: data_downloader.parse_urls.from_sentinel_meta4

.. autofunction:: data_downloader.parse_urls.from_EarthExplorer_order


Classes
-------

HyP3Service
^^^^^^^^^^^

.. autoclass:: data_downloader.parse_urls.HyP3Service
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

LiCSARService
^^^^^^^^^^^^^

.. autoclass:: data_downloader.parse_urls.LiCSARService
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

SentinelOrbit
^^^^^^^^^^^^^

.. autoclass:: data_downloader.parse_urls.SentinelOrbit
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:


Auxiliary Classes
-----------------

Jobs
^^^^

.. autoclass:: data_downloader.parse_urls.hyp3.Jobs
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

JOB_TYPE
^^^^^^^^

.. autoclass:: data_downloader.parse_urls.hyp3.JOB_TYPE
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

STATUS_CODE
^^^^^^^^^^^

.. autoclass:: data_downloader.parse_urls.hyp3.STATUS_CODE
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:
