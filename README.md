# data-downloader

Make downloading scientific data much easier

## Introduction

data-downloader is a very convenient and powerful data download package for retrieving files using HTTP, HTTPS. It current includes download model `downloader` and url parsing model `parse_urls`. As `httpx` was used which provided a method to access website with synchronous and asynchronous way, you can download multiple files at the same time.

data-downloader has many features to make retrieving files easy, including:

- Can resume aborted downloads automatically when you re-execute the code if website support resuming (status code is 216 or 416 when send a HEAD request to the server supplying a Range header)
- Can download multiple files at the same time when download a single file very slow. There are two methods provided to achieve this function：
  - `async_download_datas` (recommend) function could download mare than 100 files at the same time as using asynchronous requests of `httpx`
  - `mp_download_datas` function depends on your CPU of computer as using `multiprocessing` package
- Provide a convenient way to manage your username and password via `.netrc` file or `authorize_from_browser` parameters. When the website requires the username and password, there is no need to provide it every time you download
- Provide a convenient way to parse urls. 
  - `from_urls_file` : parse urls of data from a file which only contains urls 
  - `from_sentinel_meta4` : parse urls from sentinel `products.meta4` file downloaded from <https://scihub.copernicus.eu/dhus>
  - `from_EarthExplorer_order` : parse urls from orders in EarthExplorer (same as `bulk-downloader`)
  - `from_html` : parse urls from html website


## 1. Installation

It is recommended to use the latest version of pip to install **data_downloader**.

``` BASH
pip install data_downloader
```

## 2. downloader Usage

All downloading functions are in `data_downloader.downloader` . So import `downloader` at the beginning.

``` Python
from data_downloader import downloader
```

### 2.1 Netrc

If the website needs to log in, you can add a record to a `.netrc` file in your home which contains your login information to avoid supplying username and password each time you download data.

To view existing hosts in `.netrc` file:

``` Python
netrc = downloader.Netrc()
print(netrc.hosts)
```

To add a record

``` Python
netrc.add(self, host, login, password, account=None, overwrite=False)
```

If you want to update a record, set tha parameter `overwrite=True` 

for NASA data user:

``` Python
netrc.add('urs.earthdata.nasa.gov','your_username','your_password')
```

You can use the `downloader.get_url_host(url)` to get the host name when you don't know the host of the website:

``` python
host = downloader.get_url_host(url)
```

To remove a record

``` Python
netrc.remove(self, host)
```

To clear all records

``` Python
netrc.clear()
```

**Example:**

``` Python
In [2]: netrc = downloader.Netrc()
In [3]: netrc.hosts
Out[3]: {}

In [4]: netrc.add('urs.earthdata.nasa.gov','username','passwd') 

In [5]: netrc.hosts
Out[5]: {'urs.earthdata.nasa.gov': ('username', None, 'passwd')}

In [6]: netrc
Out[6]:
machine urs.earthdata.nasa.gov
	login username
	password passwd

# This command only for linux user
In [7]: !cat ~/.netrc
machine urs.earthdata.nasa.gov
	login username
	password passwd

In [8]: url = 'https://gpm1.gesdisc.eosdis.nasa.gov/daac-bin/OTF/HTTP_services.cgi?FILENAME=%2Fdata%2FGPM_L3%2FGPM_3IMERGM.06%2F2000%2F3B-MO.MS.MRG.3IMERG.20000601-S000000-E235959.06.V06B.HDF5&FORMAT=bmM0Lw&BBOX=31.904%2C99.492%2C35.771%2C105.908&LABEL=3B-MO.MS.MRG.3IMERG.20000601-S000000-E235959.06.V06B.HDF5.SUB.nc4&SHORTNAME=GPM_3IMERGM&SERVICE=L34RS_GPM&VERSION=1.02&DATASET_VERSION=06&VARIABLES=precipitation'

In [9]: downloader.get_url_host(url)
Out[9]: 'gpm1.gesdisc.eosdis.nasa.gov'

In [10]: netrc.add(downloader.get_url_host(url),'username','passwd')

In [11]: netrc
Out[11]:
machine urs.earthdata.nasa.gov
        login username
        password passwd
machine gpm1.gesdisc.eosdis.nasa.gov
        login username
        password passwd

In [12]: netrc.add(downloader.get_url_host(url),'username','new_passwd')
>>> Warning: test_host existed, nothing will be done. If you want to overwrite the existed record, set overwrite=True

In [13]: netrc
Out[13]:
machine urs.earthdata.nasa.gov
        login username
        password passwd
machine gpm1.gesdisc.eosdis.nasa.gov
        login username
        password passwd

In [14]: netrc.add(downloader.get_url_host(url),'username','new_passwd',overwrite=True)

In [15]: netrc
Out[15]:
machine urs.earthdata.nasa.gov
        login username
        password passwd
machine gpm1.gesdisc.eosdis.nasa.gov
        login username
        password new_passwd

In [16]: netrc.remove(downloader.get_url_host(url))

In [17]: netrc
Out[17]:
machine urs.earthdata.nasa.gov
        login username
        password passwd

In [18]: netrc.clear()

In [19]: netrc.hosts
Out[19]: {}
```

### 2.2 download_data

This function is design for downloading a single file. Try to use `download_datas`, `mp_download_datas` or `async_download_datas` function if you have a lot of files to download

``` Python
downloader.download_data(url, folder=None, authorize_from_browser=False, file_name=None, client=None, allow_redirects=False, retry=0)
```

**Parameters:**

``` 
url: str
    url of web file
folder: str
    the folder to store output files. Default is current folder.
authorize_from_browser: bool
    whether to load cookies used by your web browser for authorization.
    This means you can use python to download data by logining in to website 
    via browser (So far the following browsers are supported: Chrome，Firefox, 
    Opera, Edge, Chromium"). It will be very usefull when website doesn't support
    "HTTP Basic Auth". Default is False.
file_name: str
    the file name. If None, will parse from web response or url.
    file_name can be the absolute path if folder is None.
client: httpx.Client() object
    client maintaining connection. Default is None
allow_redirects: bool
    Enables or disables HTTP redirects
retry: int 
    number of reconnects when status code is 503
```

**Example:**

``` Python
In [6]: url = 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_201
   ...: 41211.geo.unw.tif'
   ...:  
   ...: folder = 'D:\\data'
   ...: downloader.download_data(url,folder)

20141117_20141211.geo.unw.tif:   2%|▌                   | 455k/22.1M [00:52<42:59, 8.38kB/s]
```

### 2.3 download_datas

download datas from a list like object that contains urls. This function will download files one by one.

``` Python
downloader.download_datas(urls, folder=None, authorize_from_browser=False, file_names=None):
```

**Parameters:**

``` 
urls:  iterator
    iterator contains urls
folder: str
    the folder to store output files. Default is current folder.
authorize_from_browser: bool
    whether to load cookies used by your web browser for authorization.
    This means you can use python to download data by logining in to website 
    via browser (So far the following browsers are supported: Chrome，Firefox, 
    Opera, Edge, Chromium"). It will be very usefull when website doesn't support
    "HTTP Basic Auth". Default is False.
file_names: iterator
    iterator contains names of files. Leaving it None if you want the program to parse
    them from website. file_names can cantain the absolute paths if folder is None.
```

**Examples:**

``` python
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
    ...: downloader.download_datas(urls,folder)

20141117_20141211.geo.unw.tif:   6%|█           | 1.37M/22.1M [03:09<2:16:31, 2.53kB/s]
```

### 2.4 mp_download_datas
Download files simultaneously using multiprocessing. The website that don't support resuming may download incompletely. You can use `download_datas` instead

``` Python
downloader.mp_download_datas(urls, folder=None,  authorize_from_browser=False, file_names=None,ncore=None, desc='')
```


**Parameters:**

``` 
urls:  iterator
    iterator contains urls
folder: str
    the folder to store output files. Default is current folder.
authorize_from_browser: bool
    whether to load cookies used by your web browser for authorization.
    This means you can use python to download data by logining in to website 
    via browser (So far the following browsers are supported: Chrome，Firefox, 
    Opera, Edge, Chromium"). It will be very usefull when website doesn't support
    "HTTP Basic Auth". Default is False.
file_names: iterator
    iterator contains names of files. Leaving it None if you want the program to parse
    them from website. file_names can cantain the absolute paths if folder is None.
ncore: int
    Number of cores for parallel processing. If ncore is None then the number returned
    by os.cpu_count() is used. Default is None.
desc: str
    description of data downloading
```

**Example:**

```python
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
```

### 2.5 async_download_datas

Download files simultaneously with asynchronous mode. The website that don't support resuming may lead to download incompletely. You can use `download_datas` instead

``` Python
downloader.async_download_datas(urls, folder=None, authorize_from_browser=False, file_names=None, limit=30, desc='', allow_redirects=False,  retry=0)
```

**Parameters:**

``` 
urls:  iterator
    iterator contains urls
folder: str
    the folder to store output files. Default is current folder.
authorize_from_browser: bool
    whether to load cookies used by your web browser for authorization.
    This means you can use python to download data by logining in to website 
    via browser (So far the following browsers are supported: Chrome，Firefox, 
    Opera, Edge, Chromium"). It will be very usefull when website doesn't support
    "HTTP Basic Auth". Default is False.
file_names: iterator
    iterator contains names of files. Leaving it None if you want the program
    to parse them from website. file_names can cantain the absolute paths if folder is None.
limit: int
    the number of files downloading simultaneously
desc: str
    description of datas downloading
allow_redirects: bool
    Enables or disables HTTP redirects
retry: int
    number of reconnections when status code is 503
```

**Example:**

``` python
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
```

### 2.6 status_ok

Simultaneously detecting whether the given links are accessible. 

``` Python
downloader.status_ok(urls, limit=200, authorize_from_browser=False, timeout=60)
```

**Parameters**

``` 
urls: iterator
    iterator contains urls
limit: int
    the number of urls connecting simultaneously
authorize_from_browser: bool
    whether to load cookies used by your web browser for authorization.
    This means you can use python to download data by logining in to website 
    via browser (So far the following browsers are supported: Chrome，Firefox, 
    Opera, Edge, Chromium"). It will be very usefull when website doesn't support
    "HTTP Basic Auth". Default is False.
timeout: int
    Request to stop waiting for a response after a given number of seconds
```

**Return:**

a list of results (True or False)

**Example:**

``` python
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
```
## 3. parse_url Usage

Provides a very simple way to get URLs from various medias

to import:
```python
from data_downloader import parse_urls
```

### 3.1 from_urls_file

parse urls from a file which only contains urls 

```python
parse_urls.from_urls_file(url_file)
```

**Parameters:**

    url_file: str
        path to file which only contains urls 

**Return:**

a list contains urls


### 3.2 from_sentinel_meta4

parse urls from sentinel `products.meta4` file downloaded from  <https://scihub.copernicus.eu/dhus>

```python
parse_urls.from_sentinel_meta4(url_file)
```

**Parameters:**

    url_file: str
        path to products.meta4

**Return:**

a list contains urls

### 3.3 from_html


parse urls from html website

```python
parse_urls.from_html(url, suffix=None, suffix_depth=0, url_depth=0)
```

**Parameters:**

    url: str
        the website contains datas
    suffix: list, optional
        data format. suffix should be a list contains multipart. 
        if suffix_depth is 0, all '.' will parsed. 
        Examples: 
            when set 'suffix_depth=0':
                suffix of 'xxx8.1_GLOBAL.nc' should be ['.1_GLOBAL', '.nc']
                suffix of 'xxx.tar.gz' should be ['.tar', '.gz']
            when set 'suffix_depth=1':
                suffix of 'xxx8.1_GLOBAL.nc' should be ['.nc']
                suffix of 'xxx.tar.gz' should be ['.gz']
    suffix_depth: integer
        Number of suffixes
    url_depth: integer
        depth of url in website will parsed

**Return:**

a list contains urls

**Example:**

```python
from downloader import parse_urls

url = 'https://cds-espri.ipsl.upmc.fr/espri/pubipsl/iasib_CH4_2014_uk.jsp'
urls = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1)
urls_all = parse_urls.from_html(url, suffix=['.nc'], suffix_depth=1, url_depth=1)
print(len(urls_all)-len(urls))
```

### 3.4 from_EarthExplorer_order

parse urls from orders in earthexplorer.

Reference: [bulk-downloader](https://code.usgs.gov/espa/bulk-downloader)


```python
parse_urls.from_EarthExplorer_order(username=None, passwd=None, email=None,
                                    order=None, url_host=None)
```

**Parameters:**

    username, passwd: str, optional
        your username and passwd to login in EarthExplorer. Chould be
        None when you have save them in .netrc
    email: str, optional
        email address for the user that submitted the order
    order: str or dict
        which order to download. If None, all orders retrieved from 
        EarthExplorer will be used.
    url_host: str
        if host is not USGS ESPA

**Return:**

a dict in format of {orderid: urls}

**Example:**

```python
from pathlib import Path
from data_downloader import downloader, parse_urls
folder_out = Path('D:\\data')
urls_info = parse_urls.from_EarthExplorer_order(
            'your username', 'your passwd')
for odr in urls_info.keys():
    folder = folder_out.joinpath(odr)
    if not folder.exists():
        folder.mkdir()
    urls = urls_info[odr]
    downloader.download_datas(urls, folder)
```