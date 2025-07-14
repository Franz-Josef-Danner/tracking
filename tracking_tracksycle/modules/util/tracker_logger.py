"""Simple logger utility for Kaiserlich Tracksycle."""

from __future__ import annotations

import logging

LOGGER_NAME = "Tracksycle"


def configure_logger(debug: bool = False) -> logging.Logger:
    """Configure the Tracksycle logger once.

    Parameters
    ----------
    debug : bool, optional
        Whether debug level logging should be enabled, by default ``False``.

    Returns
    -------
    :class:`logging.Logger`
        The configured logger instance.
    """

    logger = logging.getLogger(LOGGER_NAME)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('[Tracksycle] %(message)s'))
        logger.addHandler(handler)

    return logger


class TrackerLogger:
    """Wrapper around :mod:`logging` for convenience."""

    def __init__(self):
        self._logger = logging.getLogger(LOGGER_NAME)

    def info(self, msg):
        self._logger.info(msg)

    def warn(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)

    def debug(self, msg):
        self._logger.debug(msg)

