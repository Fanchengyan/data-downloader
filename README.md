# data-downloader

[toc]

## 1. Installation

It is recommended to use the latest version of pip when using pip-downloader.

``` BASH
pip install data_downloader
```

## 2. Usage

All download functions are in `data_downloader.downloader`. So import `downloader` at the beginning.

``` Python
from data_downloader import downloader
```

### 2.1 Netrc

if the website need logging,you can add a record to a `.netrc` file in your home

To view existing hosts in `.netrc` file:

``` Python
netrc = downloader.Netrc()
print(netrc.hosts)
```

To add a record

``` Python
netrc.add(host, login, password,account=None)
```


for NASA data user:
``` Python

netrc.add('urs.earthdata.nasa.gov','your_username','your_password')
```

**Example:**

``` Python
In [2]: netrc = downloader.Netrc()                                                                                                                    

In [3]: netrc.hosts                                                                                                                                   
Out[3]: {}

In [4]: netrc.add('urs.earthdata.nasa.gov','username','passwd')                                                                            

In [5]: netrc.hosts                                                                                                                                   
Out[5]: {'urs.earthdata.nasa.gov': ('username', None, 'passwd')}

```


### 2.1 download_data

Download a single file.

``` Python
downloader.download_data(url, folder=None, file_name=None, session=None)
```

**Parameters:**

```
url: str
    url of web file
folder: str
    the folder to store output files. Default current folder. 
file_name: str
    the file name. If None, will parse from web response or url
session: requests.Session() object
    session maintaining connection. Default None
```

**Example:**

``` Python
In [6]: url = 'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_201
   ...: 41211.geo.unw.tif'
   ...:  
   ...: folder = 'D:\\data'
   ...: downloader.download_data(url,folder)

20141117_20141211.geo.unw.tif:   2%|▌                         | 455k/22.1M [00:52<42:59, 8.38kB/s]
```

### 2.2 download_datas

download datas from a list which containing urls 

``` Python
downloader.download_datas(urls, folder=None, file_names=None):
```

**Patameters:**

``` 
urls:  iterator
    iterator contains urls
folder: str 
    the folder to store output files. Default current folder.
file_names: iterator
    iterator contains names of files. Leaving it None if you want the program 
    to parse them from website
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

20141117_20141211.geo.unw.tif:   6%|█▍                     | 1.37M/22.1M [03:09<2:16:31, 2.53kB/s]
```

### 2.3 async_download_datas

Download files simultaneously.

``` Python
downloader.async_download_datas(urls, folder=None, file_names=None, limit=30)
```

**Parameters:**

``` 
urls:  iterator
    iterator contains urls
folder: str 
    the folder to store output files. Default current folder.
file_names: iterator
    iterator contains names of files. Leaving it None if you want the program 
    to parse them from website 
limit: int
    the number of files downloading simultaneously
```

**Examples:**

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
   ...: downloader.async_download_datas(urls,folder,limit=3) 

>>> Total:   0%|                                                           | 0/7 [00:00<?, ?it/s]
20141024_20150221.geo.unw.tif:   1%|▏                        | 136k/21.2M [00:39<45:24, 7.75kB/s]
20141024_20150128.geo.cc.tif:   2%|▌                         | 119k/5.42M [01:02<6:47:45, 217B/s]
20141211_20150128.geo.cc.tif:   3%|▊                         | 159k/5.44M [00:36<13:02, 6.75kB/s]
20141117_20141211.geo.unw.tif:   0%|                                 | 0.00/22.1M [00:00<?, ?B/s]
20141117_20150317.geo.cc.tif:   0%|                                  | 0.00/5.44M [00:00<?, ?B/s]
20141117_20150221.geo.cc.tif:   0%|                                  | 0.00/5.47M [00:00<?, ?B/s]
20141024_20150128.geo.unw.tif:   0%|                                 | 0.00/23.4M [00:00<?, ?B/s]
```

### 2.4 status_ok

Simultaneously detecting whether the given links are accessable. 

``` Python
downloader.status_ok(urls, limit=200)
```

**Parameters**

``` 
urls: iterator
    iterator contains urls
limit: int
    the number of urls connecting simultaneously
```

**Return:**

a list of results (True or False)

**Example:**

``` python
In [1]:     from data_downloader import downloader 
   ...:     import numpy as np 
   ...:  
   ...:     urls = np.array(['https://www.baidu.com', 
   ...:     'https://www.bai.com/wrongurl', 
   ...:     'https://cn.bing.com/', 
   ...:     'https://bing.com/wrongurl', 
   ...:     'https://bing.com/'] ) 
   ...:  
   ...:     status_ok = downloader.status_ok(urls) 
   ...:     urls_accessable = urls[status_ok] 
   ...:     print(urls_accessable) 

['https://www.baidu.com' 'https://cn.bing.com/' 'https://bing.com/']
```
