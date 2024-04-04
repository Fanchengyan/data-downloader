.. _services:

services
========

The ``services`` module provides a easy way to interact with the well-known services:

.. csv-table:: Services and corresponding classes
   :file: tables/services.csv
   :header-rows: 1


.. csv-table:: Auxiliary classes for the HyP3
    :file: tables/hyp3.csv
    :header-rows: 1



Online Services
---------------

HyP3
^^^^

.. autoclass:: data_downloader.services.HyP3Service
    :members:
    :member-order: bysource
    :show-inheritance:

.. autoclass:: data_downloader.services.InSARMission
    :members:
    :member-order: bysource
    :show-inheritance:

.. autoclass:: data_downloader.services.InSARBurstMission
    :members:
    :member-order: bysource
    :show-inheritance:

LiCSAR
^^^^^^

.. autoclass:: data_downloader.services.LiCSARService
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

Sentinel-1 Orbit
^^^^^^^^^^^^^^^^

.. autoclass:: data_downloader.services.SentinelOrbit
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:


Auxiliary classes for the HyP3
------------------------------

Jobs
^^^^

.. autoclass:: data_downloader.services.hyp3.Jobs
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

JOB_TYPE
^^^^^^^^

.. autoclass:: data_downloader.services.hyp3.JOB_TYPE
    :members: 
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

STATUS_CODE
^^^^^^^^^^^

.. autoclass:: data_downloader.services.hyp3.STATUS_CODE
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:
