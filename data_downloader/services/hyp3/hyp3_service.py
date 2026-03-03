"""HyP3 service module.

This module provides the HyP3Service class for managing HyP3 user
authentication, job querying, and downloading results.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

import hyp3_sdk as sdk
from tqdm import tqdm

from data_downloader import downloader
from data_downloader.logging import setup_logger, tqdm_handler

from .jobs import Jobs

if TYPE_CHECKING:
    from datetime import datetime
    from os import PathLike

    from data_downloader.enums.hyp3 import JobType


logger = setup_logger(__name__, handler=[tqdm_handler])


class HyP3Service:
    """Class to manage HyP3 user information, job querying, and downloading."""

    _my_info: dict
    _jobs: Jobs

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        prompt: bool = False,
        include_expired: bool = False,
    ) -> None:
        """Initialize the HyP3Service class.

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
        """Return a detailed string representation of the HyP3Service."""
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
        """Return a concise string representation of the HyP3Service."""
        return (
            f"Hyp3Service({self.my_info['user_id']}, "
            f"remaining_credits={self.my_info['remaining_credits']})"
        )

    def flush_jobs(self) -> None:
        """Flush the jobs."""
        self._jobs = self._parse_jobs()

    def flush_info(self) -> None:
        """Flush the user's information."""
        self._my_info = self.hyp3.my_info()

    def flush(self) -> None:
        """Flush the jobs and the user's information."""
        self.flush_jobs()
        self.flush_info()

    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        prompt: bool = False,
    ) -> None:
        """Login to HyP3.

        If neither username/password nor prompt is provided, it will attempt
        to use credentials from a ``.netrc`` file. If prompt is True, the
        username and password will be prompted in the terminal. Otherwise,
        the username and password must be provided.

        .. note::

            This method will be called automatically when the class is
            initialized. However, you can change the user by calling this
            method again with the new username and password.

        Parameters
        ----------
        username, password : str, optional
            Username and password for HyP3
        prompt : bool, optional
            Prompt for the username and password in the terminal,
            by default False.

        """
        self.hyp3 = sdk.HyP3(username=username, password=password, prompt=prompt)
        self.flush()

    @property
    def my_info(self) -> dict:
        """User's information."""
        return self._my_info

    @property
    def jobs(self) -> Jobs:
        """All jobs.

        Not expired by default, set ``include_expired=True`` to
        include expired jobs.
        """
        return self._jobs

    def _parse_jobs(self) -> Jobs:
        """Parse all jobs."""
        batch = self.hyp3.find_jobs().filter_jobs(include_expired=self.include_expired)
        return Jobs(batch.jobs)

    # ---- Download methods (merged from HyP3JobsDownloader) ----

    def _scan_interferograms(self, home_dir: PathLike) -> list[str]:
        """Scan the local directory for the interferograms."""
        home_dir = Path(home_dir)
        return [i.stem for i in home_dir.glob("*") if i.is_dir()]

    def _download_jobs(
        self,
        output_dir: PathLike,
        job_type: JobType | None = None,
        name: str | None = None,
        request_time: datetime | str | slice | None = None,
        unzip: bool = True,
        remove_zip: bool = True,
        overwrite: bool = False,
    ) -> None:
        """Download the jobs from HyP3."""
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created directory %s", output_dir)
        logger.info("Downloading jobs from HyP3 service to %s", output_dir)

        local_ifgs = self._scan_interferograms(output_dir)
        logger.info("Found %s interferograms in %s", len(local_ifgs), output_dir)

        self.flush()
        jobs = self.jobs.sel(
            job_type=job_type, name=name, request_time=request_time
        ).succeeded
        logger.info("Found %s succeeded jobs on HyP3 service", len(jobs))

        for file_name, url in tqdm(
            zip(jobs.file_names, jobs.file_urls),
            desc="Downloading jobs",
            total=len(jobs),
        ):
            if Path(file_name).stem in local_ifgs and not overwrite:
                msg = f"Interferogram {file_name} already exists. Skipped."
                logger.info(msg)
                continue
            try:
                downloader.download_file(url, output_dir, file_name)
                if unzip:
                    unzip_file(output_dir, file_name, remove_zip, overwrite)
            except Exception:
                msg = f"Failed to download file {file_name}"
                logger.exception(msg)

    def download_jobs(
        self,
        output_dir: PathLike,
        *,
        job_type: JobType | None = None,
        name: str | None = None,
        request_time: datetime | str | slice | None = None,
        unzip: bool = True,
        remove_zip: bool = True,
        overwrite: bool = False,
        wait_until_finished: bool = True,
        wait_minutes: int = 60,
        retry: int = 30,
    ) -> None:
        """Download jobs from HyP3.

        Parameters
        ----------
        output_dir : PathLike
            Output directory to save the files
        job_type : JobType | None
            The job type to download. e.g. INSAR_GAMMA, INSAR_ISCE_BURST
        name : str, optional
            Name of submitted jobs to filter by, by default None
        request_time : datetime | str | slice, optional
            Request time of submitted jobs to filter by. Can be a datetime, a string,
            or a slice object. If a slice object is used, the start must be a string
            or a datetime, and the stop can be None, a string. If a string is used,
            it must be in the format that can be converted to a datetime.
        unzip : bool, optional
            Whether to unzip the files, by default True
        remove_zip : bool, optional
            Whether to remove the zip files after unzipping, by default True
        overwrite : bool, optional
            Whether to overwrite the existing files when unzipping. If False, The
            interferogram folders that are already unzipped will not be downloaded
            again, by default False.
        wait_until_finished : bool, optional
            Whether to wait for the jobs that are still running or pending to finish,
            by default True.

            .. note::

                If the jobs are still running, the download will be retried for
                ``retry`` times. The download will be retried every ``wait_minutes``
                minutes. The download will be retried until the jobs are finished.

        wait_minutes : int, optional
            Minutes to wait for the jobs still running or pending to finish, by
            default 60 (1 hour)
        retry : int, optional
            Number of times to retry the download if the jobs are still running or
            pending, by default 10

        """
        wait_minutes = int(wait_minutes)
        count = 0
        while True:
            self._download_jobs(
                output_dir, job_type, name, request_time, unzip, remove_zip, overwrite
            )
            count += 1
            if count >= retry:
                msg = (
                    "Downloading stopped with some jobs still running or pending"
                    f" due to {count}th retries exceeded (retry={retry})."
                )
                logger.warning(msg)
                break
            # check if there are still running jobs
            self.flush()
            jobs = self.jobs.sel(
                job_type=job_type, name=name, request_time=request_time
            )
            if len(jobs.running) == 0 and len(jobs.pending) == 0:
                msg = (
                    "All jobs are downloaded without pending or running jobs. "
                    "Downloading finished."
                )
                logger.info(msg)
                break
            if not wait_until_finished:
                msg = (
                    "Downloading stopped with some jobs still running or pending"
                    " due to 'wait_until_finished' is set to False."
                    " You need to re-download them later if all jobs are required to"
                    " be downloaded."
                )
                logger.warning(msg)
                break
            msg = (
                f"A {count}th retry will be attempted in {wait_minutes} minutes"
                f" due to there are still {len(jobs.running)} running and"
                f" {len(jobs.pending)} pending jobs."
            )
            logger.warning(msg)
            sleep(wait_minutes * 60)


def unzip_file(
    output_dir: PathLike,
    file_name: str,
    remove_zip: bool = True,
    overwrite: bool = False,
) -> None:
    """Unzip the file."""
    zip_file = Path(output_dir) / file_name
    unzip_dir = Path(output_dir) / Path(file_name).stem
    try:
        if not overwrite and unzip_dir.exists():
            logger.warning("Directory %s already exists. Skipping.", unzip_dir)
            return
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(output_dir)
        if remove_zip:
            zip_file.unlink()
    except Exception as e:
        msg = f"Error in unzipping {zip_file}"
        logger.exception(msg)
        raise RuntimeError(msg) from e
