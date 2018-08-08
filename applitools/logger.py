"""
Logs handling.
"""
from __future__ import absolute_import

import os
import sys
import logging
import functools
import datetime as dt
import typing as tp

if tp.TYPE_CHECKING:
    from ._webdriver import EyesScreenshot
    from .geometry import Region
    from .utils._image_utils import PngImage


def _parse_logger_level(logger_level):
    # type: (tp.Union[str, int]) -> int
    """
    Adapt logger params to logging library
    """
    try:
        return int(logger_level)
    except ValueError:
        levels = {'INFO': 20, 'DEBUG': 10}
        return levels.get(logger_level.strip())

_DEFAULT_EYES_LOGGER_NAME = 'eyes'
_DEFAULT_EYES_FORMATTER = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
_DEFAULT_LOGGER_LEVEL = _parse_logger_level(os.environ.get('LOGGER_LEVEL', logging.INFO))
_DEBUG_SCREENSHOT_PREFIX = os.environ.get('DEBUG_SCREENSHOT_PREFIX', 'screenshot_')
_DEBUG_SCREENSHOT_PATH = os.environ.get('DEBUG_SCREENSHOT_PATH', '.')


class _Logger(object):
    """
    Simple logger. Supports only info and debug.
    """

    def __init__(self, name=__name__, level=_DEFAULT_LOGGER_LEVEL, handler_factory=lambda: None,
                 formatter=None):
        # type: (tp.Text, int, tp.Callable, logging.Formatter) -> None
        """
        Ctor.

        :param name: The logger name.
        :param level: The log level (e.g., logging.DEBUG).
        :param handler_factory: A callable which creates a handler object. We use a factory
                                    since the actual creation of the handler should occur in open.
        :param formatter: A custom formatter for the logs.
        """
        self._name = name
        self._logger = None
        # Setting handler (a logger must have at least one handler attached to it)
        self._handler_factory = handler_factory
        self._handler = None
        self._formatter = formatter
        self._level = level

    def open(self):
        # type: () -> None
        """
        Open a handler.
        """
        # Actually create the handler
        self._handler = self._handler_factory()
        if self._handler:
            self._handler.setLevel(self._level)
            # Getting the logger
            self._logger = logging.getLogger(self._name)
            self._logger.setLevel(self._level)
            # Setting formatter
            if self._formatter is not None:
                self._handler.setFormatter(self._formatter)
            self._logger.addHandler(self._handler)

    def close(self):
        # type: () -> None
        """
        Close a handler.
        """
        if self._logger:
            self._handler.close()
            # If we don't remove the handler and a call to logging.getLogger(...) will be made with
            # the same name as the current logger, the handler will remain.
            self._logger.removeHandler(self._handler)
            self._logger = None
            self._handler = None

    def info(self, msg):
        # type: (tp.Text) -> None
        """
        Writes info level msg to the logger.

        :param msg: The message that will be written to the logger.
        """
        if self._logger:
            self._logger.info(msg)

    def debug(self, msg):
        # type: (tp.Text) -> None
        """
        Writes debug level msg to the logger.

        :param msg: The message that will be written to the logger.
        """
        if self._logger:
            self._logger.debug(msg)

    def warning(self, msg):
        # type: (tp.Text) -> None
        """
        Writes warning level msg to the logger.

        :param msg: The message that will be written to the logger.
        """
        if self._logger:
            self._logger.warning(msg)


class StdoutLogger(_Logger):
    """
    A simple logger class for printing to STDOUT.
    """

    def __init__(self, name=_DEFAULT_EYES_LOGGER_NAME, level=_DEFAULT_LOGGER_LEVEL):
        # type: (tp.Text, int) -> None
        """
        Ctor.

        :param name: The logger name.
        :param level: The log level (default is logging.DEBUG).
        """
        handler_factory = functools.partial(logging.StreamHandler, sys.stdout)
        super(StdoutLogger, self).__init__(name, level, handler_factory, _DEFAULT_EYES_FORMATTER)


class FileLogger(_Logger):
    """
    A simple logger class for outputting log messages to a file
    """

    def __init__(self, filename="eyes.log", mode='a', encoding=None, delay=0,
                 name=_DEFAULT_EYES_LOGGER_NAME, level=_DEFAULT_LOGGER_LEVEL):
        """
        Ctor.

        :param filename: The name of this file to which logs should be written.
        :param mode: The mode in which the log file is opened ('a' for appending, 'w' for overwrite).
        :param encoding: The encoding in which logs will be written to the file.
        :param delay: If True, file will not be opened until the first log message is emitted.
        :param name: The logger name.
        :param level: The log level (e.g., logging.DEBUG)
        """
        handler_factory = functools.partial(logging.FileHandler, filename, mode, encoding, delay)
        super(FileLogger, self).__init__(name, level, handler_factory, _DEFAULT_EYES_FORMATTER)


class NullLogger(_Logger):
    """
    A simple logger class which does nothing (log messages are ignored).
    """

    def __init__(self, name=_DEFAULT_EYES_LOGGER_NAME, level=_DEFAULT_LOGGER_LEVEL):
        """
        Ctor.

        :param name: The logger name.
        :param level: The log level (e.g., logging.DEBUG).
        """
        super(NullLogger, self).__init__(name, level)


# This will be set by the user.
_logger_to_use = None  # type: tp.Optional[_Logger]
# Holds the actual logger after open is called.
_logger = None  # type: tp.Optional[_Logger]


def set_logger(logger=None):
    # type: (tp.Optional[_Logger]) -> None
    """
    Sets the used logger to the logger.

    :param logger: The logger to use.
    """
    global _logger_to_use
    _logger_to_use = logger


def open_():
    # type: () -> None
    """
    Opens a new logger.
    """
    global _logger
    _logger = _logger_to_use
    if _logger is not None:
        _logger.open()


def close():
    # type: () -> None
    """
    Closed the logger.
    """
    global _logger
    if _logger is not None:
        _logger.close()
        _logger = None


def info(msg):
    # type: (tp.Text) -> None
    """
    Writes info level msg to the logger.

    :param msg: The message that will be written to the log.
    """
    if _logger is not None:
        _logger.info(msg)


def debug(msg):
    # type: (tp.Text) -> None
    """
    Writes debug level msg to the logger.

    :param msg: The message that will be written to the log.
    """
    if _logger is not None:
        _logger.debug(msg)


def warning(msg):
    # type: (tp.Text) -> None
    """
    Writes info level msg to the logger.

    :param msg: The message that will be written to the log.
    """
    if _logger is not None:
        _logger.warning(msg)


def save_screenshot(image, suffix, region=None):
    # type: (tp.Union[PngImage, EyesScreenshot], tp.Text, tp.Optional[Region]) -> None
    """
    A debug screenshot provider for saving screenshots to file.
    """
    if _logger and _logger._level == logging.DEBUG:
        from ._webdriver import EyesScreenshot
        if isinstance(image, EyesScreenshot):
            image = image._screenshot

        if region:
            suffix = 'part-{suffix}-{left}_{top}_{width}x{height}'.format(
                suffix=suffix, left=region.left, top=region.top,
                width=region.width, height=region.height
            )
        filename = '{prefix}_{timestamp}_{suffix}.png'.format(prefix=_DEBUG_SCREENSHOT_PREFIX,
                                                              timestamp=dt.datetime.now().time(),
                                                              suffix=suffix)
        full_path = os.path.join(_DEBUG_SCREENSHOT_PATH, filename)
        debug('Save screenshot: {}'.format(full_path))
        image.save_image(full_path)
