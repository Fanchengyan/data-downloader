from __future__ import annotations

from datetime import datetime
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from data_downloader.logging import setup_logger

from .pairs import Pairs

logger = setup_logger(__name__)


class Baselines:
    """A class manage the baselines of the interferograms."""

    def __init__(
        self,
        dates: pd.DatetimeIndex | Sequence[datetime],
        values: np.ndarray,
    ) -> None:
        """Initialize the Baselines object.

        Parameters
        ----------
        dates : pd.DatetimeIndex | Sequence[datetime]
            The dates of the SAR acquisitions.
        values : np.ndarray
            The cumulative values of the baselines relative to the first
            acquisition.

        """
        dates = pd.to_datetime(dates)
        values = np.asarray(values, dtype=np.float32).flatten()

        if len(dates) != len(values):
            msg = "The length of dates and values should be the same."
            raise ValueError(msg)

        self._dates = dates
        self._values = np.asarray(values, dtype=np.float32)

    def __repr__(self) -> str:
        """Return the representation of the Baselines object."""
        return f"Baselines(num={len(self)})"

    def __str__(self) -> str:
        """Return the string representation of the Baselines object."""
        return f"Baselines(num={len(self)})"

    def __len__(self) -> int:
        """Return the number of the baselines."""
        return len(self.values)

    @property
    def series(self) -> pd.Series:
        """Return the Series of the baselines."""
        return pd.Series(self.values, index=self.dates)

    @property
    def values(self) -> np.ndarray:
        """Return the values of the baselines."""
        return self._values

    @property
    def dates(self) -> pd.DatetimeIndex:
        """Return the dates of the SAR acquisitions."""
        return self._dates

    @classmethod
    def from_pair_wise(cls, pairs: Pairs, values: np.ndarray) -> Baselines:
        """Generate the Baselines object from the pair-wise baseline.

        Parameters
        ----------
        pairs : Pairs
            The pairs instance of the interferograms.
        values : np.ndarray
            The values of spatial baselines of the pairs.

        Returns
        -------
        baselines : Baselines
            The Baselines object.

        """
        from .inversion import NSBASInversion, NSBASMatrixFactory
        from .tsmodels import LinearModel

        model_bs = LinearModel(pairs.dates)
        mf = NSBASMatrixFactory(values[:, None], pairs, model_bs)
        incs, *_ = NSBASInversion(mf, verbose=False).inverse()

        cum = np.cumsum(incs, axis=0)
        cum = np.insert(cum, 0, 0, axis=0)
        return cls(pairs.dates, cum.flatten())

    def to_pair_wise(self, pairs: Pairs) -> pd.Series:
        """Generate the pair-wise baseline from the Baselines object.

        Parameters
        ----------
        pairs : Pairs
            The pairs of the interferograms.

        Returns
        -------
        values : np.ndarray
            The values of the baselines.

        """
        baselines = self.series[pairs.secondary] - self.series[pairs.primary]
        bs = pd.Series(baselines, index=pairs.to_names())
        bs.index.name = "pairs"
        bs.name = "baseline"
        return bs

    def plot(
        self,
        pairs: Pairs,
        pairs_removed: Pairs | None = None,
        plot_gaps: bool = True,
        ax: Axes | None = None,
        xlabel: str = "Acquisition date",
        ylabel: str = "Perpendicular baseline (m)",
        legend: bool = True,
        legend_labels: list[str] | None = None,
        pairs_kwargs: dict | None = None,
        pairs_removed_kwargs: dict | None = None,
        acq_kwargs: dict | None = None,
        gaps_kwargs: dict | None = None,
    ) -> Axes:
        """Plot the baselines of the interferograms.

        Parameters
        ----------
        pairs : Pairs
            All pairs used (temporal baseline).
        pairs_removed : Pairs, optional
            The pairs of the interferograms which are removed. Default is None.
        plot_gaps : bool
            Whether to plot the gaps between the acquisitions. Default is True.
        ax : matplotlib.axis.Axes
            The axes of the plot. Default is None, which means a new plot will
            be created.
        xlabel : str
            The label of the x-axis. Default is "Acquisition date".
        ylabel : str
            The label of the y-axis. Default is "Perpendicular baseline (m)".
        legend : bool
            Whether to show the legend. Default is True.
        legend_labels : list[str] | None
            The labels of the legend in the order of [valid pairs, removed pairs,
            acquisitions, gaps]. Default is None,
        pairs_kwargs : dict
            The keyword arguments for the pairs to :meth:`plt.plot`. Default is
            None.
        pairs_removed_kwargs : dict
            The keyword arguments for the pairs remove to :meth:`plt.plot`.
            Default is None.
        acq_kwargs : dict
            The keyword arguments for the acquisitions to :meth:`plt.plot`.
            Default is {}.
        gaps_kwargs : dict
            The keyword arguments for the gaps to :meth:`plt.vlines`. Default is
            None.

        Returns
        -------
        ax : matplotlib.axis.Axes
            The axes of the plot.

        """
        if gaps_kwargs is None:
            gaps_kwargs = {}
        if acq_kwargs is None:
            acq_kwargs = {}
        if pairs_removed_kwargs is None:
            pairs_removed_kwargs = {}
        if pairs_kwargs is None:
            pairs_kwargs = {}
        if legend_labels is None:
            legend_labels = ["Remained pairs", "Removed pairs", "Acquisitions", "Gaps"]
        if ax is None:
            ax = plt.gca()

        pairs_kwargs = {"c": "tab:blue", "alpha": 0.5, "ls": "-"}
        pairs_removed_kwargs = {"c": "r", "alpha": 0.3, "ls": "--"}

        pairs_kwargs.update(pairs_kwargs)
        pairs_removed_kwargs.update(pairs_removed_kwargs)

        pairs_valid = pairs
        if pairs_removed is not None:
            pairs_valid = pairs - pairs_removed

        # plot valid pairs
        line_valid = None
        line_removed = None
        line_gaps = None
        for pair in pairs_valid:
            start, end = pair.primary, pair.secondary
            line_valid = ax.plot(
                [start, end],
                [self.series[start], self.series[end]],
                **pairs_kwargs,
            )[0]
        # plot removed pairs
        if pairs_removed is not None:
            for pair in pairs_removed:
                start, end = pair.primary, pair.secondary
                line_removed = ax.plot(
                    [start, end],
                    [self.series[start], self.series[end]],
                    **pairs_removed_kwargs,
                )[0]
        # plot acquisitions
        pairs_kwargs = {"c": "tab:blue", "marker": "o", "ls": "", "alpha": 0.5}
        pairs_kwargs.update(acq_kwargs)
        acq = ax.plot(self.dates, self.values, **pairs_kwargs)[0]

        # plot gaps
        if plot_gaps:
            gaps = pairs.parse_gaps(pairs_removed)
            offset = pairs.days.min() / 2
            gaps = gaps - pd.Timedelta(offset, "D")

            dates_valid = np.setdiff1d(pairs.dates, gaps)
            vals = self.series[dates_valid]
            margin = vals.std() / 3
            ymin, ymax = vals.min() - margin, vals.max() + margin
            gaps_kwargs_ = {"color": "k", "ls": "--", "alpha": 0.5}
            gaps_kwargs_.update(gaps_kwargs)
            line_gaps = ax.vlines(gaps, ymin=ymin, ymax=ymax, **gaps_kwargs_)

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if legend:
            handles = []
            labels = []
            if line_valid is not None:
                handles.append(line_valid)
                labels.append(legend_labels[0])
            if line_removed is not None:
                handles.append(line_removed)
                labels.append(legend_labels[1])
            handles.append(acq)
            labels.append(legend_labels[2])
            if line_gaps is not None:
                handles.append(line_gaps)
                labels.append(legend_labels[3])
            ax.legend(handles, labels)

        return ax
