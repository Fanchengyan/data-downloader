from __future__ import annotations

from datetime import datetime

import hyp3_sdk as sdk
import numpy as np
import pandas as pd
from dateutil.parser import parse as parse_date

from data_downloader.logging import setup_logger

from data_downloader.enums.hyp3 import JobStatus, JobType

logger = setup_logger(__name__)


def id_of_job(job: sdk.Job) -> str:
    return f"{job.job_id}{job.job_type}"


class Job(sdk.Job):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __hash__(self) -> int:
        return hash(id_of_job(self))

    def __lt__(self, other: "Job") -> bool:
        return id_of_job(self) < id_of_job(other)

    def __eq__(self, other: "Job") -> bool:
        return id_of_job(self) == id_of_job(other)

    def __gt__(self, other: "Job") -> bool:
        return id_of_job(self) > id_of_job(other)

    @staticmethod
    def from_dict(input_dict: dict):
        expiration_time = (
            parse_date(input_dict["expiration_time"])
            if input_dict.get("expiration_time")
            else None
        )
        return Job(
            job_type=input_dict["job_type"],
            job_id=input_dict["job_id"],
            request_time=parse_date(input_dict["request_time"]),
            status_code=input_dict["status_code"],
            user_id=input_dict["user_id"],
            name=input_dict.get("name"),
            job_parameters=input_dict.get("job_parameters"),
            files=input_dict.get("files"),
            logs=input_dict.get("logs"),
            browse_images=input_dict.get("browse_images"),
            thumbnail_images=input_dict.get("thumbnail_images"),
            expiration_time=expiration_time,
            processing_times=input_dict.get("processing_times"),
            credit_cost=input_dict.get("credit_cost"),
        )


class Jobs:
    """A class to manage HyP3 jobs. It provides a pythonic interface to filter
    and select jobs using the numpy and pandas libraries. This class is designed
    to be used as the jobs attribute of the HyP3Service class.
    """

    def __init__(self, jobs: list[sdk.Job]) -> None:
        """Initialize the Jobs class

        Parameters
        ----------
        jobs : list[sdk.Job]
            List of Job objects from HyP3 SDK. You can get the jobs from the
            hyp3_sdk.Batch.jobs attribute.
        """
        self.jobs = pd.Series(
            [Job.from_dict(i.to_dict()) for i in jobs],
            dtype="O",
        )
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

    def __add__(self, other: "Jobs") -> "Jobs":
        if not isinstance(other, Jobs):
            raise ValueError("Can only sum Jobs with Jobs instances.")
        return Jobs(pd.concat([self.jobs, other.jobs]).tolist())

    def __sub__(self, other: "Jobs") -> "Jobs":
        if not isinstance(other, Jobs):
            raise ValueError("Can only subtract Jobs with Jobs instances.")
        mask = np.isin(self.jobs, other.jobs)
        return Jobs(self.jobs[~mask].tolist())

    def __iter__(self):
        return iter(self.jobs)

    def __getitem__(self, key):
        return Jobs(self.jobs[key].tolist())

    def _retrieve_jobs(self) -> list[list]:
        """Retrieve jobs based on job type and status code

        Parameters
        ----------
        job_type : Literal[job_type]
            Job type to filter by
        status_code : Literal[status_code]
            Status code to filter by
        """
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

        return [
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
        ]

    def _retrieve_list(self, val: list | None) -> str | None:
        """Retrieve job from a list"""
        if val is None:
            return None
        if len(val) == 0:
            return None
        return val[0]

    def _ensure_datetime(self, val: datetime | str) -> datetime:
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
        return np.array(self._credit_cost, dtype=np.float32)

    @property
    def total_credit_cost(self) -> int:
        """the total credit cost of all jobs"""
        return np.nansum(self.credit_cost)

    @property
    def frame(self) -> pd.DataFrame:
        """jobs in the form of a pandas DataFrame"""
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
        name: str | None = None,
        job_type: JobType | None = None,
        status_code: JobStatus | None = None,
        request_time: datetime | str | slice | None = None,
    ) -> "Jobs":
        """Select jobs based on job type and status code

        Parameters
        ----------
        name : str | None
            Name of the job to filter by
        job_type : JobType | None
            Job type to filter by
        status_code : JobStatus | None
            Status code to filter by
        request_time : datetime | str | slice | None
            Request time to filter by. Can be a datetime object, a string, or a slice object. If a slice object is used, the start must be a string or a datetime object, and the stop can be None, a string, or a datetime object. If a string is used, it must be in the format that can be converted to a datetime object using pd.to_datetime. by default None
        """
        if job_type is not None and not hasattr(JobType, job_type):
            raise ValueError(
                f"Invalid job type: {job_type}. Valid job types are: {JobType.variables()}"
            )
        if status_code is not None and not hasattr(JobStatus, status_code):
            raise ValueError(
                f"Invalid status code: {status_code}. Valid status codes are: {JobStatus.variables()}"
            )

        mask = np.ones(len(self.frame), dtype=bool)
        if request_time is not None:
            if isinstance(request_time, slice):
                if request_time.start is None:
                    msg = "The start of the slice must be a string or a datetime object"
                    logger.error(msg)
                    raise ValueError(msg)
                else:
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

        if name is not None:
            mask = (self.name == name) & mask
        if job_type is not None:
            mask = (self.job_type == job_type) & mask
        if status_code is not None:
            mask = (self.status_code == status_code) & mask

        return Jobs(self.jobs[mask].tolist())

    @property
    def succeeded(self) -> "Jobs":
        """all succeeded jobs (not expired by default)"""
        return self.sel(status_code=JobStatus.SUCCEEDED)

    @property
    def failed(self) -> "Jobs":
        """all failed jobs (not expired by default)"""
        return self.sel(status_code=JobStatus.FAILED)

    @property
    def pending(self) -> "Jobs":
        """all pending jobs (not expired by default)"""
        return self.sel(status_code=JobStatus.PENDING)

    @property
    def running(self) -> "Jobs":
        """all running jobs (not expired by default)"""
        return self.sel(status_code=JobStatus.RUNNING)
