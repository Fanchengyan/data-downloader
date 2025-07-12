from __future__ import annotations

from enum import Enum, auto

from typing_extensions import Self

from data_downloader.logging import setup_logger

logger = setup_logger(__name__)


class StrEnum(str, Enum):
    """A string enum class.

    This class is used to support StrEnum before Python 3.11.
    """

    _value_: str

    def __new__(cls, value: str | auto, *args, **kwargs) -> Self:
        if not isinstance(value, (str, auto)):
            msg = f"Values of StrEnums must be strings: {value!r} is a {type(value)}"
            logger.error(msg)
            raise TypeError(msg)
        return super().__new__(cls, value, *args, **kwargs)

    def __str__(self) -> str:
        return str(self.value)

    @staticmethod
    def _generate_next_value_(name: str, *args, **kwargs) -> str:
        return name


class BaseConstants(StrEnum):
    @classmethod
    def variables(cls) -> list[str]:
        """all available variables"""
        return list(cls.__members__.keys())

