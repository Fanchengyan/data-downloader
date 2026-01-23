"""Netrc class."""

from __future__ import annotations

from netrc import netrc
from pathlib import Path
from typing import TYPE_CHECKING

from .logging import setup_logger

if TYPE_CHECKING:
    from os import PathLike


logger = setup_logger(__name__)


class Netrc(netrc):
    """A class managing records in .netrc file.

    Parameters
    ----------
    file : str | PathLike | None
        The .netrc file path. If None, use the default ~/.netrc file.

    """

    def __init__(self, file: str | PathLike | None = None) -> None:
        """Initialize Netrc object."""
        file = Path("~/.netrc").expanduser() if file is None else Path(file)
        self.file = file
        if not file.exists():
            self.file.open("w", encoding="utf-8").close()

        super().__init__(file)

    def _info_to_file(self) -> None:
        rep = repr(self)
        Path(self.file).write_text(rep, encoding="utf-8")

    def _update_info(self) -> None:
        with Path(self.file).open(encoding="utf-8") as fp:
            self._parse(str(self.file), fp, False)

    def add(
        self,
        host: str,
        login: str,
        password: str,
        account: str | None = None,
        overwrite: bool = False,
    ) -> None:
        """Add a record.

        Will do nothing if host exists in .netrc file unless set overwrite=True
        """
        if host in self.hosts and not overwrite:
            logger.warning(
                ">>> Warning: %s existed, nothing will be done. If you want to "
                "overwrite the existed record, set overwrite=True",
                host,
            )
        else:
            self.hosts.update({host: (login, account, password)})
            self._info_to_file()
            self._update_info()

    def remove(self, host: str) -> None:
        """Remove a record by host."""
        self.hosts.pop(host)
        self._info_to_file()
        self._update_info()

    def clear(self) -> None:
        """Remove all records."""
        self.hosts = {}
        self._info_to_file()
        self._update_info()
