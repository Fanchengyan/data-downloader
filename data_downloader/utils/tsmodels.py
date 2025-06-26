from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Sequence

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from datetime import datetime


class TimeSeriesModels:
    """Base class for time series models."""

    _unit: Literal["year", "day"]
    _dates: pd.DatetimeIndex
    _date_spans: np.ndarray

    # Following attributes should be set in subclasses
    _G_br: np.ndarray
    _param_names: list[str]

    __slots__ = ["_G_br", "_date_spans", "_dates", "_param_names", "_unit"]

    def __init__(
        self,
        dates: pd.DatetimeIndex | Sequence[datetime],
        unit: Literal["year", "day"] = "day",
    ) -> None:
        """Initialize TimeSeriesModels.

        Parameters
        ----------
        dates : pd.DatetimeIndex | Sequence[datetime]
            Dates of SAR acquisitions. This can be easily obtained by accessing
            :attr:`Pairs.dates <faninsar.Pairs.dates>`.
        unit : Literal["year", "day"], optional
            Unit of day spans in time series model, by default "day".

        """
        self._unit = None
        self._dates = None
        self._date_spans = None

        self.unit = unit
        self.dates = dates

    def __str__(self) -> str:
        """Return a string representation of the object."""
        return f"{self.__class__.__name__}(dates: {len(self.dates)}, unit: {self.unit})"

    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return (
            f"{self.__class__.__name__}(\n"
            f"    dates: {len(self.dates)}\n"
            f"    unit: {self.unit}\n"
            f"    param_names: {self.param_names}\n"
            f"    G_br shape: {self.G_br.shape})\n"
            ")"
        )

    @property
    def unit(self) -> str:
        """Unit of date_spans in time series model."""
        return self._unit

    @unit.setter
    def unit(
        self,
        unit: Literal["year", "day"],
    ) -> None:
        """Update unit."""
        if unit not in ["day", "year"]:
            msg = "unit must be either day or year"
            raise ValueError(msg)
        if unit != self._unit and self._unit is not None:
            self._date_spans = self._date_spans * (
                1 / 365.25 if unit == "year" else 365.25
            )
        self._unit = unit

    @property
    def dates(self) -> pd.DatetimeIndex:
        """Dates of SAR acquisitions."""
        return self._dates

    @dates.setter
    def dates(self, dates: pd.DatetimeIndex) -> None:
        """Update dates."""
        if not isinstance(dates, pd.DatetimeIndex):
            try:
                dates = pd.to_datetime(dates)
            except Exception as e:
                msg = "dates must be either pd.DatetimeIndex or iterable of datetime"
                raise TypeError(msg) from e
        self._dates = dates
        date_spans = (dates - dates[0]).days.values
        if self.unit == "year":
            date_spans = date_spans / 365.25
        self._date_spans = date_spans

    @property
    def date_spans(self) -> np.ndarray:
        """Date spans of SAR acquisitions in unit of year or day."""
        return self._date_spans

    @property
    def G_br(self) -> np.ndarray:  # noqa: N802
        """Bottom right block of the design matrix G in NSBAS inversion."""
        return self._G_br

    @property
    def param_names(self) -> list[str]:
        """Parameter names in time series model."""
        return self._param_names


class LinearModel(TimeSeriesModels):
    """Linear model."""

    def __init__(
        self,
        dates: pd.DatetimeIndex | Sequence[datetime],
        unit: Literal["year", "day"] = "day",
    ) -> None:
        """Initialize LinearModel.

        Parameters
        ----------
        dates : pd.DatetimeIndex | Sequence[datetime]
            Dates of SAR acquisitions. This can be easily obtained by accessing
            :attr:`Pairs.dates <faninsar.Pairs.dates>`.
        unit : Literal["year", "day"], optional
            Unit of day spans in time series model, by default "day".

        """
        super().__init__(dates, unit=unit)

        self._G_br = np.array([self.date_spans, np.ones_like(self.date_spans)]).T
        self._param_names = ["velocity", "constant"]
