"""HyP3 job submission module.

This module provides abstract and concrete classes for submitting
InSAR jobs to the HyP3 service.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

import hyp3_sdk as sdk
import pandas as pd
from tqdm import tqdm

from data_downloader.enums.hyp3 import JobType
from data_downloader.logging import setup_logger, tqdm_handler
from data_downloader.utils import Pairs

if TYPE_CHECKING:
    from datetime import datetime
    from os import PathLike

    from .hyp3_service import HyP3Service
    from .jobs import Jobs


logger = setup_logger(__name__, handler=[tqdm_handler])


class HyP3Jobs(ABC):
    """Abstract class to manage HyP3 jobs."""

    _job_type: JobType
    """The job type. e.g. INSAR_GAMMA, INSAR_ISCE_BURST"""
    date_idx: int
    """The index of the date in the granule name"""
    submit_func: Callable
    """The function to submit the job"""

    def __init__(
        self,
        service: HyP3Service,
        granules: pd.Series | None = None,
        job_parameters: dict | None = None,
    ) -> None:
        """Initialize the InSARJob class.

        Parameters
        ----------
        service : HyP3Service
            HyP3Service instance to submit the job and check the
            submitted jobs.
        granules : pd.Series, optional
            A pandas Series containing granule information, where the
            index represents the granule date and the values are the
            granule names. If not provided, only job downloading from
            HyP3 is supported; job submission is unavailable.
        job_parameters : dict, optional
            Arguments to be passed to the job, by default {}.

            .. hint::
                - You can still modify job parameters after
                initialization by resetting the ``job_parameters``
                attribute.
                - You can use the ``show_parameters`` method to view
                all available submission parameters.

        """
        self.granules = granules if granules is not None else pd.Series([])
        self.service = service
        self.job_type = self._job_type
        self.job_parameters = job_parameters if job_parameters is not None else {}
        self._job_parameters: dict = {}
        """Job parameters."""
        self._pairs_succeed: list = []
        """Pairs that succeeded in the job submission."""
        self._pairs_failed: list = []
        """Pairs that failed in the job submission."""

        # initialize the batch
        self.batch = sdk.Batch()
        self._init_submit_func()

    @abstractmethod
    def _init_submit_func(self) -> None:
        """Initialize the ``submit_func`` function of ``hyp3_sdk.HyP3``.

        .. hint::
            You can use ``self.service.hyp3`` to get the
            ``hyp3_sdk.HyP3`` instance.
        """

    @property
    def jobs_on_service(self) -> Jobs:
        """Get the jobs on the service."""
        self.service.flush()
        return self.service.jobs.sel(job_type=self.job_type)

    @property
    def job_parameters(self) -> dict:
        """Job parameters."""
        return self._job_parameters

    @job_parameters.setter
    def job_parameters(self, job_parameters: dict) -> None:
        """Set the job parameters."""
        if not isinstance(job_parameters, dict):
            err_msg = "job_parameters must be a dictionary."
            raise TypeError(err_msg)
        self._job_parameters = job_parameters

    @property
    def pairs_succeed(self) -> Pairs:
        """Pairs that succeeded in the job submission."""
        return Pairs(self._pairs_succeed)

    @property
    def pairs_failed(self) -> Pairs:
        """Pairs that failed in the job submission."""
        return Pairs(self._pairs_failed)

    def jobs_to_pairs(self, jobs: Jobs) -> Pairs:
        """Convert jobs to pairs."""
        pairs = []
        for job in jobs:
            if job.job_type != self.job_type:
                warnings.warn(
                    f"Job type {job.job_type} is not {self.job_type}. Skipping.",
                    stacklevel=2,
                )
                continue
            if len(job.job_parameters["granules"]) != 2:
                warnings.warn(
                    f"Invalid number of granules for job {job.job_id}. Skipping.",
                    stacklevel=2,
                )
                continue
            pair = (
                granule_to_date(job.job_parameters["granules"][0], self.date_idx),
                granule_to_date(job.job_parameters["granules"][1], self.date_idx),
            )
            pairs.append(pair)
        return Pairs(pairs)

    def _get_remain_pairs(self, pairs: Pairs, skip_existing: bool = True) -> Pairs:
        """Get the remaining pairs to submit."""
        if not skip_existing:
            return pairs

        pairs_exclude = self.jobs_to_pairs(self.jobs_on_service)
        if pairs_exclude is None or len(pairs_exclude) == 0:
            return pairs

        msg = f"Skipping {len(pairs_exclude)} existing pairs already submitted."
        logger.info(msg)
        return pairs - pairs_exclude

    def _submit_job(
        self,
        reference: pd.Series | str,
        secondary: pd.Series | str,
    ) -> None:
        """Submit the job to HyP3."""
        self.batch += self.submit_func(reference, secondary, **self.job_parameters)

    def submit_jobs(self, pairs: Pairs, skip_existing: bool = True) -> None:
        """Submit the job to HyP3.

        Parameters
        ----------
        pairs : Pairs
            Pairs to be submitted to HyP3
        skip_existing : bool, optional
            Whether to skip the existing pairs that have succeeded or are
            running, by default True

        """
        pairs_remain = self._get_remain_pairs(pairs, skip_existing)
        for pair in tqdm(pairs_remain, desc="Submitting jobs"):
            ref, sec = str(pair).split("_")
            reference, secondary = self.granules[ref], self.granules[sec]

            if reference is None or secondary is None:
                msg = f"Granule not found for pair {pair}. Skipping."
                logger.warning(msg)
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
                logger.exception("Failed to submit job for pair %s", pair)
                self._pairs_failed.append(pair)

    def download_jobs(
        self,
        output_dir: PathLike,
        **kwargs,
    ) -> None:
        """Download jobs from HyP3 via the service.

        Delegates to ``self.service.download_jobs`` with this instance's
        ``job_type``. All keyword arguments are forwarded.

        Parameters
        ----------
        output_dir : PathLike
            Output directory to save the files
        **kwargs
            Additional keyword arguments passed to
            ``HyP3Service.download_jobs``.

        """
        self.service.download_jobs(output_dir, self.job_type, **kwargs)


class HyP3JobsGAMMA(HyP3Jobs):
    """Class to manage ``INSAR_GAMMA`` jobs.

    This class provides a pythonic interface to submit and download
    ``INSAR_GAMMA`` jobs from HyP3.
    """

    _job_type = JobType.INSAR_GAMMA
    date_idx = 5

    def _init_submit_func(self) -> None:
        self.submit_func = self.service.hyp3.submit_insar_job


class HyP3JobsBurst(HyP3Jobs):
    """Class to manage ``INSAR_ISCE_BURST`` jobs.

    This class provides a pythonic interface to submit and download
    ``INSAR_ISCE_BURST`` jobs from HyP3.
    """

    _job_type = JobType.INSAR_ISCE_BURST
    date_idx = 3

    def _init_submit_func(self) -> None:
        self.submit_func = self.service.hyp3.submit_insar_isce_burst_job


class HyP3JobsMultiBurst(HyP3Jobs):
    """Class to manage ``INSAR_ISCE_MULTI_BURST`` jobs.

    This class provides a pythonic interface to submit and download
    ``INSAR_ISCE_MULTI_BURST`` jobs from HyP3.

    Unlike ``HyP3JobsBurst``, this class handles granules with duplicated
    dates (multiple burst IDs per date). Each date pair is submitted as a
    single multi-burst job containing all bursts for that date.
    """

    _job_type = JobType.INSAR_ISCE_MULTI_BURST
    date_idx = 3

    def _init_submit_func(self) -> None:
        self.submit_func = self.service.hyp3.submit_insar_isce_multi_burst_job

    def jobs_to_pairs(self, jobs: Jobs) -> Pairs:
        """Convert multi-burst jobs to pairs.

        Multi-burst jobs use ``reference``/``secondary`` lists instead of
        ``granules``, so the first element of each list is used to extract
        the date.
        """
        pairs = []
        for job in jobs:
            if job.job_type != self.job_type:
                warnings.warn(
                    f"Job type {job.job_type} is not {self.job_type}. Skipping.",
                    stacklevel=2,
                )
                continue
            ref_list = job.job_parameters.get("reference", [])
            sec_list = job.job_parameters.get("secondary", [])
            if not ref_list or not sec_list:
                warnings.warn(
                    f"Missing reference or secondary for job {job.job_id}. Skipping.",
                    stacklevel=2,
                )
                continue
            pair = (
                granule_to_date(ref_list[0], self.date_idx),
                granule_to_date(sec_list[0], self.date_idx),
            )
            pairs.append(pair)
        return Pairs(pairs)

    def _submit_job(
        self,
        reference: pd.Series | list[str] | str,
        secondary: pd.Series | list[str] | str,
    ) -> None:
        """Submit a multi-burst job to HyP3.

        Converts ``pd.Series`` to ``list[str]`` for the SDK API.
        """
        if isinstance(reference, pd.Series):
            reference = reference.tolist()
        if isinstance(secondary, pd.Series):
            secondary = secondary.tolist()
        self.batch += self.submit_func(reference, secondary, **self.job_parameters)

    def submit_jobs(self, pairs: Pairs, skip_existing: bool = True) -> None:
        """Submit multi-burst jobs to HyP3.

        Unlike the base class, this method does not call ``_ensure_granules``
        because each date maps to multiple granules (one per burst ID).

        Parameters
        ----------
        pairs : Pairs
            Pairs to be submitted to HyP3
        skip_existing : bool, optional
            Whether to skip the existing pairs that have succeeded or are
            running, by default True

        """
        pairs_remain = self._get_remain_pairs(pairs, skip_existing)
        for pair in tqdm(pairs_remain, desc="Submitting multi-burst jobs"):
            ref, sec = str(pair).split("_")
            reference, secondary = self.granules[ref], self.granules[sec]

            if reference is None or secondary is None:
                msg = f"Granule not found for pair {pair}. Skipping."
                logger.warning(msg)
                self._pairs_failed.append(pair)
                continue

            try:
                self._submit_job(reference, secondary)
                self._pairs_succeed.append(pair)
            except Exception:
                msg = f"Failed to submit multi-burst job for pair {pair}"
                logger.exception(msg)
                self._pairs_failed.append(pair)


def granule_to_date(granule: str, idx_date: int) -> datetime:
    """Convert granule to date."""
    return pd.to_datetime(granule.split("_")[idx_date])


def _ensure_granules(granule: pd.Series | str, pair: Pairs) -> str:
    """Remove the duplicate pairs."""
    if isinstance(granule, pd.Series):
        msg = (
            f"Multiple granules found for pair {pair}: {list(granule)}."
            "First one will be used."
        )
        logger.warning(msg)
        granule = granule[0]
    return str(granule)
