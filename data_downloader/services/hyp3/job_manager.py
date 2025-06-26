from __future__ import annotations

import warnings
import zipfile
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Callable

import hyp3_sdk as sdk
import pandas as pd
from tqdm import tqdm

from data_downloader import downloader
from data_downloader.logging import setup_logger
from data_downloader.utils import Pairs

from .constants import JOB_TYPE

if TYPE_CHECKING:
    from os import PathLike

    from .jobs import Jobs

logger = setup_logger(__name__)


class HyP3Service:
    """Class to manage HyP3 user information and jobs"""

    _my_info: dict
    _jobs: Jobs

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        prompt: bool = False,
        include_expired=False,
    ):
        """Initialize the HyP3Service class

        Parameters
        ----------
        username, password : str, optional
            Username and password for HyP3
        prompt : bool, optional
            Prompt for the username and password in the terminal, by default False.
        include_expired : bool, optional
            Include expired jobs, by default False
        """
        self.include_expired = include_expired
        self.login(username, password, prompt)
        self.flush()

    def __repr__(self) -> str:
        return (
            "HyP3Service("
            f"\n    user_id={self.my_info['user_id']}, "
            f"\n    remaining_credits={self.my_info['remaining_credits']}, "
            f"\n    succeeded={len(self.jobs.succeeded)},"
            f"\n    failed={len(self.jobs.failed)},"
            f"\n    pending={len(self.jobs.pending)},"
            f"\n    running={len(self.jobs.running)}"
            "\n)"
        )

    def __str__(self) -> str:
        return f"Hyp3Service({self.my_info['user_id']}, remaining_credits={self.my_info['remaining_credits']})"

    def flush_jobs(self) -> None:
        """Flush the jobs"""
        self._jobs = self._parse_jobs()

    def flush_info(self) -> None:
        """Flush the user's information"""
        self._my_info = self.hyp3.my_info()

    def flush(self) -> None:
        """Flush the jobs and the user's information"""
        self.flush_jobs()
        self.flush_info()

    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        prompt: bool = False,
    ) -> None:
        """Login to HyP3. If neither username/password nor prompt is provided,
        it will attempts to use credentials from a ``.netrc`` file. If prompt is True,
        the username and password will be prompted in the terminal. Otherwise, the
        username and password must be provided.

        .. note::

            This method will be called automatically when the class is initialized.
            However, you can change the user by calling this method again with the new
            username and password.

        Parameters
        ----------
        username, password : str, optional
            Username and password for HyP3
        prompt : bool, optional
            Prompt for the username and password in the terminal, by default False.
        """
        self.hyp3 = sdk.HyP3(username=username, password=password, prompt=prompt)
        self.flush()

    @property
    def my_info(self) -> dict:
        """user's information"""
        return self._my_info

    @property
    def jobs(self) -> Jobs:
        """all jobs (not expired by default, set ``include_expired=True`` to
        include expired jobs)"""
        return self._jobs

    def _parse_jobs(self) -> Jobs:
        """Parse all jobs"""
        batch = self.hyp3.find_jobs().filter_jobs(include_expired=self.include_expired)
        return Jobs(batch.jobs)


class HyP3JobsDownloader:
    """Class to download HyP3 jobs"""

    def __init__(self, service: HyP3Service, job_type: str) -> None:
        """Initialize the HyP3JobsDownloader.

        Parameters
        ----------
        service : HyP3Service
            The HyP3 service
        job_type : str
            The job type to download. e.g. INSAR_GAMMA, INSAR_ISCE_BURST
        """
        self.service = service
        self.job_type = job_type

    @property
    def jobs_on_service(self) -> Jobs:
        """Get the jobs on the service"""
        self.service.flush()
        jobs_on_service = self.service.jobs.sel(job_type=self.job_type)
        return jobs_on_service

    def _scan_interferograms(self, home_dir: PathLike) -> list[str]:
        """Scan the local directory for the interferograms"""
        home_dir = Path(home_dir)
        return [i.stem for i in home_dir.glob("*") if i.is_dir()]

    def _download_jobs(
        self,
        output_dir: PathLike,
        name: str | None = None,
        request_time: datetime | str | slice | None = None,
        unzip: bool = True,
        remove_zip: bool = True,
        overwrite: bool = False,
    ) -> None:
        """Download the jobs from HyP3"""
        jobs = self.jobs_on_service.sel(name=name, request_time=request_time).succeeded
        for file_name, url in tqdm(
            zip(jobs.file_names, jobs.file_urls),
            desc="Downloading jobs",
            total=len(jobs),
        ):
            local_ifgs = self._scan_interferograms(output_dir)
            if Path(file_name).stem in local_ifgs and not overwrite:
                tqdm.write(f"Interferogram {file_name} already exists. Skipping.")
                continue
            try:
                downloader.download_data(url, output_dir, file_name)
                if unzip:
                    unzip_file(output_dir, file_name, remove_zip, overwrite)
            except Exception as e:
                tqdm.write(f"Failed to download file {file_name}. {e}")

    def download_jobs(
        self,
        output_dir: PathLike,
        name: str | None = None,
        request_time: datetime | str | slice | None = None,
        unzip: bool = True,
        remove_zip: bool = True,
        overwrite: bool = False,
        wait_running=True,
        wait_minutes=60,
        retry=3,
    ) -> None:
        """Download jobs from HyP3.

        Parameters
        ----------
        output_dir : PathLike
            Output directory to save the files
        name : str, optional
            Name of submitted jobs to filter by, by default None
        request_time : datetime | str | slice, optional
            Request time of submitted jobs to filter by. Can be a datetime object,
            a string, or a slice object. If a slice object is used, the start
            must be a string or a datetime object, and the stop can be None, a
            string. If a string is used, it must be in the format that can be
            converted to a datetime
        unzip : bool, optional
            Whether to unzip the files, by default True
        remove_zip : bool, optional
            Whether to remove the zip files after unzipping, by default True
        overwrite : bool, optional
            Whether to overwrite the existing files when unzipping. If False, The
            interferogram folders that are already unzipped will not be downloaded
            again, by default False.
        wait_running : bool, optional
            Whether to wait for the jobs that are still running, by default True
        wait_minutes : int, optional
            Time to wait for the jobs to finish, by default 60 (1 hour)
        retry : int, optional
            Number of times to retry the download, by default 3
        """
        count = 0
        while True:
            self._download_jobs(
                output_dir, name, request_time, unzip, remove_zip, overwrite
            )
            count += 1
            if count >= retry:
                break
            # check if there are still running jobs
            jobs = self.jobs_on_service.sel(name=name, request_time=request_time)
            if len(jobs.running) == 0:
                break
            if not wait_running:
                logger.warning(
                    "Some jobs are still running. You may need to download them later."
                )
                break
            wait_minutes = int(wait_minutes)
            tqdm.write(
                "Downloading jobs finished. But some jobs are still running."
                f"\nA new download will be attempted in {wait_minutes} minutes."
                "\nYou can stop the process by pressing Ctrl+C."
            )
            sleep(wait_minutes * 60)


class HyP3Jobs(HyP3JobsDownloader):
    """Abstract class to manage HyP3 jobs"""

    _job_type: str
    """The job type. e.g. INSAR_GAMMA, INSAR_ISCE_BURST"""
    date_idx: int
    """The index of the date in the granule name"""
    _submit_func: Callable
    """The function to submit the job"""

    _job_parameters: dict = {}
    """Job parameters"""
    _pairs_succeed: list = []
    """Pairs that succeeded in the job submission"""
    _pairs_failed: list = []
    """Pairs that failed in the job submission"""

    def __init__(
        self,
        service: HyP3Service,
        granules: pd.Series = pd.Series([]),
        job_parameters: dict = {},
    ) -> None:
        """Initialize the InSARJob class

        Parameters
        ----------
        service : HyP3Service
            HyP3Service instance to submit the job and check the submitted jobs.
        granules : pd.Series, optional
            A pandas Series containing granule information, where the index represents the granule date and the values are the granule names. If not provided, only job downloading from HyP3 is supported; job submission is unavailable.
        job_parameters : dict, optional
            Arguments to be passed to the job, by default {}.

            .. hint::
                - You can still modify job parameters after initialization by 
                resetting the ``job_parameters`` attribute.
                - You can use the ``show_parameters`` method to view all available submission parameters.
        """
        self.granules = granules
        self.service = service
        self.job_parameters = job_parameters

        # initialize the batch
        self.batch = sdk.Batch()
        super().__init__(service, self._job_type)

    @property
    def jobs_on_service(self) -> Jobs:
        """Get the jobs on the service"""
        self.service.flush()
        jobs_on_service = self.service.jobs.sel(job_type=self.job_type)
        return jobs_on_service

    @property
    def job_parameters(self) -> dict:
        """Job parameters"""
        return self._job_parameters

    @job_parameters.setter
    def job_parameters(self, job_parameters: dict):
        """Set the job parameters"""
        if not isinstance(job_parameters, dict):
            raise ValueError("job_parameters must be a dictionary.")
        self._job_parameters = job_parameters

    @property
    def pairs_succeed(self) -> Pairs:
        """Pairs that succeeded in the job submission"""
        return Pairs(self._pairs_succeed)

    @property
    def pairs_failed(self) -> Pairs:
        """Pairs that failed in the job submission"""
        return Pairs(self._pairs_failed)

    def jobs_to_pairs(self, jobs: Jobs) -> Pairs:
        """Convert jobs to pairs"""
        pairs = []
        for job in jobs:
            if job.job_type != self.job_type:
                warnings.warn(
                    f"Job type {job.job_type} is not {self.job_type}. Skipping."
                )
                continue
            if len(job.job_parameters["granules"]) != 2:
                warnings.warn(
                    f"Invalid number of granules for job {job.job_id}. Skipping."
                )
                continue
            pair = (
                granule_to_date(job.job_parameters["granules"][0], self.date_idx),
                granule_to_date(job.job_parameters["granules"][1], self.date_idx),
            )
            pairs.append(pair)
        return Pairs(pairs)

    def _get_remain_pairs(self, pairs: Pairs, skip_existing: bool = True):
        """Get the remaining pairs to submit"""
        if not skip_existing:
            return pairs

        pairs_exclude = self.jobs_to_pairs(self.jobs_on_service)
        if pairs_exclude is None:
            return pairs
        warnings.warn(
            f"Skipping {len(pairs_exclude)} existing pairs already submitted."
        )
        pairs_remain = pairs - pairs_exclude
        return pairs_remain

    def show_parameters(self) -> None:
        """Show the all available parameters for submitting the job"""
        print(self._submit_func.__doc__)

    def _submit_job(
        self,
        reference,
        secondary,
    ) -> None:
        """Submit the job to HyP3"""
        self.batch += self._submit_func(reference, secondary, **self.job_parameters)

    def submit_jobs(self, pairs: Pairs, skip_existing: bool = True):
        """Submit the job to HyP3

        Parameters
        ----------
        pairs : Pairs
            Pairs to be submitted to HyP3
        skip_existing : bool, optional
            Whether to skip the existing pairs that have succeeded or are running,
            by default True
        """
        pairs_remain = self._get_remain_pairs(pairs, skip_existing)
        for pair in tqdm(pairs_remain, desc="Submitting jobs"):
            ref, sec = str(pair).split("_")
            reference, secondary = self.granules[ref], self.granules[sec]

            if reference is None or secondary is None:
                tqdm.write(f"Granule not found for pair {pair}. Skipping.")
                self._pairs_failed.append(pair)
                continue

            reference = _ensure_granules(reference, pair)
            secondary = _ensure_granules(secondary, pair)
            try:
                self._submit_job(reference, secondary)
                self._pairs_succeed.append(pair)
            except Exception as e:
                params = {"granule1": reference, "granule2": secondary}
                params.update(self.job_parameters)
                msg = (
                    f"Failed to submit job for pair {pair}. Job parameters: {params}."
                    f"Error: {e}"
                )
                tqdm.write(msg)
                self._pairs_failed.append(pair)


class HyP3JobsGAMMA(HyP3Jobs):
    """Class to manage ``INSAR_GAMMA`` jobs.

    This class provides a pythonic interface to submit and download
    ``INSAR_GAMMA`` jobs from HyP3.
    """

    _job_type = JOB_TYPE.INSAR_GAMMA
    date_idx = 5
    _submit_func = sdk.HyP3.submit_insar_job


class HyP3JobsBurst(HyP3Jobs):
    """Class to manage ``INSAR_ISCE_BURST`` jobs.

    This class provides a pythonic interface to submit and download
    ``INSAR_ISCE_BURST`` jobs from HyP3.
    """

    _job_type = JOB_TYPE.INSAR_ISCE_BURST
    date_idx = 3
    _submit_func = sdk.HyP3.submit_insar_isce_burst_job


def granule_to_date(granule: str, idx_date):
    """Convert granule to date"""
    return pd.to_datetime(granule.split("_")[idx_date])


def unzip_file(output_dir, file_name, remove_zip=True, overwrite=False):
    """Unzip the file"""
    zip_file = Path(output_dir) / file_name
    unzip_dir = Path(output_dir) / Path(file_name).stem
    try:
        if not overwrite and unzip_dir.exists():
            logger.warning(f"Directory {unzip_dir} already exists. Skipping.")
            return None
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(output_dir)
        if remove_zip:
            zip_file.unlink()
    except Exception as e:
        msg = f"Error in unzipping {zip_file}\n{e}"
        logger.warning(msg)
        raise Exception(msg)


def _ensure_granules(granule: pd.Series | str, pair: Pairs) -> str:
    """Remove the duplicate pairs"""
    if isinstance(granule, pd.Series):
        tqdm.write(
            f"Multiple granules found for pair {pair}: {[i for i in granule]}."
            "First one will be used."
        )
        granule = granule[0]
    return str(granule)
