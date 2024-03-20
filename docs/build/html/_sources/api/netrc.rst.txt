.. _netrc:

netrc
=====

``.netrc`` is a file that contains login information for various servers. It's used by programs that need to log in to servers. It's a plain text file, and you can put your username and password in it. It's not secure, but it's convenient.

Netrc class
-----------

We use the ``Netrc`` class to manage the ``.netrc`` file. 

.. autoclass:: data_downloader.downloader.Netrc
    :members:
    :undoc-members:
    :member-order: bysource
    :show-inheritance:

Auxiliary functions
-------------------

.. automethod:: data_downloader.downloader.get_url_host

.. automethod:: data_downloader.downloader.get_netrc_auth