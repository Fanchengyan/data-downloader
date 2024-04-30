"""This module provides the Pair and Pairs classes to handle pairs of InSAR data.
``Pair`` and ``Pairs`` class are modified from the FanInSAR package.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Callable, Literal, Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray


class Pair:
    """Pair class for one pair."""

    _values: np.ndarray
    _name: str
    _days: int

    __slots__ = ["_values", "_name", "_days"]

    def __init__(
        self,
        pair: Iterable[datetime, datetime],
    ) -> None:
        """
        Parameters
        ----------
        pair: Iterable
            Iterable object of two dates. Each date is a datetime object.
            For example, (date1, date2).
        """
        self._values = np.sort(pair).astype("M8[D]")
        self._name = "_".join([i.strftime("%Y%m%d") for i in self._values.astype("O")])
        self._days = (self._values[1] - self._values[0]).astype(int)

    def __str__(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"Pair({self._name})"

    def __eq__(self, other: "Pair") -> bool:
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self._name)

    def __array__(self, dtype=None) -> np.ndarray:
        return np.asarray(self._values, dtype=dtype)

    @property
    def values(self) -> NDArray[np.datetime64]:
        """the values of the pair with format of datetime."""
        return self._values

    @property
    def name(self) -> str:
        """String of the pair with format of '%Y%m%d_%Y%m%d'."""
        return self._name

    @property
    def days(self) -> int:
        """the time span of the pair in days."""
        return self._days

    @property
    def primary(self) -> np.datetime64:
        """the primary dates of all pairs"""
        return self.values[0]

    @property
    def secondary(self) -> np.datetime64:
        """the secondary dates of all pairs"""
        return self.values[1]

    def primary_string(self, date_format="%Y%m%d") -> str:
        """return the primary dates of all pairs in string format

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.
        """
        return pd.to_datetime(self.values[0]).strftime(date_format)

    def secondary_string(self, date_format="%Y%m%d") -> str:
        """return the secondary dates of all pairs in string format

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
        parse_function: Optional[Callable] = None,
        date_args: dict = {},
    ) -> "Pair":
        """initialize the pair class from a pair name

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
        dates = DateManager.str_to_dates(name, 2, parse_function, date_args)
        return cls(dates)


class Pairs:
    """Pairs class to handle pairs

    Examples
    --------
    prepare dates and pairs for examples:

    >>> dates = pd.date_range('20130101', '20231231').values
    >>> n = len(dates)
    >>> pair_ls = []
    >>> loop_ls = []
    >>> for i in range(5):
    ...    np.random.seed(i)
    ...    pair_ls.append(dates[np.random.randint(0, n, 2)])

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

    >>> pairs1 = pairs['2018-03-09':]
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

    __slots__ = ["_values", "_dates", "_length", "_edge_index", "_names"]

    def __init__(
        self,
        pairs: Iterable[Iterable[datetime, datetime]] | Iterable[Pair],
        sort: bool = True,
    ) -> None:
        """initialize the pairs class


        Parameters
        ----------
        pairs: Iterable
            Iterable object of pairs. Each pair is an Iterable or Pair
            object of two dates with format of datetime. For example,
            [(date1, date2), ...].
        sort: bool, optional
            Whether to sort the pairs. Default is True.
        """
        if pairs is None or len(pairs) == 0:
            raise ValueError("pairs cannot be None.")

        _values = np.array(pairs, dtype="M8[D]")

        self._values = _values
        self._parse_pair_meta()

        if sort:
            self.sort(inplace=True)

    def _parse_pair_meta(self):
        self._dates = np.unique(self._values.flatten())
        self._length = self._values.shape[0]
        self._edge_index = np.searchsorted(self._dates, self._values)
        self._names = self.to_names()

    def __len__(self) -> int:
        return self._length

    def __str__(self) -> str:
        return f"Pairs({self._length})"

    def __repr__(self) -> str:
        return self.to_frame().__repr__()

    def __eq__(self, other: "Pairs") -> bool:
        return np.array_equal(self.values, other.values)

    def __add__(self, other: "Pairs") -> "Pairs":
        _pairs = np.union1d(self.names, other.names)
        if len(_pairs) > 0:
            return Pairs.from_names(_pairs)

    def __sub__(self, other: "Pairs") -> "Pairs":
        _pairs = np.setdiff1d(self.names, other.names)
        if len(_pairs) > 0:
            return Pairs.from_names(_pairs)

    def __getitem__(self, index: int) -> "Pair" | "Pairs":
        if isinstance(index, slice):
            start, stop, step = index.start, index.stop, index.step
            if isinstance(start, (int, np.integer, type(None))) and isinstance(
                stop, (int, np.integer, type(None))
            ):
                if start is None:
                    start = 0
                if stop is None:
                    stop = self._length
                return Pairs(self._values[start:stop:step])
            elif isinstance(
                start, (datetime, np.datetime64, pd.Timestamp, str, type(None))
            ) and isinstance(
                stop, (datetime, np.datetime64, pd.Timestamp, str, type(None))
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
                    raise ValueError(
                        f"Index start {start} should be earlier than index stop {stop}."
                    )
                _pairs = []
                for pair in self._values:
                    pair = pair.astype("M8[s]")
                    if start <= pair[0] <= stop and start <= pair[1] <= stop:
                        _pairs.append(pair)
                if len(_pairs) > 0:
                    return Pairs(_pairs)
                else:
                    return None
        elif isinstance(index, (int, np.integer)):
            if index >= self._length:
                raise IndexError(
                    f"Index {index} out of range. Pairs number is {self._length}."
                )
            return Pair(self._values[index])
        elif isinstance(index, (datetime, np.datetime64, pd.Timestamp, str)):
            if isinstance(index, str):
                try:
                    index = pd.to_datetime(index)
                except:
                    raise ValueError(f"String {index} cannot be converted to datetime.")
            pairs = []
            for pair in self._values:
                if index in pair:
                    pairs.append(pair)
            if len(pairs) > 0:
                return Pairs(pairs)
            else:
                return None
        elif isinstance(index, Iterable):
            index = np.array(index)
            return Pairs(self._values[index])
        else:
            raise TypeError(
                "Index should be int, slice, datetime, str, or bool or int array"
                f" indexing, but got {type(index)}."
            )

    def __hash__(self) -> int:
        return hash("".join(self.names))

    def __iter__(self):
        pairs_ls = [Pair(i) for i in self._values]
        return iter(pairs_ls)

    def __contains__(self, item):
        if isinstance(item, Pair):
            item = item.values
        elif isinstance(item, str):
            item = Pair.from_name(item).values
        elif isinstance(item, Iterable):
            item = np.sort(item)
        else:
            raise TypeError(
                f"item should be Pair, str, or Iterable, but got {type(item)}."
            )

        return np.any(np.all(item == self.values, axis=1))

    def __array__(self, dtype=None) -> NDArray[np.datetime64]:
        return np.asarray(self._values, dtype=dtype)

    def _ensure_pairs(
        self, pairs: str | Pair | "Pairs" | Iterable[str] | Iterable[Pair]
    ) -> "Pairs":
        """ensure the pairs are in the Pairs object"""
        if isinstance(pairs, str):
            pairs = Pairs.from_names([pairs])
        elif isinstance(pairs, Pair):
            pairs = Pairs([pairs])
        elif isinstance(pairs, Pairs):
            return pairs
        elif isinstance(pairs, Iterable):
            pairs = np.asarray(pairs)
            if pairs.ndim == 1 and pairs.dtype == "O":
                pairs = Pairs.from_names(pairs)
            elif pairs.ndim == 2 and pairs.shape[1] == 2:
                pairs = Pairs(pairs)
            else:
                raise ValueError(
                    f"pairs should be 1D array of str, 2D array of datetime, or Pairs, but got {pairs}."
                )
        else:
            raise TypeError(
                f"pairs should be str, Pair, list of str, list of Pair, or Pairs, but got {type(pairs)}."
            )
        return pairs

    @property
    def values(self) -> NDArray[np.datetime64]:
        """return the numpy array of the pairs"""
        return self._values

    @property
    def names(self) -> NDArray[np.str_]:
        """return the names (string format) of the pairs"""
        return self._names

    @property
    def dates(self) -> pd.DatetimeIndex:
        """return the sorted dates array of all pairs in type of np.datetime64[D]"""
        return pd.to_datetime(self._dates)

    @property
    def days(self) -> NDArray[np.int64]:
        """return the time span of all pairs in days"""
        return (self._values[:, 1] - self._values[:, 0]).astype(int)

    @property
    def primary(self) -> pd.DatetimeIndex:
        """return the primary dates of all pairs"""
        return pd.to_datetime(self._values[:, 0])

    @property
    def secondary(self) -> pd.DatetimeIndex:
        """return the secondary dates of all pairs"""
        return pd.to_datetime(self._values[:, 1])

    def primary_string(self, date_format="%Y%m%d") -> pd.Index:
        """return the primary dates of all pairs in string format

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.
        """
        return self.primary.strftime(date_format)

    def secondary_string(self, date_format="%Y%m%d") -> pd.Index:
        """return the secondary dates of all pairs in string format

        Parameters
        ----------
        date_format: str
            Format of the date string. Default is '%Y%m%d'. See more at
            `strftime Format Codes <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes>`_.
        """
        return self.secondary.strftime(date_format)

    @property
    def edge_index(self) -> NDArray[np.int64]:
        """return the index of the pairs in the dates coordinate (edge index in
        graph theory)"""
        return self._edge_index

    @property
    def shape(self) -> tuple[int, int]:
        """return the shape of the pairs array"""
        return self._values.shape

    @classmethod
    def from_names(
        cls,
        names: Iterable[str],
        parse_function: Optional[Callable] = None,
        date_args: dict = {},
    ) -> "Pairs":
        """initialize the pair class from a pair name

        .. note::
            The pairs will be in the order of the input names. If you want to
            sort the pairs, you can call the :meth:`Pairs.sort()` method to
            achieve it.

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
        pairs: Pairs
            unsorted Pairs object.
        """
        pairs = []
        for name in names:
            pair = Pair.from_name(name, parse_function, date_args)
            pairs.append(pair.values)
        return cls(pairs, sort=False)

    def where(
        self,
        pairs: list[str] | list[Pair] | "Pairs",
        return_type: Literal["index", "mask"] = "index",
    ) -> Optional[NDArray[np.int64 | np.bool_]]:
        """return the index of the pairs

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.
        return_type: str, optional
            Whether to return the index or mask of the pairs. Default is 'index'.
        """
        pairs = self._ensure_pairs(pairs)
        con = np.isin(self.names, pairs.names)
        if return_type == "mask":
            return con
        elif return_type == "index":
            if np.any(con):
                return np.where(con)[0]
        else:
            raise ValueError(
                f"return_type should be one of ['index', 'mask'], but got {return_type}."
            )

    def intersect(self, pairs: list[str] | list[Pair] | "Pairs") -> Optional["Pairs"]:
        """return the intersection of the pairs. The pairs both in self and
        input pairs.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.
        """
        pairs = self._ensure_pairs(pairs)
        return self[self.where(pairs)]

    def union(self, pairs: list[str] | list[Pair] | "Pairs") -> "Pairs":
        """return the union of the pairs. All pairs that in self and input pairs.
        A more robust operation than addition.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.
        """
        pairs = self._ensure_pairs(pairs)
        return self + pairs

    def difference(self, pairs: list[str] | list[Pair] | "Pairs") -> Optional["Pairs"]:
        """return the difference of the pairs. The pairs in self but not in pairs.
        A more robust operation than subtraction.

        Parameters
        ----------
        pairs: list of str or Pair, or Pairs
            Pair names or Pair objects, or Pairs object.
        """
        pairs = self._ensure_pairs(pairs)
        return self - pairs

    def copy(self) -> "Pairs":
        """return a copy of the pairs"""
        return Pairs(self._values.copy())

    def sort(
        self,
        order: list | Literal["pairs", "primary", "secondary", "days"] = "pairs",
        ascending: bool = True,
        inplace: bool = True,
    ) -> Optional[tuple["Pairs", NDArray[np.int64]]]:
        """sort the pairs

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
        item_map = {
            "pairs": self._values,
            "primary": self._values[:, 0],
            "secondary": self._values[:, 1],
            "days": self.days,
        }
        if isinstance(order, str):
            order = [order]
        _values_ = []
        for i in order:
            if i not in item_map.keys():
                raise ValueError(
                    f"order should be one of {list(item_map.keys())}, but got {order}."
                )
            _values_.append(item_map[i].reshape(self._length, -1))
        _values_ = np.hstack(_values_)
        _values, _index = np.unique(_values_, axis=0, return_index=True)
        if not ascending:
            _index = _index[::-1]
        if inplace:
            self._values = _values
            self._parse_pair_meta()
        else:
            return Pairs(_values), _index

    def to_names(self, prefix: Optional[str] = None) -> NDArray[np.str_]:
        """generate pairs names string with prefix

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

        return names.values

    def to_frame(self) -> pd.DataFrame:
        """return the pairs as a DataFrame"""
        return pd.DataFrame(self._values, columns=["primary", "secondary"])

    def to_matrix(self, dtype=None) -> NDArray[np.number]:
        """return the SBAS matrix

        Parameters
        ----------
        matrix: np.ndarray
            SBAS matrix in shape of (n_pairs, n_dates-1). The dates between
            pairs are set to 1, otherwise 0.
        """
        matrix = np.zeros((len(self), len(self.dates) - 1), dtype=dtype)
        col_idxs = self.edge_index.copy()
        for row_idx, col_idx in enumerate(col_idxs):
            matrix[row_idx, col_idx[0] : col_idx[1]] = 1

        return matrix


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
            raise ValueError("Month should be in range 1-12." f" But got '{month}'.")
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
