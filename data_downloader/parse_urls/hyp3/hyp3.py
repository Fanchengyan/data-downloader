import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from dateutil.parser import parse as parse_date
from tqdm.auto import tqdm

from .constants import JOB_TYPE, STATUS_CODE

try:
    import hyp3_sdk as sdk
except ImportError:
    raise ImportError(
        "HyP3 SDK not installed. Please install it using 'pip install hyp3_sdk'"
    )

try:
    from faninsar import Pairs, datasets
except ImportError:
    raise ImportError(
        "FanInSAR package not installed. Please install it using 'pip install FanInSAR'"
    )


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
        return Jobs(pd.concat([self.jobs, other.jobs]))

    def __sub__(self, other: "Jobs") -> "Jobs":
        if not isinstance(other, Jobs):
            raise ValueError("Can only subtract Jobs with Jobs instances.")
        mask = np.isin(self.jobs, other.jobs)
        return Jobs(self.jobs[~mask])

    def __iter__(self):
        return iter(self.jobs)

    def __getitem__(self, key):
        return Jobs(self.jobs[key])

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

    def _ensure_datetime(self, val: datetime | str) -> np.datetime64:
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
        return np.array(self._credit_cost, dtype=np.int_)

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
        job_type: JOB_TYPE | None = None,
        status_code: STATUS_CODE | None = None,
        request_time: datetime | str | slice | None = None,
    ) -> "Jobs":
        """Select jobs based on job type and status code

        Parameters
        ----------
        job_type : JOB_TYPE | None
            Job type to filter by
        status_code : STATUS_CODE | None
            Status code to filter by
        request_time : datetime | str | slice | None
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

    @property
    def succeeded(self) -> "Jobs":
        """all succeeded jobs (not expired by default)"""
        return self.sel(status_code=STATUS_CODE.SUCCEEDED)

    @property
    def failed(self) -> "Jobs":
        """all failed jobs (not expired by default)"""
        return self.sel(status_code=STATUS_CODE.FAILED)

    @property
    def pending(self) -> "Jobs":
        """all pending jobs (not expired by default)"""
        return self.sel(status_code=STATUS_CODE.PENDING)

    @property
    def running(self) -> "Jobs":
        """all running jobs (not expired by default)"""
        return self.sel(status_code=STATUS_CODE.RUNNING)


class HyP3Service:
    """Class to manage HyP3 user information and jobs"""

    _my_info = None
    _jobs = None

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
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

    def __repr__(self) -> str:
        return (
            f"HyP3Service(\n    user_id={self.my_info['user_id']}, "
            f"\n    remaining_credits={self.my_info['remaining_credits']}, "
            f"\n    succeeded={len(self.jobs.succeeded)},"
            f"\n    failed={len(self.jobs.failed)},"
            f"\n    pending={len(self.jobs.pending)},"
            f"\n    running={len(self.jobs.running)}"
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

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        prompt: Optional[bool] = False,
    ):
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
    def my_info(self):
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


class InSARMission:
    """Class to manage INSAR_GAMMA jobs. It provides a pythonic interface to
    submit and download InSAR jobs from HyP3.
    """

    job_type = JOB_TYPE.INSAR_GAMMA
    dataset = datasets.HyP3S1

    _pairs_succeed = []
    _pairs_failed = []
    _job_index: int = 0
    _job_parameters: dict

    def __init__(
        self,
        service: HyP3Service,
        granules: pd.Series,
        job_parameters: dict = {},
    ) -> None:
        """Initialize the InSARJob class

        Parameters
        ----------
        service : HyP3Service
            HyP3Service instance to submit the job and check the submitted jobs.
        granules : pd.Series
            A pandas Series containing the granules information. The index of
            the Series should be the date of the granule, and the values should
            be the granule name.
        job_parameters : dict, optional
            Arguments to be passed to the job, by default {}. You can also change
            the job parameters after initializing the class by job_parameters
            attribute.
        """
        self.granules = granules
        self.service = service
        self.job_parameters = job_parameters

        # initialize the batch
        self.batch = sdk.Batch()

    @property
    def jobs_on_service(self) -> Jobs:
        """Get the INSAR_GAMMA jobs on the service"""
        self.service.flush()
        jobs_valid = self.service.jobs.sel(job_type=self.job_type)
        return jobs_valid

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
        if len(self._pairs_succeed) == 0:
            return None
        return Pairs(self._pairs_succeed)

    @property
    def pairs_failed(self) -> Pairs:
        """Pairs that failed in the job submission"""
        if len(self._pairs_failed) == 0:
            return None
        return Pairs(self._pairs_failed)

    def jobs_to_pairs(self, jobs: Jobs) -> Pairs:
        """Convert INSAR_GAMMA jobs to pairs"""
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
                granule_to_date(job.job_parameters["granules"][0]),
                granule_to_date(job.job_parameters["granules"][1]),
            )
            pairs.append(pair)
        if len(pairs) == 0:
            warnings.warn("No valid pairs found.")
            return None
        return Pairs(pairs)

    def _get_remain_pairs(self, pairs: Pairs, skip_existing: bool = True):
        """Get the remaining pairs to submit"""
        if not skip_existing:
            return pairs

        pairs_exclude = self.jobs_to_pairs(self.jobs_valid)
        if pairs_exclude is None:
            return pairs
        warnings.warn(
            f"Skipping {len(pairs_exclude)} existing pairs already submitted."
        )
        pairs_remain = pairs - pairs_exclude
        return pairs_remain

    def _reset_job_index(self):
        """Reset the job index"""
        self._job_index = 0

    def _ensure_granules(self, granule: pd.Series | str) -> str:
        """Remove the duplicate pairs"""
        if isinstance(granule, pd.Series):
            granule = granule[0]
        return granule

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
            try:
                ref, sec = str(pair).split("_")
                reference, secondary = self.granules[ref], self.granules[sec]

                if reference is None or secondary is None:
                    tqdm.write(f"Granule not found for pair {pair}. Skipping.")
                    self._pairs_failed.append(pair)
                    continue

                def _ensure_granules(granule: pd.Series | str) -> str:
                    """Remove the duplicate pairs"""
                    if isinstance(granule, pd.Series):
                        tqdm.write(
                            f"Multiple granules found for pair {pair}: {[i for i in granule]}."
                            "First one will be used."
                        )
                        granule = granule[0]
                    return granule

                reference = _ensure_granules(reference)
                secondary = _ensure_granules(secondary)

                self.batch += self.service.hyp3.submit_insar_job(
                    reference, secondary, **self.job_parameters
                )
                self._pairs_succeed.append(pair)
            except Exception as e:
                params = {"granule1": reference, "granule2": secondary}
                params.update(self.job_parameters)

                tqdm.write(
                    f"Failed to submit job for pair {pair}. {e}."
                    f"\nJob parameters: {params}"
                )
                self._pairs_failed.append(pair)


def granule_to_date(granule: str):
    """Convert granule to date"""
    return pd.to_datetime(granule.split("_")[5])
