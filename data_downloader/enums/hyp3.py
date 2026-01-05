"""Enums for HyP3."""

from __future__ import annotations

from enum import auto

from data_downloader.enums import BaseConstants


class JobType(BaseConstants):
    """Job types for HyP3."""

    AUTORIFT = auto()
    RTC_GAMMA = auto()
    INSAR_GAMMA = auto()
    INSAR_ISCE_BURST = auto()


class JobStatus(BaseConstants):
    """Job status for HyP3."""

    SUCCEEDED = auto()
    FAILED = auto()
    RUNNING = auto()
    PENDING = auto()
