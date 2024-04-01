from datetime import datetime
from typing import Optional, Union

import numpy as np
import pandas as pd

from .constants import JOB_TYPE, STATUS_CODE

try:
    import hyp3_sdk as sdk
except ImportError:
    raise ImportError(
        "HyP3 SDK not installed. Please install it using 'pip install hyp3_sdk'"
    )


class Jobs:
    """Class to manage HyP3 jobs. It provides a basic jobs interface for the HyP3Service class."""

    def __init__(self, jobs: list[sdk.Job]) -> None:
        """Initialize the Jobs class

        Parameters
        ----------
        jobs : list[sdk.Job]
            List of Job objects from HyP3 SDK
        """
        self.jobs = np.array(jobs, dtype="O")
        (
            self._job_id,
            self._job_type,
            self._request_time,
            self._status_code,
            self._user_id,
            self._name,
            self._job_parameters,
            self._files,
            self._logs,
            self._browse_images,
            self._thumbnail_images,
            self._expiration_time,
            self._processing_times,
            self._credit_cost,
        ) = self._retrieve_jobs()

    def __repr__(self) -> str:
        return f"Jobs({len(self.jobs)})"

    def __len__(self) -> int:
        return len(self.jobs)

    def _retrieve_jobs(self) -> list[sdk.Job]:
        """Retrieve jobs based on job type and status code

        Parameters
        ----------
        job_type : Literal[job_type]
            Job type to filter by
        status_code : Literal[status_code]
            Status code to filter by
        """
        """Convert the jobs to a pandas DataFrame"""
        job_id = []
        job_type = []
        request_time = []
        status_code = []
        user_id = []
        name = []
        job_parameters = []
        files = []
        logs = []
        browse_images = []
        thumbnail_images = []
        expiration_time = []
        processing_times = []
        credit_cost = []
        for job in self.jobs:
            job_id.append(job.job_id)
            job_type.append(job.job_type)
            request_time.append(job.request_time)
            status_code.append(job.status_code)
            user_id.append(job.user_id)
            name.append(job.name)
            job_parameters.append(job.job_parameters)
            files.append(self._retrieve_files(job.files))
            logs.append(self._retrieve_list(job.logs))
            browse_images.append(self._retrieve_list(job.browse_images))
            thumbnail_images.append(self._retrieve_list(job.thumbnail_images))
            expiration_time.append(job.expiration_time)
            processing_times.append(self._retrieve_list(job.processing_times))
            credit_cost.append(job.credit_cost)

        return (
            job_id,
            job_type,
            request_time,
            status_code,
            user_id,
            name,
            job_parameters,
            files,
            logs,
            browse_images,
            thumbnail_images,
            expiration_time,
            processing_times,
            credit_cost,
        )

    def _retrieve_list(self, val: Optional[list]) -> Optional[str]:
        """Retrieve job from a list"""
        if val is None:
            return np.nan
        if len(val) == 0:
            return np.nan
        return val[0]

    def _ensure_datetime(self, val: Union[datetime, str]) -> np.datetime64:
        """Convert a string to a datetime object, otherwise return the object"""
        if isinstance(val, str):
            return pd.to_datetime(val)
        return val

    def _retrieve_files(self, files: list) -> dict:
        """Retrieve files from a list"""
        dict_null = {"filename": np.nan, "s3": np.nan, "size": np.nan, "url": np.nan}
        if files is None:
            return dict_null
        if len(files) == 0:
            return dict_null
        return files[0]

    @property
    def job_type(self) -> np.ndarray:
        """the job type of all jobs"""
        return np.array(self._job_type, dtype=np.str_)

    @property
    def job_id(self) -> np.ndarray:
        """the job ID of all jobs"""
        return np.array(self._job_id, dtype=np.str_)

    @property
    def request_time(self) -> np.ndarray:
        """the request time of all jobs"""
        return np.array(self._request_time, dtype="M8[D]")

    @property
    def status_code(self) -> np.ndarray:
        """the status code of all jobs"""
        return np.array(self._status_code, dtype=np.str_)

    @property
    def user_id(self) -> np.ndarray:
        """the user ID of all jobs"""
        return np.array(self._user_id, dtype=np.str_)

    @property
    def name(self) -> np.ndarray:
        """the name of all jobs"""
        return np.array(self._name, dtype=np.str_)

    @property
    def job_parameters(self) -> np.ndarray:
        """the job parameters of all jobs"""
        return np.array(self._job_parameters, dtype="O")

    @property
    def files(self) -> np.ndarray:
        """the files of all jobs"""
        return np.array(self._files, dtype="O")

    @property
    def file_names(self) -> np.ndarray:
        """the file names of all jobs"""
        return np.array([file["filename"] for file in self._files])

    @property
    def file_urls(self) -> np.ndarray:
        """the file urls of all jobs"""
        return np.array([file["url"] for file in self._files])

    @property
    def file_sizes(self) -> np.ndarray:
        """the file sizes of all jobs"""
        return np.array([file["size"] for file in self._files])

    @property
    def df_files(self) -> pd.DataFrame:
        """the files of all jobs"""
        return pd.DataFrame(self._files, columns=["filename", "s3", "size", "url"])

    @property
    def logs(self) -> np.ndarray:
        """the logs of all jobs"""
        return np.array(self._logs, dtype=np.str_)

    @property
    def browse_images(self) -> np.ndarray:
        """the browse images of all jobs"""
        return np.array(self._browse_images)

    @property
    def thumbnail_images(self) -> np.ndarray:
        """the thumbnail images of all jobs"""
        return np.array(self._thumbnail_images, dtype=np.str_)

    @property
    def expiration_time(self) -> np.ndarray:
        """the expiration time of all jobs"""
        return np.array(self._expiration_time, dtype="M8[D]")

    @property
    def processing_times(self) -> np.ndarray:
        """the processing times of all jobs"""
        return np.array(self._processing_times, dtype=np.str_)

    @property
    def credit_cost(self) -> np.ndarray:
        """the credit cost of all jobs"""
        return np.array(self._credit_cost, dtype=np.int_)

    @property
    def total_credit_cost(self) -> int:
        """the total credit cost of all jobs"""
        return np.nansum(self.credit_cost)

    @property
    def frame(self) -> pd.DataFrame:
        """Convert the jobs to a pandas DataFrame"""
        df = pd.DataFrame(
            {
                "name": self.name,
                "job_type": self.job_type,
                "status_code": self.status_code,
                "file_names": self.file_names,
                "file_sizes": self.file_sizes,
                "file_urls": self.file_urls,
                "credit_cost": self.credit_cost, 
                "request_time": self.request_time,
                "processing_times": self.processing_times,
                "expiration_time": self.expiration_time,
                "job_parameters": self.job_parameters,
                "user_id": self.user_id,
                "logs": self.logs,
                "browse_images": self.browse_images,
                "thumbnail_images": self.thumbnail_images,
            },
            index=self.job_id,
        )
        df.index.name = "job_id"
        return df

    def sel(
        self,
        job_type: Optional[JOB_TYPE] = None,
        status_code: Optional[STATUS_CODE] = None,
        request_time: Optional[Union[datetime, str, slice]] = None,
    ) -> "Jobs":
        """Select jobs based on job type and status code

        Parameters
        ----------
        job_type : Optional[JOB_TYPE]
            Job type to filter by
        status_code : Optional[STATUS_CODE]
            Status code to filter by
        request_time : Optional[Union[datetime,str,slice]]
            Request time to filter by. Can be a datetime object, a string, or a slice object. If a slice object is used, the start must be a string or a datetime object, and the stop can be None, a string, or a datetime object. If a string is used, it must be in the format that can be converted to a datetime object using pd.to_datetime. by default None
        """
        if job_type != None and not hasattr(JOB_TYPE, job_type):
            raise ValueError(
                f"Invalid job type: {job_type}. Valid job types are: {JOB_TYPE.variables()}"
            )
        if status_code != None and not hasattr(STATUS_CODE, status_code):
            raise ValueError(
                f"Invalid status code: {status_code}. Valid status codes are: {STATUS_CODE.variables()}"
            )

        mask = np.ones(len(self.frame), dtype=bool)
        if request_time is not None:
            if isinstance(request_time, slice):
                if request_time.start is not None:
                    start = self._ensure_datetime(request_time.start)
                if request_time.stop is None:
                    end = datetime.now().date()
                else:
                    end = self._ensure_datetime(request_time.stop)
                mask = (self.request_time >= start) & (self.request_time <= end)
            if isinstance(request_time, str):
                request_time = self._ensure_datetime(request_time)
                mask = self.request_time == request_time
            if isinstance(request_time, datetime):
                mask = self.request_time == request_time

        if job_type is not None:
            mask = (self.job_type == job_type) & mask
        if status_code is not None:
            mask = (self.status_code == status_code) & mask

        return Jobs(self.jobs[mask])


class HyP3Service:
    """Class to manage HyP3 jobs and user information."""

    _my_info = None
    _jobs = None

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        prompt: bool = False,
        include_expired=False,
    ):
        self.hyp3 = sdk.HyP3(username=username, password=password, prompt=prompt)
        self.include_expired = include_expired
        self.flush()

    def __repr__(self) -> str:
        return (
            f"HyP3Service(\n    user_id={self.my_info['user_id']}, "
            f"\n    remaining_credits={self.my_info['remaining_credits']}, "
            f"\n    succeeded={len(self.succeeded)},"
            f"\n    failed={len(self.failed)},"
            f"\n    pending={len(self.pending)},"
            f"\n    running={len(self.running)}"
            "\n)"
        )

    def __str__(self) -> str:
        return f"Hyp3Service({self.my_info['user_id']}, remaining_credits={self.my_info['remaining_credits']})"

    def flush_jobs(self):
        """Flush the jobs"""
        self._jobs = self._parse_jobs()

    def flush_info(self):
        """Flush the user's information"""
        self._my_info = self.hyp3.my_info()

    def flush(self):
        """Flush the jobs and the user's information"""
        self.flush_jobs()
        self.flush_info()

    @property
    def my_info(self):
        """Get the user's information"""
        return self._my_info

    @property
    def jobs(self) -> Jobs:
        """Get the jobs"""
        return self._jobs

    def _parse_jobs(self) -> Jobs:
        """Parse the jobs not expired"""
        batch = self.hyp3.find_jobs().filter_jobs(include_expired=self.include_expired)
        return Jobs(batch.jobs)

    @property
    def succeeded(self) -> Jobs:
        """Get the succeeded jobs"""
        return self.jobs.sel(status_code=STATUS_CODE.SUCCEEDED)

    @property
    def failed(self) -> Jobs:
        """Get the failed jobs"""
        return self.jobs.sel(status_code=STATUS_CODE.FAILED)

    @property
    def pending(self) -> Jobs:
        """Get the pending jobs"""
        return self.jobs.sel(status_code=STATUS_CODE.PENDING)

    @property
    def running(self) -> Jobs:
        """Get the running jobs"""
        return self.jobs.sel(status_code=STATUS_CODE.RUNNING)
