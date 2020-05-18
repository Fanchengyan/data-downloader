#!/usr/bin/env python3
import os
import time
import requests
import asyncio
import aiohttp
from tqdm import tqdm
from netrc import netrc
from urllib.parse import urlparse

requests.packages.urllib3.disable_warnings()


class Netrc:
    '''add or clean records in .netrc file'''

    def __init__(self, file=None):
        if file is None:
            file = os.path.join(os.path.expanduser("~"), ".netrc")
        self.file = file
        self._update_info()

    def _update_info(self):
        self.netrc = netrc(self.file)
        self.hosts = self.netrc.hosts

    def add(self, host, login, password, account=None):
        '''add a record'''
        if host in self.hosts:
            pass
        else:
            rep = f"machine {host}\n\tlogin {login}\n"
            if account:
                rep += f"\taccount {account}\n"
            rep += f"\tpassword {password}\n"

            with open(self.file, 'a') as f:
                f.write(rep)
        self._update_info()

    def clean(self):
        '''remove all records'''
        with open(self.file, 'w') as f:
            f.write('')
        self._update_info()


def parse_file_name(response):
    '''parse the file_name from the headers of web response or url'''

    if 'Content-disposition' in response.headers:
        file_name = response.headers['Content-disposition'].split('filename=')[
            1].strip('"').strip("'")
    else:
        file_name = os.path.basename(urlparse(str(response.url)).path)
    return file_name


def unit_formater(size, suffix):
    if 1024 <= size < 1024 ** 2:
        return f'{size/1024:.3f}k{suffix}'
    elif 1024**2 <= size < 1024 ** 3:
        return f'{size/1024**2:.3f}M{suffix}'
    elif 1024**3 <= size <= 1024 ** 4:
        return f'{size/1024**3:.3f}G{suffix}'
    else:
        return f'{size}{suffix}'


def download_data(url, folder=None, file_name=None, session=None):
    '''Download a single file.

    Parameters:
    -----------
    url: str
        url of web file
    folder: str
        the folder to store output files. Default current folder. 
    file_name: str
        the file name. If None, will parse from web response or url
    session: requests.Session() object
        session maintaining connection. Default None
    '''
    # init parameters
    support_resume = False
    headers = {'Range': 'bytes=0-4'}
    if not session:
        session = requests.Session()

    r = session.get(url, headers=headers, stream=True, verify=False)
    r.close()

    if not folder:
        folder = os.getcwd()
    if not file_name:
        file_name = parse_file_name(r)

    file_path = os.path.join(folder, file_name)

    local_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # parse the whether the website supports resuming breakpoint
    if r.status_code == 206:
        support_resume = True
        remote_size = int(r.headers['Content-Range'].rsplit('/')[-1])

        # init process bar
        if local_size < remote_size:
            pbar = tqdm(initial=local_size, total=remote_size,
                        unit='B', unit_scale=True,
                        desc=file_name)
        else:
            print(f'{file_name} was downloaded entirely. skiping download')
            return True

    elif r.status_code == 200:
        # know the total size, then delete the file that wasn't downloaded entirely and redownload it.
        if 'Content-length' in r.headers:
            remote_size = int(r.headers['Content-length'])

            if 0 < local_size < remote_size:
                print(f"Detect {file_name} wasn't downloaded entirely")
                print(
                    'The website not supports resuming breakpoint. Prepare to remove and redownload')
                os.remove(file_path)
            elif local_size == remote_size:
                print(f'{file_name} was downloaded entirely. skiping download')
                return True
        # don't know the total size, warning user if detect the file was downloaded.
        else:
            if os.path.exists(file_path):
                print(
                    f">>> Warning: Detect the {file_name} was downloaded, but can't parse the it's size from website")
                print(
                    f"    If you know it wasn't downloaded entirely, delete it and redownload it again. skiping download...")
                return True

    else:
        return False

    # begin downloading
    if support_resume:
        headers['Range'] = f'bytes={local_size}-{remote_size}'
        r = session.get(url, headers=headers, stream=True,
                        timeout=120, verify=False)
    else:
        r = session.get(url, stream=True, timeout=120, verify=False)

    with open(file_path, "ab") as f:
        time_start_realtime = time_start = time.time()
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
            if support_resume:
                pbar.update(size_add)
            else:
                time_end_realtime = time.time()
                speed_realtime = size_add / \
                    (time_end_realtime - time_start_realtime)
                print('Downloading {} [Speed: {} | Size: {}]'.format(
                    file_name,
                    unit_formater(speed_realtime, 'B/s'),
                    unit_formater(local_size, 'B')), end='\r')
                time_start_realtime = time_end_realtime
    if not support_resume:
        speed = local_size / (time.time() - time_start)
        print('Finish downloading {} [Speed: {} | Total Size: {}]'.format(
            file_name,
            unit_formater(speed, 'B/s'),
            unit_formater(local_size, 'B')))
    return True


def download_datas(urls, folder=None, file_names=None):
    '''download datas from a list like object which containing urls. 
    This function will download files one by one.

    Patameters:
    -----------
    urls:  iterator
        iterator contains urls
    folder: str 
        the folder to store output files. Default current folder.
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program 
        to parse them from website

    Examples:
    ---------
    ```python
    from data_downloader import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif'] 

    folder = 'D:\\data'
    downloader.download_datas(urls,folder)
    ```
    '''
    session = requests.Session()
    for i, url in enumerate(urls):
        if file_names:
            download_data(url, folder, file_names[i], session)
        else:
            download_data(url, folder, session=session)


async def _download_data(session, url, folder=None, file_name=None):
    # parse whether the url supports support_resume resuming
    headers = {'Range': 'bytes=0-4'}
    support_resume = False

    if not folder:
        folder = os.getcwd()

    async with session.get(url, headers=headers, ssl=False) as r:
        if not file_name:
            file_name = parse_file_name(r)
        file_path = os.path.join(folder, file_name)
        local_size = os.path.getsize(
            file_path) if os.path.exists(file_path) else 0

        # parse the whether the website supports resuming breakpoint
        if r.status == 206:
            support_resume = True
            remote_size = int(r.headers['Content-Range'].rsplit('/')[-1])

            # init process bar
            if local_size < remote_size:
                pbar = tqdm(initial=local_size, total=remote_size,
                            unit='B', unit_scale=True,
                            desc=file_name)
            else:
                print(f'{file_name} was downloaded entirely. skiping download')
                return True

        elif r.status == 200:
            # know the total size, then delete the file that wasn't downloaded entirely and redownload it.
            if 'Content-length' in r.headers:
                remote_size = int(r.headers['Content-length'])

                if 0 < local_size < remote_size:
                    print(f"Detect {file_name} wasn't downloaded entirely")
                    print(
                        'The website not supports resuming breakpoint. Prepare to remove and redownload')
                    os.remove(file_path)
                elif local_size == remote_size:
                    print(f'{file_name} was downloaded entirely. skiping download')
                    return True
            # don't know the total size, warning user if detect the file was downloaded.
            else:
                if os.path.exists(file_path):
                    print(
                        f">>> Warning: Detect the {file_name} was downloaded, but can't parse the it's size from website")
                    print(
                        f"    If you know it wasn't downloaded entirely, delete it and redownload it again. skiping download...")
                    return True

        else:
            return False

    # begin download
    headers['Range'] = f'bytes={local_size}-{remote_size}'

    async with session.get(url, headers=headers, ssl=False) as r:
        with open(file_path, "ab") as f:
            time_start_realtime = time_start = time.time()

            while True:
                chunk = await r.content.read(1024)
                if not chunk:
                    break
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
                if support_resume:
                    pbar.update(size_add)
                else:
                    time_end_realtime = time.time()
                    speed_realtime = size_add / \
                        (time_end_realtime - time_start_realtime)
                    print('Downloading {} [Speed: {} | Size: {}]'.format(
                        file_name,
                        unit_formater(speed_realtime, 'B/s'),
                        unit_formater(local_size, 'B')), end='\r')
                    time_start_realtime = time_end_realtime
            if not support_resume:
                speed = local_size / (time.time()-time_start)
                print('Finish downloading {} [Speed: {} | Total Size: {}]'.format(
                    file_name,
                    unit_formater(speed, 'B/s'),
                    unit_formater(local_size, 'B')))
            return True


async def creat_tasks(urls, folder, file_names, limit, desc):
    conn = aiohttp.TCPConnector(limit_per_host=limit)
    timeout = aiohttp.ClientTimeout()
    async with aiohttp.ClientSession(connector=conn, timeout=timeout, trust_env=True) as session:
        if file_names:
            tasks = [asyncio.ensure_future(_download_data(session, url, file_names[i]))
                     for i, url in enumerate(urls)]
        else:
            tasks = [asyncio.ensure_future(_download_data(session, url))
                     for url in urls]

        # Total process bar
        tasks_iter = asyncio.as_completed(tasks)
        desc = '>>> Total | ' + desc.title()
        pbar = tqdm(tasks_iter, total=len(urls), desc=desc)
        for coroutine in pbar:
            await coroutine


def async_download_datas(urls, folder=None, file_names=None, limit=30, desc=''):
    '''Download multiple files simultaneously.

    Parameters:
    -----------
    urls:  iterator
        iterator contains urls
    folder: str 
        the folder to store output files. Default current folder.
    file_names: iterator
        iterator contains names of files. Leaving it None if you want the program 
        to parse them from website 
    limit: int
        the number of files downloading simultaneously
    desc: str
        description of datas downloading

    Example:
    ---------

    from data_downloader import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif'] 

    folder = 'D:\\data'
    downloader.async_download_datas(urls,folder,limit=3,desc='interferograms')
    '''
    loop = asyncio.get_event_loop()
    loop.run_until_complete(creat_tasks(urls, folder, file_names, limit, desc))
    # Zero-sleep to allow underlying connections to close
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()


async def _is_response_staus_ok(session, url, timeout):
    try:
        async with session.get(url, timeout=timeout, ssl=False) as r:

            if r.reason == 'OK':
                return True
            else:
                return False
    except:
        return False


async def creat_tasks_status_ok(urls, limit, timeout):
    conn = aiohttp.TCPConnector(limit=limit)
    timeout = aiohttp.ClientTimeout()  # remove timeout
    async with aiohttp.ClientSession(connector=conn, trust_env=True) as session:
        tasks = [asyncio.ensure_future(_is_response_staus_ok(session, url, timeout))
                 for url in urls]
        status_ok = await asyncio.gather(*tasks)
        return status_ok


def status_ok(urls, limit=200, timeout=60):
    '''Simultaneously detecting whether the given links are accessable. 

    Parameters
    ----------
    urls: iterator
        iterator contains urls
    limit: int
        the number of urls connecting simultaneously
    timeout: int
        Request to stop waiting for a response after a given number of seconds

    Return:
    ------
    a list of results (True or False)

    Example:
    -------
    ```python
    from data_downloader import downloader
    import numpy as np

    urls = np.array(['https://www.baidu.com',
    'https://www.bai.com/wrongurl',
    'https://cn.bing.com/',
    'https://bing.com/wrongurl',
    'https://bing.com/'] )

    status_ok = downloader.status_ok(urls)
    urls_accessable = urls[status_ok]
    print(urls_accessable)
    ```
    '''
    loop = asyncio.get_event_loop()
    status_ok = loop.run_until_complete(
        creat_tasks_status_ok(urls, limit, timeout))
    # Zero-sleep to allow underlying connections to close
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    return status_ok
