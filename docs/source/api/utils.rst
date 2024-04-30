.. _utils:


utils
=====

This module contains classes and functions of general utility used in multiple places throughout ``data_downloader``. 

pairs module
------------

This module contains the :class:`.Pair` and :class:`.Pairs` classes to handle pairs of InSAR data, which are the simplified versions from the `FanInSAR <https://faninsar.readthedocs.io/en/latest/>`_ package.

.. csv-table::
   :header: "Class", "Description"

   ":class:`.Pair`", "A class to handle **one pair** of InSAR data."
   ":class:`.Pairs`", "A class to handle **multiple pairs** of InSAR data."

Pair
^^^^

.. autoclass:: data_downloader.utils.Pair
    :members:
    :member-order: bysource
    :show-inheritance:


Pairs
^^^^^

.. autoclass:: data_downloader.utils.Pairs
    :members:
    :member-order: bysource
    :show-inheritance:

    