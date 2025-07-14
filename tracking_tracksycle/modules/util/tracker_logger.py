"""Simple logger utility for Kaiserlich Tracksycle."""

import logging


class TrackerLogger:
    def __init__(self, debug=False):
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='[Tracksycle] %(message)s')
        self._logger = logging.getLogger('Tracksycle')

    def info(self, msg):
        self._logger.info(msg)

    def warn(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)

    def debug(self, msg):
        self._logger.debug(msg)

