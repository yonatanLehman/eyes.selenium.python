"""
Pytest configuration

pytest |-n|--platform|--browser|--headless

Example of usage:
    pytest -n 5     # run tests on all supported platforms in 5 thread
    pytest --platform 'iPhone 10.0'  # run tests only for iPhone 10.0 platform in one thread
    pytest --platform 'Linux' --browser firefox    # run all tests on Linux platform with firefox browser
    pytest --browser firefox    # run all tests on your current platform with firefox browser
    pytest --browser firefox --headless 1   # run all tests on your current platform with firefox browser in headless mode
"""
import os
import sys

import pytest
from applitools.utils import iteritems

from selenium import webdriver

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.remote_connection import RemoteConnection

from applitools.__version__ import __version__
from applitools.core import logger, StdoutLogger
from applitools.selenium import Eyes, EyesWebDriver, eyes_selenium_utils

from .platfroms import SUPPORTED_PLATFORMS, SUPPORTED_PLATFORMS_DICT

logger.set_logger(StdoutLogger())


@pytest.fixture(scope="function")
def eyes(request):
    # TODO: allow to setup logger level through pytest option
    # logger.set_logger(StdoutLogger())
    eyes = Eyes()
    eyes.hide_scrollbars = True

    # configure eyes options through @pytest.mark.eyes() marker
    eyes_mark_opts = request.node.get_closest_marker('eyes')
    eyes_mark_opts = eyes_mark_opts.kwargs if eyes_mark_opts else {}

    # configure eyes through @pytest.mark.parametrize('eyes', [])
    eyes_parametrized_opts = getattr(request, 'param', {})
    if set(eyes_mark_opts.keys()).intersection(eyes_parametrized_opts):
        raise ValueError("Eyes options conflict. The values from .mark.eyes and .mark.parametrize shouldn't intersect.")

    eyes_mark_opts.update(eyes_parametrized_opts)
    for key, val in iteritems(eyes_mark_opts):
        setattr(eyes, key, val)

    yield eyes
    eyes.abort_if_not_closed()


@pytest.fixture(scope="function")
def eyes_open(request, eyes, driver):
    test_page_url = request.node.get_closest_marker('test_page_url').args[-1]

    viewport_size = request.node.get_closest_marker('viewport_size')
    viewport_size = viewport_size.args[-1] if viewport_size else None

    test_suite_name = request.node.get_closest_marker('test_suite_name')
    test_suite_name = test_suite_name.args[-1] if test_suite_name else 'Python SDK'

    # use camel case in method name for fit java sdk tests name
    test_name = request.function.__name__.title().replace('_', '')

    if eyes.force_full_page_screenshot:
        test_suite_name += ' - ForceFPS'
        test_name += '_FPS'
    driver = eyes.open(driver, test_suite_name, test_name,
                       viewport_size=viewport_size)
    driver.get(test_page_url)

    yield eyes, driver
    results = eyes.close()
    print(results)


@pytest.fixture(scope="function")
def eyes_for_class(request, eyes_open):
    # TODO: implement eyes.setDebugScreenshotsPrefix("Java_" + testName + "_");

    eyes, driver = eyes_open
    request.cls.eyes = eyes
    request.cls.driver = driver
    yield


@pytest.fixture(scope="function")
def driver_for_class(request, driver):
    test_page_url = request.node.get_closest_marker('test_page_url').args[0]
    viewport_size = request.node.get_closest_marker('viewport_size').args[0]

    driver = EyesWebDriver(driver, None)
    if viewport_size:
        eyes_selenium_utils.set_browser_size(driver, viewport_size)
    request.cls.driver = driver

    driver.get(test_page_url)
    yield


@pytest.yield_fixture(scope='function')
def driver(request, browser_config):
    test_name = request.node.name
    build_tag = os.environ.get('BUILD_TAG', None)
    tunnel_id = os.environ.get('TUNNEL_IDENTIFIER', None)
    username = os.environ.get('SAUCE_USERNAME', None)
    access_key = os.environ.get('SAUCE_ACCESS_KEY', None)

    force_remote = request.config.getoption('remote')
    selenium_url = os.environ.get('SELENIUM_SERVER_URL', 'http://127.0.0.1:4444/wd/hub')
    if 'ondemand.saucelabs.com' in selenium_url or force_remote:
        selenium_url = "https://%s:%s@ondemand.saucelabs.com:443/wd/hub" % (username, access_key)
    logger.debug('SELENIUM_URL={}'.format(selenium_url))

    desired_caps = browser_config.copy()
    desired_caps['build'] = build_tag
    desired_caps['tunnelIdentifier'] = tunnel_id
    desired_caps['name'] = test_name

    executor = RemoteConnection(selenium_url, resolve_ip=False)
    browser = webdriver.Remote(command_executor=executor,
                               desired_capabilities=desired_caps)
    if browser is None:
        raise WebDriverException("Never created!")

    yield browser

    # report results
    try:
        browser.execute_script("sauce:job-result=%s" % str(not request.node.rep_call.failed).lower())
    except WebDriverException:
        # we can ignore the exceptions of WebDriverException type -> We're done with tests.
        logger.info('Warning: The driver failed to quit properly. Check test and server side logs.')
    finally:
        browser.quit()


def pytest_addoption(parser):
    parser.addoption("--platform", action="store")
    parser.addoption("--browser", action="store")
    parser.addoption("--headless", action="store")
    parser.addoption("--remote", action="store")


def _get_capabilities(platform_name=None, browser_name=None, headless=False):
    if platform_name is None:
        sys2platform_name = {
            'linux':  'Linux',
            'darwin': 'macOS 10.13',
            'win32':  'Windows 10'
        }
        platform_name = sys2platform_name[sys.platform]
    platform = SUPPORTED_PLATFORMS_DICT[platform_name]
    if platform.is_appium_based:
        capabilities = [platform.platform_capabilities()]
    else:
        if browser_name:
            return [platform.get_browser_capabilities(browser_name, headless)]
        capabilities = list(platform.browsers_capabilities(headless))
    return capabilities


def _setup_env_vars_for_session():
    import uuid
    python_version = os.environ.get('TRAVIS_PYTHON_VERSION', None)
    if not python_version:
        import platform
        python_version = platform.python_version()
    # setup environment variables once per test run if not settled up
    # needed for multi thread run
    os.environ['APPLITOOLS_BATCH_ID'] = os.environ.get('APPLITOOLS_BATCH_ID', str(uuid.uuid4()))
    os.environ['APPLITOOLS_BATCH_NAME'] = 'Python {} | SDK {} Tests'.format(python_version, __version__)


def pytest_generate_tests(metafunc):
    platform_name = metafunc.config.getoption('platform')
    browser_name = metafunc.config.getoption('browser')
    headless = metafunc.config.getoption('headless')

    _setup_env_vars_for_session()

    if platform_name or browser_name:
        desired_caps = _get_capabilities(platform_name, browser_name, headless)
    else:
        desired_caps = []
        platforms = getattr(metafunc.function, 'platform', [])
        if platforms:
            platforms = platforms.args

        for platform in SUPPORTED_PLATFORMS:
            if platform.name not in platforms:
                continue
            desired_caps.extend(_get_capabilities(platform.full_name, headless=headless))

    # update capabilities from capabilities marker
    if hasattr(metafunc, 'function'):
        func_capabilities = getattr(metafunc.function, 'capabilities', {})
        if func_capabilities:
            for caps in desired_caps:
                caps.update(func_capabilities.kwargs)

    # generate combinations of driver options before run
    if 'driver' in metafunc.fixturenames:
        metafunc.parametrize('browser_config',
                             desired_caps,
                             ids=_generate_param_ids(desired_caps),
                             scope='function')


def _generate_param_ids(desired_caps):
    results = []
    for caps in desired_caps:
        platform = caps.get('platform')
        browser = caps.get('browserName', '')
        if platform:
            browser_version = caps.get('version', '')
            browser += str(browser_version)
        else:
            platform = caps.get('platformName')
            platform_version = caps.get('version', '')
            platform += platform_version
        results.append('platform: {}, browser: {}'.format(platform, browser))
    return results


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # this sets the result as a test attribute for SauceLabs reporting.
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # set an report attribute for each phase of a call, which can
    # be "setup", "call", "teardown"
    setattr(item, "rep_" + rep.when, rep)


def pytest_runtest_setup(item):
    """Skip tests that not fit for selected platform"""
    platform_marker = item.get_closest_marker("platform")
    platform_cmd = item.config.getoption("platform")
    if platform_marker and platform_cmd:
        platforms = platform_marker.args
        cmd_platform = platform_cmd.split()[0]  # remove platform version
        if cmd_platform and cmd_platform not in platforms:
            pytest.skip("test requires platform %s" % cmd_platform)

    browser_marker = item.get_closest_marker("browser")
    browser_cmd = item.config.getoption("browser")
    if browser_marker and browser_cmd:
        browsers = browser_marker.args
        if browser_cmd and browser_cmd not in browsers:
            pytest.skip("test requires browser %s" % browser_cmd)
