"""This module provides the Pair and Pairs classes to handle pairs of InSAR data.
``Pair`` and ``Pairs`` class are modified from the FanInSAR package.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, overload

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from ..logging import setup_logger

if TYPE_CHECKING:
    from numpy.typing import DTypeLike, NDArray

logger = setup_logger(__name__)


class Pair:
    """Pair class for one pair."""

    _values: np.ndarray
    _name: str
    _days: int

    __slots__ = ["_days", "_name", "_values"]

    def __init__(
        self,
        pair: Sequence[datetime, datetime],
    ) -> None:
        """Initialize the Pair class.

        Parameters
        ----------
        pair: Sequence[datetime, datetime]
            Sequence object of two dates. Each date is a datetime object.
            For example, (date1, date2).

        """
        self._values = np.sort(pair).astype("M8[D]")
        self._name = "_".join(
            [i.strftime("%Y%m%d") for i in self._values.astype("O")],
        )
        self._days = (self._values[1] - self._values[0]).astype(int)

    def __str__(self) -> str:
        """Return the name of the pair."""
        return self._name

    def __repr__(self) -> str:
        """Return the representation of the pair."""
        return f"Pair({self._name})"

    def __eq__(self, other: Pair) -> bool:
        """Compare the pair with another pair."""
        return self.name == other.name

    def __hash__(self) -> int:
        """Return the hash of the pair."""
        return hash(self._name)

    def __array__(self, dtype: DTypeLike = None) -> np.ndarray:
        """Return the pair as a numpy array."""
        return np.asarray(self._values, dtype=dtype)

    @property
    def values(self) -> NDArray[np.datetime64]:
        """The values of the pair with format of datetime."""
        return self._values

    @property
    def name(self) -> str:
        """String of the pair with format of '%Y%m%d_%Y%m%d'."""
        return self._name

    @property
    def days(self) -> int:
        """The time span of the pair in days."""
        return self._days

    @property
    def primary(self) -> pd.Timestamp:
        """The primary dates of all pairs."""
        return pd.Timestamp(self.values[0])

    @property
    def secondary(self) -> pd.Timestamp:
        """The secondary dates of all pairs."""
        return pd.Timestamp(self.values[1])

    def primary_string(self, date_format: str = "%Y%m%d") -> str:
        """Return the primary dates of all pairs in string format.

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.

        """
        return pd.to_datetime(self.values[0]).strftime(date_format)

    def secondary_string(self, date_format: str = "%Y%m%d") -> str:
        """Return the secondary dates of all pairs in string format.

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.

        """
        return pd.to_datetime(self.values[1]).strftime(date_format)

    @classmethod
    def from_name(
        cls,
        name: str,
        parse_function: Callable | None = None,
        date_args: dict | None = None,
    ) -> Pair:
        """Initialize the pair class from a pair name.

        Parameters
        ----------
        name: str
            Pair name.
        parse_function: Callable, optional
            Function to parse the date strings from the pair name.
            If None, the pair name will be split by '_' and
            the last 2 items will be used. Default is None.
        date_args: dict, optional
            Keyword arguments for pd.to_datetime() to convert the date strings
            to datetime objects. For example, {'format': '%Y%m%d'}.
            Default is {}.

        Returns
        -------
        pair: Pair
            Pair class.

        """
        if date_args is None:
            date_args = {}
        dates = DateManager.str_to_dates(name, 2, parse_function, date_args)
        return cls(dates)

    def to_numpy(self, dtype: DTypeLike = None) -> NDArray[np.datetime64]:
        """Return the pair as a numpy array."""
        return np.asarray(self._values, dtype=dtype)


class Pairs:
    """Pairs class to handle pairs.

    .. note::
        - Each pair will be sorted in the acquisition order. The primary date
          will be always earlier than the secondary date.
        - The pairs will be sorted by the primary date.



    Examples
    --------
    prepare dates and pairs for examples:

    >>> dates = pd.date_range("20130101", "20231231").values
    >>> n = len(dates)
    >>> pair_ls = []
    >>> loop_ls = []
    >>> for i in range(5):
    ...     np.random.seed(i)
    ...     pair_ls.append(dates[np.random.randint(0, n, 2)])

    initialize pairs from a list of pairs

    >>> pairs = Pairs(pair_ls)
    >>> print(pairs)
        primary  secondary
    0 2013-06-24 2016-02-21
    1 2013-08-24 2015-11-28
    2 2017-08-16 2018-03-14
    3 2020-01-20 2021-11-15
    4 2020-02-21 2020-06-25

    select pairs by date slice

    >>> pairs1 = pairs["2018-03-09":]
    >>> print(pairs1)
        primary  secondary
    0 2020-01-20 2021-11-15
    1 2020-02-21 2020-06-25

    pairs can be added (union)  and subtracted (difference)

    >>> pairs2 = pairs - pairs1
    >>> pairs3 = pairs1 + pairs2
    >>> print(pairs2)
        primary  secondary
    0 2013-06-24 2016-02-21
    1 2013-08-24 2015-11-28
    2 2017-08-16 2018-03-14
    >>> print(pairs3)
        primary  secondary
    0 2013-06-24 2016-02-21
    1 2013-08-24 2015-11-28
    2 2017-08-16 2018-03-14
    3 2020-01-20 2021-11-15
    4 2020-02-21 2020-06-25

    pairs can be compared with `==`and `!=`

    >>> print(pairs3 == pairs)
    >>> print(pairs3 != pairs)
    True
    False

    """

    _values: np.ndarray
    _dates: np.ndarray
    _length: int
    _edge_index: np.ndarray
    _names: np.ndarray

    __slots__ = ["_dates", "_edge_index", "_length", "_names", "_values"]

    def __init__(
        self,
        pairs: Sequence[Sequence[datetime, datetime]] | Sequence[Pair],
        sort: bool = True,
    ) -> None:
        """Initialize the pairs class.

        Parameters
        ----------
        pairs: Sequence
            Sequence object of pairs. Each pair is an Sequence or Pair
            object of two dates with format of datetime. For example,
            [(date1, date2), ...].
        sort: bool, optional
            Whether to sort the pairs. Default is True.

        """
        if pairs is None:
            pairs = []

        _values = np.array(pairs, dtype="M8[D]")

        self._values = self._format_pair_values(_values)
        self._parse_pair_meta()

        if sort:
            self.sort(inplace=True)

    def _format_pair_values(
        self,
        values: NDArray[np.datetime64],
    ) -> NDArray[np.datetime64]:
        """Format the pair values.

        This function is used to make sure the primary date is earlier than the
        secondary date.
        """
        if values.ndim == 1:
            values = values.reshape(-1, 2)
        idx = values[:, 0] > values[:, 1]
        values[idx] = values[idx, ::-1]
        return values

    def _parse_pair_meta(self) -> None:
        self._dates = np.unique(self._values.flatten())
        self._length = self._values.shape[0]
        self._edge_index = np.searchsorted(self._dates, self._values)
        self._names = self.to_names()

    def __len__(self) -> int:
        """Return the number of pairs."""
        return self._length

    def __str__(self) -> str:
        """Return the string representation of the pairs."""
        return f"Pairs({self._length})"

    def __repr__(self) -> str:
        """Return the representation of the pairs."""
        return self._to_frame().__repr__()

    def _repr_html_(self) -> str:
        """Return the HTML representation of the pairs."""
        return formatting_html.pairs_repr(self)

    def __eq__(self, other: Pairs) -> bool:
        """Compare the pairs with another pairs."""
        return np.array_equal(self.values, other.values)

    def __add__(self, other: Pairs) -> Pairs:
        """Return the unique, sorted union of the pairs."""
        _pairs = np.union1d(self.names, other.names)
        return Pairs.from_names(_pairs)

    def __sub__(self, other: Pairs) -> Pairs:
        """Return the difference of the pairs."""
        _pairs = np.setdiff1d(self.names, other.names)

        return Pairs.from_names(_pairs)

    @overload
    def __getitem__(self, index: int | np.integer) -> Pair: ...

    @overload
    def __getitem__(self, index: slice) -> Pairs | None: ...

    def __getitem__(  # noqa: PLR0911, PLR0912
        self,
        index: int | slice | datetime | str | PairLike | Iterable,
    ) -> Pair | Pairs | None:
        """Return the pair or pairs by index or slice."""
        if isinstance(index, slice):
            start, stop, step = index.start, index.stop, index.step
            if isinstance(start, (int, np.integer, type(None))) and isinstance(
                stop,
                (int, np.integer, type(None)),
            ):
                if start is None:
                    start = 0
                if stop is None:
                    stop = self._length
                return Pairs(self._values[start:stop:step])
            if isinstance(
                start,
                (datetime, np.datetime64, pd.Timestamp, str, type(None)),
            ) and isinstance(
                stop,
                (datetime, np.datetime64, pd.Timestamp, str, type(None)),
            ):
                if isinstance(start, str):
                    start = DateManager.ensure_datetime(start)
                if isinstance(stop, str):
                    stop = DateManager.ensure_datetime(stop)
                if start is None:
                    start = self._dates[0]
                if stop is None:
                    stop = self._dates[-1]

                start, stop = (np.datetime64(start, "s"), np.datetime64(stop, "s"))

                if start > stop:
                    msg = (
                        f"Index start {start} should be earlier than index stop {stop}."
                    )
                    raise ValueError(msg)
                _pairs = []
                for pair in self._values:
                    pair = pair.astype("M8[s]")  # noqa: PLW2901
                    if start <= pair[0] <= stop and start <= pair[1] <= stop:
                        _pairs.append(pair)
                if len(_pairs) > 0:
                    return Pairs(_pairs)
                return None
            msg = f"Unsupported slice index {index} for Pairs."
            logger.warning(msg)
            return None
        if isinstance(index, (int, np.integer)):
            if index >= self._length:
                msg = f"Index {index} out of range. Pairs number is {self._length}."
                raise IndexError(
                    msg,
                )
            return Pair(self._values[index])
        if isinstance(index, (datetime, np.datetime64, pd.Timestamp, str)):
            if isinstance(index, str):
                try:
                    index = pd.to_datetime(index)
                except Exception as e:
                    msg = f"String {index} cannot be converted to datetime."
                    raise ValueError(msg) from e
            pairs = [pair for pair in self._values if index in pair]
            if len(pairs) > 0:
                return Pairs(pairs)
            return None
        if isinstance(index, Iterable):
            index = np.array(index)
            return Pairs(self._values[index])
        msg = (
            "Index should be int, slice, datetime, str, or bool or int array"
            f" indexing, but got {type(index)}."
        )
        raise TypeError(
            msg,
        )

    def __hash__(self) -> int:
        """Return the hash of the pairs."""
        return hash("".join(self.names))

    def __iter__(self) -> iter[Pair]:
        """Iterate the pairs."""
        pairs_ls = [Pair(i) for i in self._values]
        return iter(pairs_ls)

    def __array__(self, dtype: DTypeLike = None) -> NDArray:
        """Return the pairs as a numpy array."""
        return np.asarray(self._values, dtype=dtype)

    def _to_frame(self) -> pd.DataFrame:
        """Return the pairs as a DataFrame."""
        pairs_str = "Pairs"
        columns = pd.MultiIndex.from_tuples(
            [(pairs_str, "primary"), (pairs_str, "secondary")],
        )
        return pd.DataFrame(self._values, columns=columns)

    def _ensure_pairs(
        self,
        pairs: str | Pair | Pairs | Sequence[str] | Sequence[Pair],
    ) -> Pairs:
        """Ensure the pairs are in the Pairs object."""
        if isinstance(pairs, str):
            pairs = Pairs.from_names([pairs])
        elif isinstance(pairs, Pair):
            pairs = Pairs([pairs])
        elif isinstance(pairs, Pairs):
            return pairs
        elif isinstance(pairs, Sequence):
            pairs = np.asarray(pairs)
            if pairs.ndim == 1:
                pairs = Pairs.from_names(pairs)
            elif pairs.ndim == 2 and pairs.shape[1] == 2:
                pairs = Pairs(pairs)
            else:
                msg = (
                    "pairs should be 1D array of str, 2D array of datetime, "
                    f"or Pairs, but got {pairs}."
                )
                raise ValueError(msg)
        else:
            msg = (
                "pairs should be str, Pair, list of str, list of Pair, "
                f"or Pairs, but got {type(pairs)}."
            )
            raise TypeError(msg)
        return pairs

    @property
    def values(self) -> NDArray[np.datetime64]:
        """The numpy array of the pairs."""
        return self._values

    @property
    def names(self) -> NDArray[np.str_]:
        """The names (string format) of the pairs."""
        return self._names

    @property
    def dates(self) -> Acquisition:
        """The sorted dates array of all pairs in type of np.datetime64[D]."""
        return Acquisition(pd.to_datetime(self._dates))

    @property
    def days(self) -> DaySpan:
        """The time span of all pairs in days."""
        days = (self._values[:, 1] - self._values[:, 0]).astype(int)
        return DaySpan(days, dtype=np.int32)

    @property
    def primary(self) -> Acquisition:
        """The primary dates of all pairs."""
        if len(self._values) == 0:
            return Acquisition([])
        return Acquisition(pd.to_datetime(self._values[:, 0]))

    @property
    def secondary(self) -> Acquisition:
        """The secondary dates of all pairs."""
        if len(self._values) == 0:
            return Acquisition([])
        return Acquisition(pd.to_datetime(self._values[:, 1]))

    @property
    def xindexes(self) -> Indexes:
        """The xarray indexes of the pairs."""
        indexes = {
            "primary": self.primary,
            "secondary": self.secondary,
            "days": self.days,
            "dates": self.dates,
        }
        variables = {
            "primary": self.primary.to_xarray(),
            "secondary": self.secondary.to_xarray(),
            "days": self.days.to_xarray(),
            "dates": self.dates.to_xarray(),
        }
        return Indexes(indexes=indexes, variables=variables, index_type=pd.Index)

    def primary_string(self, date_format: str = "%Y%m%d") -> pd.Index:
        """Return the primary dates of all pairs in string format.

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.

        """
        return self.primary.strftime(date_format)

    def secondary_string(self, date_format: str = "%Y%m%d") -> pd.Index:
        """Return the secondary dates of all pairs in string format.

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.

        """
        return self.secondary.strftime(date_format)

    @property
    def edge_index(self) -> NDArray[np.int64]:
        """The index of the pairs in the dates coordinate.

        This is useful to construct the edge index in graph theory.
        """
        return self._edge_index

    @property
    def shape(self) -> tuple[int, int]:
        """The shape of the pairs array."""
        return self._values.shape

    @classmethod
    def from_names(
        cls,
        names: Sequence[str | None],
        parse_function: Callable | None = None,
        date_args: dict | None = None,
    ) -> Pairs:
        """Initialize the pair class from a pair name.

        .. note::
            The pairs will be in the order of the input names. If you want to
            sort the pairs, you can call the :meth:`Pairs.sort()` method to
            achieve it.

        Parameters
        ----------
        names: str
            Pair names.
        parse_function: Callable, optional
            Function to parse the date strings from the pair name.
            If None, the pair name will be split by '_' and
            the last 2 items will be used. Default is None.
        date_args: dict, optional
            Keyword arguments for pd.to_datetime() to convert the date strings
            to datetime objects. For example, {'format': '%Y%m%d'}.
            Default is {}.

        Returns
        -------
        pairs: Pairs
            unsorted Pairs object.

        """
        if date_args is None:
            date_args = {}
        pairs = []
        # No names in list
        if len(names) == 0:
            return cls(pairs)
        # Parse the names
        for name in names:
            pair = Pair.from_name(name, parse_function, date_args)
            pairs.append(pair.values)
        return cls(pairs, sort=False)

    def where(
        self,
        pairs: list[str] | list[Pair] | Pairs,
        return_type: Literal["index", "mask"] = "index",
    ) -> NDArray[np.int64 | np.bool_]:
        """Return the index of the pairs.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.
        return_type: str, optional
            Whether to return the index or mask of the pairs. Default is 'index'.

        """
        if return_type not in ["index", "mask"]:
            msg = (
                "return_type should be one of ['index', 'mask'], "
                f"but got {return_type}."
            )
            raise ValueError(msg)

        pairs = self._ensure_pairs(pairs)
        con = np.isin(self.names, pairs.names)
        if return_type == "index":
            con = np.where(con)[0]
        return con

    def intersect(self, pairs: PairLike) -> Pairs | None:
        """Return the intersection of the pairs.

        The pairs both in self and input pairs.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.

        """
        pairs = self._ensure_pairs(pairs)
        return self[self.where(pairs)]

    def union(self, pairs: list[str] | list[Pair] | Pairs) -> Pairs:
        """Return the unique, sorted union of the pairs.

        All pairs that in self and input pairs. Same as addition.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.

        """
        pairs = self._ensure_pairs(pairs)
        return self + pairs

    def difference(self, pairs: PairsLike) -> Pairs | None:
        """Return the difference of the pairs.

        The pairs in self but not in pairs. Same as subtraction.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.

        """
        pairs = self._ensure_pairs(pairs)
        return self - pairs

    def copy(self) -> Pairs:
        """Return a copy of the pairs."""
        return Pairs(self._values.copy())

    def sort(
        self,
        order: PairsOrder = "pairs",
        ascending: bool = True,
        inplace: bool = True,
    ) -> tuple[Pairs, NDArray[np.int64]] | None:
        """Sort the pairs.

        Parameters
        ----------
        order: str or list of str, optional
            By which fields to sort the pairs. This argument specifies
            which fields to compare first, second, etc. Default is 'pairs'.

            The available options are one or a list of:
            ['pairs', 'primary', 'secondary', 'days'].
        ascending: bool, optional
            Whether to sort ascending. Default is True.
        inplace: bool, optional
            Whether to sort the pairs inplace. Default is True.

        Returns
        -------
        None or (Pairs, np.ndarray). if inplace is True, return the sorted pairs
        and the index of the sorted pairs in the original pairs. Otherwise,
        return None.

        """
        # for null pairs
        if len(self) == 0:
            if inplace:
                return None
            return self

        # for valid pairs
        item_map = {
            "pairs": self._values,
            "primary": self._values[:, 0],
            "secondary": self._values[:, 1],
            "days": self.days.data,
        }
        if isinstance(order, str):
            order = [order]
        _values_ = []
        for i in order:
            if i not in item_map:
                msg = (
                    f"order should be one of {list(item_map.keys())}, but got {order}."
                )
                raise ValueError(
                    msg,
                )
            _values_.append(item_map[i].reshape(self._length, -1))
        _values_ = np.hstack(_values_)
        _values, _index = np.unique(_values_, axis=0, return_index=True)
        if not ascending:
            _index = _index[::-1]
        if inplace:
            self._values = _values
            self._parse_pair_meta()
            return None
        return Pairs(_values), _index

    def to_names(self, prefix: str | None = None) -> NDArray[np.str_]:
        """Generate pairs names string with prefix.

        Parameters
        ----------
        prefix: str
            Prefix of the pair file names. Default is None.

        Returns
        -------
        names: np.ndarray
            Pairs names string with format of '%Y%m%d_%Y%m%d'.

        """
        names = (
            pd.DatetimeIndex(self.primary).strftime("%Y%m%d")
            + "_"
            + pd.DatetimeIndex(self.secondary).strftime("%Y%m%d")
        )
        if prefix:
            names = prefix + "_" + names

        return names.to_numpy(dtype=np.str_)

    def to_numpy(self, dtype: DTypeLike = None) -> NDArray[np.datetime64]:
        """Return the pairs as a numpy array."""
        return np.asarray(self._values, dtype=dtype)

    def to_frame(self) -> pd.DataFrame:
        """Return the pairs as a DataFrame."""
        frame = pd.DataFrame()
        frame["primary"] = self.primary
        frame["secondary"] = self.secondary
        frame["days"] = self.days
        return frame

    def to_xarray(self) -> pd.DataFrame:
        """Return the pairs as a xarray DataArray."""
        return xr.Variable(dims=["pairs", "primary-secondary"], data=self._values)

    def to_triplet_loops(self) -> TripletLoops:
        """Return all possible triplet loops from the pairs."""
        from faninsar import TripletLoops

        loops = []
        for i, pair12 in enumerate(self._values):
            for pair23 in self._values[i + 1 :]:
                if pair12[1] == pair23[0] and Pair([pair12[0], pair23[1]]) in self:
                    loops.append([pair12[0], pair12[1], pair23[1]])  # noqa: PERF401
        return TripletLoops(loops)

    def to_loops(
        self,
        max_acquisition: int = 5,
        max_days: int | None = None,
        edge_pairs: Pairs | None = None,
        edge_days: int | None = None,
    ) -> Loops:
        r"""Return all possible loops from the pairs.

        .. important::
            The pairs in the loops may be fewer than the input pairs. You can use
            the :meth:`Pairs.where` method to get the index/mask of the pairs
            in the loops from the input pairs.

            **Example**:

            >>> loops = pairs.to_loops()
            >>> mask = pairs.where(loops.pairs, return_type="mask")

        Parameters
        ----------
        max_acquisition: int
            The maximum number of acquisitions in the loops. It should be at least 3.

            .. note::
                The number of acquisitions is equal to the number of intervals + 1
                :math:`n (acquisition) = n (edge\ pairs) + 1 (diagonal\ pair) =
                n (intervals) + 1`.
        max_days: int, optional
            The maximum number of days for the pairs in the loops. If None, all
            available pairs will be used. Default is None.
        edge_pairs: Pairs, optional
            The edge pairs to form loops. If None, ``edge_days`` must be provided.
        edge_days: int, optional
            The maximum number of days used to identify the edge pairs. If None,
            ``edge_pairs`` must be provided. Default is None.

            .. note::
                This parameter will be ignored if ``edge_pairs`` is provided.

        """
        # a list containing all loops
        loops = []
        if edge_pairs is None:
            if edge_days is None:
                msg = "Either edge_days or edge_pairs should be provided."
                raise ValueError(msg)
            edge_pairs = self[self.days <= edge_days]
        # find valid diagonal pairs
        for i in self - edge_pairs:
            if max_days is not None and i.days > max_days:
                continue
            if not valid_diagonal_pair(i, self, edge_pairs):
                continue
            start_date, end_date = i.values[0], i.values[1]

            # find valid primary pairs
            mask_primaries = (self.primary == start_date) & (self.secondary < end_date)
            if not mask_primaries.any():
                continue
            pairs_primary = self[mask_primaries]

            # initialize a loop with the primary acquisition
            loop = [start_date]

            # find all loops for all primary acquisitions
            find_loops(
                self,
                loops,
                loop,
                pairs_primary,
                end_date,
                edge_pairs,
                max_acquisition,
            )
        from faninsar import Loops

        return Loops(loops)

    def to_matrix(self, dtype: DTypeLike = None) -> NDArray[np.number]:
        """Return the SBAS matrix.

        Parameters
        ----------
        matrix: np.ndarray
            SBAS matrix in shape of (n_pairs, n_dates-1). The dates between
            pairs are set to 1, otherwise 0.
        dtype: np.dtype, optional
            Data type of the matrix. Default is None.

        """
        matrix = np.zeros((len(self), len(self.dates) - 1), dtype=dtype)
        col_idxs = self.edge_index.copy()
        for row_idx, col_idx in enumerate(col_idxs):
            matrix[row_idx, col_idx[0] : col_idx[1]] = 1

        return matrix

    def parse_gaps(self, pairs_removed: Pairs | None = None) -> pd.DatetimeIndex:
        """Parse network gaps where the acquisitions are not connected by pairs.

        The gaps are detected by the dates that are not present in the secondary
        acquisition of the pairs.

        .. note::
            Theoretically, the gaps should be the temporal spans  (or intervals)
            between the consecutive acquisitions. For simplicity, the end dates
            of the gaps are returned here.

        Parameters
        ----------
        pairs_removed: Pairs, optional
            Pairs that are removed from the original pairs. Default is None,
            which means all pairs are used.

        Returns
        -------
        gaps : pd.DatetimeIndex
            Acquisition/date gaps that are not covered by any pairs.

        """
        dates = self.dates[1:]
        pairs_valid = self - pairs_removed if pairs_removed is not None else self

        dates_secondary = np.unique(pairs_valid.secondary)
        return np.setdiff1d(dates, dates_secondary)


class DateManager:
    # TODO: user defined period (using day of year, wrap into new year and cut into periods)
    def __init__(self) -> None:
        pass

    @staticmethod
    def season_of_month(month: int) -> int:
        """return the season of a given month

        Parameters
        ----------
        month: int
            Month of the year.

        Returns
        -------
        season: int
            Season of corresponding month:
                1 for spring,
                2 for summer,
                3 for fall,
                4 for winter.
        """
        month = int(month)
        if month not in list(range(1, 13)):
            raise ValueError(f"Month should be in range 1-12. But got '{month}'.")
        season = (month - 3) % 12 // 3 + 1
        return season

    @staticmethod
    def ensure_datetime(date: Any) -> datetime:
        """ensure the date is a datetime object

        Parameters
        ----------
        date: datetime or str
            Date to be ensured.

        Returns
        -------
        date: datetime
            Date with format of datetime.
        """
        if isinstance(date, datetime):
            pass
        elif isinstance(date, str):
            date = pd.to_datetime(date)
        else:
            raise TypeError(f"Date should be datetime or str, but got {type(date)}")
        return date

    @staticmethod
    def str_to_dates(
        date_str: str,
        length: Optional[int] = 2,
        parse_function: Optional[Callable] = None,
        date_args: dict = {},
    ):
        """convert date string to dates

        Parameters
        ----------
        date_str: str
            Date string containing dates.
        length: int, optional
            Length/number of dates in the date string. if 0, all dates in the
            date string will be used. Default is 2.
        parse_function: Callable, optional
            Function to parse the date strings from the date string.
            If None, the date string will be split by '_' and the
            last 2 items will be used. Default is None.
        date_args: dict, optional
            Keyword arguments for :func:`pd.to_datetime` to convert the date strings
            to datetime objects. For example, {'format': '%Y%m%d'}.
            Default is {}.
        """
        if parse_function is not None:
            dates = parse_function(date_str)
        else:
            items = date_str.split("_")
            if len(items) >= length:
                dates_ls = items[-length:]
            else:
                raise ValueError(
                    f"The number of dates in {date_str} is less than {length}."
                )

        date_args.update({"errors": "raise"})
        try:
            dates = [pd.to_datetime(i, **date_args) for i in dates_ls]
        except:
            raise ValueError(f"Dates in {date_str} not recognized.")

        return tuple(dates)
