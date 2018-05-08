from __future__ import absolute_import

import functools
import time
import typing as tp
from struct import pack

# noinspection PyProtectedMember
from . import logger
from ._webdriver import EyesScreenshot
from .errors import OutOfBoundsError
from .geometry import Region
from .target import Target
from .utils import general_utils

if tp.TYPE_CHECKING:
    from ._agent_connector import AgentConnector
    from ._webdriver import EyesWebElement, EyesWebDriver
    from .eyes import Eyes, ImageMatchSettings
    from .utils._custom_types import (Num, RunningSession, AppOutput,
                                      UserInputs, MatchResult, AnyWebDriver)


class MatchWindowTask(object):
    """
    Handles matching of output with the expected output (including retry and 'ignore mismatch' when needed).
    """
    _MATCH_INTERVAL = 0.5

    MINIMUM_MATCH_TIMEOUT = 60  # Milliseconds

    def __init__(self, eyes, agent_connector, running_session, driver, default_retry_timeout):
        # type: (Eyes, AgentConnector, RunningSession, AnyWebDriver, Num) -> None
        """
        Ctor.

        :param eyes: The Eyes instance which created this task.
        :param agent_connector: The agent connector to use for communication.
        :param running_session:  The current eyes session.
        :param driver: The webdriver for which the current session is run.
        :param default_retry_timeout: The default match timeout. (milliseconds)
        """
        self._eyes = eyes
        self._agent_connector = agent_connector
        self._running_session = running_session
        self._driver = driver
        self._default_retry_timeout = default_retry_timeout / 1000.0  # type: Num # since we want the time in seconds.
        self._screenshot = None  # type: EyesScreenshot

    def _get_screenshot(self, force_full_page_screenshot, wait_before_screenshots, element=None):
        # type: (bool, Num, tp.Optional[EyesWebElement]) -> EyesScreenshot
        seconds_to_wait = wait_before_screenshots / 1000.0

        if element:
            current_screenshot = self._driver.get_stitched_screenshot(element, seconds_to_wait)
            return EyesScreenshot.create_from_image(current_screenshot, self._driver)

        if force_full_page_screenshot:
            current_screenshot = self._driver.get_full_page_screenshot(seconds_to_wait)
            return EyesScreenshot.create_from_image(current_screenshot, self._driver)

        logger.debug("Waiting {} ms before taking screenshots...".format(wait_before_screenshots))
        time.sleep(seconds_to_wait)
        logger.debug('Finished waiting!')

        current_screenshot64 = self._driver.get_screenshot_as_base64()
        return EyesScreenshot.create_from_base64(current_screenshot64, self._driver)

    @staticmethod
    def _create_match_data_bytes(app_output,  # type: AppOutput
                                 user_inputs,  # type: UserInputs
                                 tag,  # type: tp.Text
                                 ignore_mismatch,  # type: bool
                                 screenshot,  # type: EyesScreenshot
                                 default_match_settings,  # type: ImageMatchSettings
                                 target=None,  # type: Target
                                 ignore=None,  # type: tp.Optional[tp.List]
                                 floating=None,  # type: tp.Optional[tp.List]
                                 ):
        # type: (...) -> bytes
        if target is None:
            target = Target()  # Use defaults
        if ignore is None:
            ignore = []
        if floating is None:
            floating = []

        match_data = {
            "IgnoreMismatch": ignore_mismatch,
            "Options": {
                "Name": tag,
                "UserInputs": user_inputs,
                "ImageMatchSettings": {
                    "MatchLevel": default_match_settings.match_level,
                    "IgnoreCaret": target.get_ignore_caret(),
                    "Exact": default_match_settings.exact_settings,
                    "Ignore": ignore,
                    "Floating": floating
                },
                "IgnoreMismatch": ignore_mismatch,
                "Trim": {
                    "Enabled": False
                }
            },
            "UserInputs": user_inputs,
            "AppOutput": app_output,
            "tag": tag
        }
        match_data_json_bytes = general_utils.to_json(match_data).encode('utf-8')
        match_data_size_bytes = pack(">L", len(match_data_json_bytes))
        screenshot_bytes = screenshot.get_bytes()
        body = match_data_size_bytes + match_data_json_bytes + screenshot_bytes
        return body

    @staticmethod
    def _get_dynamic_regions(target, driver, eyes_screenshot):
        # type: (tp.Optional[Target], EyesWebDriver, EyesScreenshot) -> tp.Dict[str, tp.List[tp.Optional[Region]]]
        ignore = []  # type: tp.List[Region]
        floating = []  # type: tp.List[Region]
        if target is not None:
            for region_wrapper in target.ignore_regions:
                try:
                    current_region = region_wrapper.get_region(driver, eyes_screenshot)
                    ignore.append(current_region)
                except OutOfBoundsError as err:
                    logger.info("WARNING: Region specified by {} is out of bounds! {}".format(region_wrapper, err))
            for floating_wrapper in target.floating_regions:
                try:
                    current_floating = floating_wrapper.get_region(driver, eyes_screenshot)
                    floating.append(current_floating)
                except OutOfBoundsError as err:
                    logger.info("WARNING: Floating region specified by {} is out of bounds! {}".format(floating_wrapper,
                                                                                                       err))
        return {"ignore": ignore, "floating": floating}

    def _prepare_match_data_for_window(self, tag,  # type: tp.Text
                                       force_full_page_screenshot,  # type: bool
                                       user_inputs,  # type: UserInputs
                                       wait_before_screenshots,  # type: Num
                                       default_match_settings,  # type: ImageMatchSettings
                                       target,  # type: Target
                                       ignore_mismatch=False):
        # type: (...) -> bytes
        title = self._eyes.get_title()
        self._screenshot = self._get_screenshot(force_full_page_screenshot, wait_before_screenshots)
        dynamic_regions = MatchWindowTask._get_dynamic_regions(target, self._driver, self._screenshot)
        app_output = {'title': title, 'screenshot64': None}  # type: AppOutput
        return self._create_match_data_bytes(app_output, user_inputs, tag, ignore_mismatch,
                                             self._screenshot, default_match_settings, target,
                                             dynamic_regions['ignore'], dynamic_regions['floating'])

    def _prepare_match_data_for_region(self, region,  # type: Region
                                       tag,  # type: tp.Text
                                       force_full_page_screenshot,  # type: bool
                                       user_inputs,  # type: UserInputs
                                       wait_before_screenshots,  # type: Num
                                       default_match_settings,  # type: ImageMatchSettings
                                       target,  # type: Target
                                       ignore_mismatch=False):
        # type: (...) -> bytes
        title = self._eyes.get_title()
        self._screenshot = self._get_screenshot(force_full_page_screenshot, wait_before_screenshots)
        self._screenshot = self._screenshot.get_sub_screenshot_by_region(region)
        dynamic_regions = MatchWindowTask._get_dynamic_regions(target, self._driver, self._screenshot)
        app_output = {'title': title, 'screenshot64': None}  # type: AppOutput
        return self._create_match_data_bytes(app_output, user_inputs, tag, ignore_mismatch,
                                             self._screenshot, default_match_settings, target,
                                             dynamic_regions['ignore'], dynamic_regions['floating'])

    def _prepare_match_data_for_element(self, element,  # type: EyesWebElement
                                        tag,  # type: tp.Text
                                        force_full_page_screenshot,  # type: bool
                                        user_inputs,  # type: UserInputs
                                        wait_before_screenshots,  # type: Num
                                        default_match_settings,  # type: ImageMatchSettings
                                        target,  # type: Target
                                        stitch_content=False,
                                        ignore_mismatch=False):
        # type: (...) -> bytes
        title = self._eyes.get_title()

        if stitch_content:
            self._screenshot = self._get_screenshot(force_full_page_screenshot, wait_before_screenshots, element)
        else:
            self._screenshot = self._get_screenshot(force_full_page_screenshot, wait_before_screenshots)
            self._screenshot = self._screenshot.get_sub_screenshot_by_element(element)

        dynamic_regions = MatchWindowTask._get_dynamic_regions(target, self._driver, self._screenshot)
        app_output = {'title': title, 'screenshot64': None}  # type: AppOutput
        return self._create_match_data_bytes(app_output, user_inputs, tag, ignore_mismatch,
                                             self._screenshot, default_match_settings, target,
                                             dynamic_regions['ignore'], dynamic_regions['floating'])

    def _run_with_intervals(self, prepare_action, retry_timeout):
        # type: (tp.Callable, Num) -> MatchResult
        """
        Includes retries in case the screenshot does not match.
        """
        logger.debug('Matching with intervals...')
        # We intentionally take the first screenshot before starting the timer, to allow the page
        # just a tad more time to stabilize.
        data = prepare_action(ignore_mismatch=True)
        # Start the timer.
        start = time.time()
        logger.debug('First match attempt...')
        as_expected = self._agent_connector.match_window(self._running_session, data)
        if as_expected:
            return {"as_expected": True, "screenshot": self._screenshot}
        retry = time.time() - start
        logger.debug("Failed. Elapsed time: {0:.1f} seconds".format(retry))
        while retry < retry_timeout:
            logger.debug('Matching...')
            time.sleep(self._MATCH_INTERVAL)
            data = prepare_action(ignore_mismatch=True)
            as_expected = self._agent_connector.match_window(self._running_session, data)
            if as_expected:
                return {"as_expected": True, "screenshot": self._screenshot}
            retry = time.time() - start
            logger.debug("Elapsed time: {0:.1f} seconds".format(retry))
        # One last try
        logger.debug('One last matching attempt...')
        data = prepare_action()
        as_expected = self._agent_connector.match_window(self._running_session, data)
        return {"as_expected": as_expected, "screenshot": self._screenshot}

    def _run(self, prepare_action, run_once_after_wait=False, retry_timeout=-1):
        # type: (tp.Callable, bool, Num) -> MatchResult
        if 0 < retry_timeout < MatchWindowTask.MINIMUM_MATCH_TIMEOUT:
            raise ValueError("Match timeout must be at least 60ms, got {} instead.".format(retry_timeout))
        if retry_timeout < 0:
            retry_timeout = self._default_retry_timeout
        else:
            retry_timeout /= 1000.0
        logger.debug("Match timeout set to: {0} seconds".format(retry_timeout))
        start = time.time()
        if run_once_after_wait or retry_timeout == 0:
            logger.debug("Matching once...")
            # If the load time is 0, the sleep would immediately return anyway.
            time.sleep(retry_timeout)
            data = prepare_action()
            as_expected = self._agent_connector.match_window(self._running_session, data)
            result = {"as_expected": as_expected, "screenshot": self._screenshot}  # type: MatchResult
        else:
            result = self._run_with_intervals(prepare_action, retry_timeout)
        logger.debug("Match result: {0}".format(result["as_expected"]))
        elapsed_time = time.time() - start
        logger.debug("_run(): Completed in {0:.1f} seconds".format(elapsed_time))
        return result

    def match_window(self, retry_timeout,  # type: Num
                     tag,  # type: str
                     force_full_page_screenshot,  # type: bool
                     user_inputs,  # UserInputs
                     wait_before_screenshots,  # type: Num
                     default_match_settings,  # type: ImageMatchSettings
                     target,  # type: tp.Optional[Target]
                     run_once_after_wait=False,
                     ):
        # type: (...) -> MatchResult
        """
        Performs a match for the window.

        :param retry_timeout: Amount of time until it retries.
        :param tag: The name of the tag (optional).
        :param force_full_page_screenshot: Whether or not force full page screenshot.
        :param user_inputs: The user input.
        :param wait_before_screenshots: Milliseconds to wait before taking each screenshot.
        :param default_match_settings: The default match settings for the session.
        :param target: The target of the check_window call.
        :param run_once_after_wait: Whether or not to run again after waiting.
        :return: The result of the run.
        """
        prepare_action = functools.partial(self._prepare_match_data_for_window, tag,
                                           force_full_page_screenshot, user_inputs, wait_before_screenshots,
                                           default_match_settings, target)
        return self._run(prepare_action, run_once_after_wait, retry_timeout)

    def match_region(self, region,  # type: Region
                     retry_timeout,  # type: Num
                     tag,  # type: tp.Text
                     force_full_page_screenshot,  # type: bool
                     user_inputs,  # type: UserInputs
                     wait_before_screenshots,  # type: Num
                     default_match_settings,  # type: ImageMatchSettings
                     target,  # type: tp.Optional[Target]
                     run_once_after_wait=False):
        # type: (...) -> MatchResult
        """
        Performs a match for a given region.

        :param region: The region to run the match with.
        :param retry_timeout: Amount of time until it retries.
        :param tag: The name of the tag (optional).
        :param force_full_page_screenshot: Whether or not force full page screenshot.
        :param user_inputs: The user input.
        :param wait_before_screenshots: Milliseconds to wait before taking each screenshot.
        :param default_match_settings: The default match settings for the session.
        :param target: The target of the check_window call.
        :param run_once_after_wait: Whether or not to run again after waiting.
        :return: The result of the run.
        """
        stitch_content = False
        prepare_action = functools.partial(self._prepare_match_data_for_region, region, tag,
                                           force_full_page_screenshot, user_inputs, wait_before_screenshots,
                                           default_match_settings, target, stitch_content)
        return self._run(prepare_action, run_once_after_wait, retry_timeout)

    def match_element(self, element,  # type: EyesWebElement
                      retry_timeout,  # type: Num
                      tag,  # type: tp.Text
                      force_full_page_screenshot,  # type: bool
                      user_inputs,  # type: UserInputs
                      wait_before_screenshots,  # type: Num
                      default_match_settings,  # type: ImageMatchSettings
                      target,  # type: tp.Optional[Target]
                      run_once_after_wait=False,
                      stitch_content=False):
        # type: (...) -> MatchResult
        """
        Performs a match for a given element.

        :param element: The element to run the match with.
        :param retry_timeout: Amount of time until it retries.
        :param tag: The name of the tag (optional).
        :param force_full_page_screenshot: Whether or not force full page screenshot.
        :param user_inputs: The user input.
        :param wait_before_screenshots: Milliseconds to wait before taking each screenshot.
        :param default_match_settings: The default match settings for the session.
        :param target: The target of the check_window call.
        :param run_once_after_wait: Whether or not to run again after waiting.
        :return: The result of the run.
        """
        prepare_action = functools.partial(self._prepare_match_data_for_element, element,
                                           tag, force_full_page_screenshot, user_inputs, wait_before_screenshots,
                                           default_match_settings, target, stitch_content)
        return self._run(prepare_action, run_once_after_wait, retry_timeout)
