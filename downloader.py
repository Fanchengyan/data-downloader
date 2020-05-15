#!/usr/bin/env python3
import os
import time
import requests
import asyncio
import aiohttp
from tqdm import tqdm
from urllib.parse import urlparse

requests.packages.urllib3.disable_warnings()


def parse_file_name(response):
    '''parse the file_name from the headers of web response or url'''

    if 'Content-disposition' in response.headers:
        file_name = response.headers['Content-disposition'].split('filename=')[
            1].strip('"').strip("'")
    else:
        file_name = os.path.basename(urlparse(response.url).path)
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


def download_data(url, folder=None, file_name=None, Session=None):
    '''Download a single file.

    Parameters:
    -----------
    url: str
        url of web file
    folder: str
        folder to save file 
    file_name: str
        the file name. If None, will parse from web response or url
    Session: requests.Session() object
        Session maintaining connection. Default None
    '''
    # init parameters
    support_resume = False
    local_size = 0
    headers = {'Range': 'bytes=0-4'}
    if not Session:
        Session = requests.Session()

    r = Session.get(url, headers=headers, stream=True, verify=False)
    r.close()

    if not folder:
        folder = os.getcwd()
    if not file_name:
        file_name = parse_file_name(r)

    file_path = os.path.join(folder, file_name)

    # parse the whether the website supports resuming breakpoint
    if r.status_code == 206:
        support_resume = True
        remote_size = int(r.headers['Content-Range'].rsplit('/')[-1])
        # parse local file size
        if os.path.exists(file_path):
            local_size = os.path.getsize(file_path)
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
            if os.path.exists(file_path):
                local_size = os.path.getsize(file_path)
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
        r = Session.get(url, headers=headers, stream=True,
                        timeout=120, verify=False)
    else:
        r = Session.get(url, stream=True, timeout=120, verify=False)

    with open(file_path, "ab") as f:
        time_start = time.time()
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
            if support_resume:
                pbar.update(size_add)
            else:
                print('Downloading {} [{}]'.format(
                    file_name, unit_formater(local_size, 'B')), end='\r')
    if not support_resume:
        speed = local_size / (time.time()-time_start)
        print('Downloaded {} [Speed: {} | Total Size: {}]'.format(
            file_name,
            unit_formater(speed, 'B/s'),
            unit_formater(local_size, 'B')))
    return True


async def _download_data(session, url, file_path):
    # parse whether the url supports support_resume resuming
    headers = {'Range': 'bytes=0-4'}
    async with session.get(url, headers=headers) as r:
        if r.status == 206:
            remote_size = int(r.headers['Content-Range'].rsplit('/')[-1])
            # parse local file size
            if os.path.exists(file_path):
                local_size = os.path.getsize(file_path)
            else:
                local_size = 0
            # init process bar
            if local_size < remote_size:
                pbar = tqdm(initial=local_size, total=remote_size,
                            unit='B', unit_scale=True,
                            desc=f'{os.path.basename(file_path)}')
            else:
                print(f'{file_path} was downloaded entirely. skiping download')
                return True

        elif r.status == 200:
            remote_size = 0
        else:
            return False

    # begin download
    headers['Range'] = f'bytes={local_size}-{remote_size}'

    async with session.get(url, headers=headers, ssl=False) as r:
        with open(file_path, "ab") as f:
            while True:
                chunk = await r.content.read(1024)
                if not chunk:
                    break
                size_add = len(chunk)
                local_size += size_add
                f.write(chunk)
                f.flush()
                # print process condition
                if remote_size > 0:
                    pbar.update(size_add)
                else:
                    print('Downloading {} [{}]'.format(
                        os.path.basename(file_path), local_size), end='\r')
        pbar.close()
        return True


async def creat_tasks(urls, file_paths, limit=30):
    conn = aiohttp.TCPConnector(limit_per_host=limit)
    timeout = aiohttp.ClientTimeout()
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        tasks = [asyncio.ensure_future(_download_data(session, url, file_paths[i]))
                 for i, url in enumerate(urls)]

        # Total process bar
        tasks_iter = asyncio.as_completed(tasks)
        pbar = tqdm(tasks_iter, total=len(urls), desc='>>> Total')
        for coroutine in pbar:
            await coroutine


def download_datas(urls, file_paths, limit=30):
    '''Download multiple files simultaneously.
    Parameters:
    urls:  iterator
        iterator contains urls
    file_paths: iterator
        iterator contains paths of files
    limit: int
        the number of downloading simultaneously

    Examples:
    ---------
    import downloader

    urls=['http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20141211/20141117_20141211.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150221/20141024_20150221.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141024_20150128/20141024_20150128.geo.unw.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141211_20150128/20141211_20150128.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150317/20141117_20150317.geo.cc.tif',
    'http://gws-access.ceda.ac.uk/public/nceo_geohazards/LiCSAR_products/106/106D_05049_131313/interferograms/20141117_20150221/20141117_20150221.geo.cc.tif'] 

    path = [i.rsplit('/',1)[-1] for i in urls]

    downloader.download_datas(urls,path,3)
    '''
    loop = asyncio.get_event_loop()
    loop.run_until_complete(creat_tasks(urls, file_paths, limit))
