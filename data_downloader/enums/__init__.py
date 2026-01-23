from __future__ import annotations

from enum import Enum, auto
from typing import Any

from typing_extensions import Self

from data_downloader.logging import setup_logger

logger = setup_logger(__name__)


class StrEnum(str, Enum):
    """A string enum class.

    This class is used to support StrEnum before Python 3.11.
    """

    _value_: str

    def __new__(cls, value: str | auto, *args: Any, **kwargs: Any) -> Self:
        """Create a new StrEnum member."""
        if not isinstance(value, (str, auto)):
            msg = "Values of StrEnums must be strings: %r is a %s"
            logger.error(msg, value, type(value))
            raise TypeError(msg % (value, type(value)))
        return super().__new__(cls, value, *args, **kwargs)

    def __str__(self) -> str:
        """Return the string representation of the enum value."""
        return str(self.value)

    @staticmethod
    def _generate_next_value_(
        name: str,
        *args: Any,
        **kwargs: Any,  # noqa: ARG004
    ) -> str:
        return name


class BaseConstants(StrEnum):
    """Base class for constants."""

    @classmethod
    def variables(cls) -> list[str]:
        """All available variables."""
        return list(cls.__members__.keys())
