"""Proxy management utilities for Kaiserlich Tracksycle."""

import bpy
import os
import time


def remove_existing_proxies(clip, logger=None):
    """Delete previously generated proxy files if they exist.

    Ensures ``clip.use_proxy_custom_directory`` is enabled so the
    proxy path is honored.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        MovieClip for which old proxies should be removed.
    logger : :class:`TrackerLogger`, optional
        Logger used for warning output.
    """

    # ensure proxy directory usage is enabled
    clip.use_proxy_custom_directory = True
    if not clip.proxy.directory:
        clip.proxy.directory = "//proxies"
    directory = clip.proxy.directory
    os.makedirs(bpy.path.abspath(directory), exist_ok=True)

    path = os.path.join(directory, "proxy_50.avi")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as exc:  # pylint: disable=broad-except
            if logger:
                logger.warn(f"Failed to remove existing proxy: {exc}")


def create_proxy_and_wait(clip, timeout=300, logger=None):
    """Create a 50% proxy and wait until the proxy file exists.

    Activates ``clip.use_proxy`` and ``clip.use_proxy_custom_directory`` so the
    proxy is generated in the configured directory.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        Movie clip for which the proxy should be generated.
    timeout : int, optional
        Maximum time to wait for the proxy in seconds.
    logger : :class:`TrackerLogger`, optional
        Logger used for debug output.
    """

    if clip is None:
        message = "No clip provided to create_proxy_and_wait"
        if logger:
            logger.error(message)
        else:
            print(f"ERROR: {message}")
        return False

    # enable proxies before generating them
    clip.use_proxy = True
    # ensure proxy directory usage is enabled
    clip.use_proxy_custom_directory = True
    if not clip.proxy.directory:
        if logger:
            logger.warn("Proxy directory was not set; using default '//proxies'")
        clip.proxy.directory = "//proxies"

    directory = bpy.path.abspath(clip.proxy.directory)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        message = f"Failed to create proxy directory: {directory} ({exc})"
        if logger:
            logger.error(message)
        else:
            print(f"ERROR: {message}")
        return False

    proxy_path = os.path.join(directory, "proxy_50.avi")

    # Enable proxy generation and set up building the proxy
    try:
        clip.proxy.build_50 = True
        # clip.proxy.build_proxy() gibt es so nicht – stattdessen ggf. durch Timer auf das File warten wie bisher
    except Exception as e:  # pylint: disable=broad-except
        if logger:
            logger.error(f"Proxy-Build-Setup fehlgeschlagen: {e}")
        else:
            print(f"ERROR: Proxy-Build-Setup fehlgeschlagen: {e}")
        return False

    if logger:
        logger.info(f"Waiting for proxy file: {proxy_path}")

    state = {"start": time.time()}

    def _wait_for_proxy():
        if os.path.exists(proxy_path):
            if logger:
                logger.info("Proxy file found.")
            return None
        elapsed = time.time() - state["start"]
        if elapsed > timeout:
            if logger:
                logger.error("Proxy creation timed out after 300 seconds.")
            return None
        if logger:
            logger.info(f"Proxy not found yet... {int(elapsed)}s elapsed")
        return 1.0

    bpy.app.timers.register(_wait_for_proxy)
    return True


def create_proxy_and_wait_async(clip, callback=None, timeout=300, logger=None):
    """Create a 50% proxy and run ``callback`` once it exists.

    This works like :func:`create_proxy_and_wait` but executes the
    provided ``callback`` after the proxy file was detected.  The
    function itself returns immediately after registering the timer.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        Movie clip for which the proxy should be generated.
    callback : callable, optional
        Function to run after the proxy has been created.  If ``None``
        no callback is executed.
    timeout : int, optional
        Maximum time to wait for the proxy in seconds.
    logger : :class:`TrackerLogger`, optional
        Logger used for debug output.
    """

    if clip is None:
        message = "No clip provided to create_proxy_and_wait_async"
        if logger:
            logger.error(message)
        else:
            print(f"ERROR: {message}")
        return False

    # enable proxies before generating them
    clip.use_proxy = True
    clip.use_proxy_custom_directory = True
    if not clip.proxy.directory:
        if logger:
            logger.warn("Proxy directory was not set; using default '//proxies'")
        clip.proxy.directory = "//proxies"

    directory = bpy.path.abspath(clip.proxy.directory)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        message = f"Failed to create proxy directory: {directory} ({exc})"
        if logger:
            logger.error(message)
        else:
            print(f"ERROR: {message}")
        return False

    proxy_path = os.path.join(directory, "proxy_50.avi")

    try:
        clip.proxy.build_50 = True
    except Exception as e:  # pylint: disable=broad-except
        if logger:
            logger.error(f"Proxy-Build-Setup fehlgeschlagen: {e}")
        else:
            print(f"ERROR: Proxy-Build-Setup fehlgeschlagen: {e}")
        return False

    if logger:
        logger.info(f"Waiting for proxy file: {proxy_path}")

    state = {"start": time.time()}

    def _wait_for_proxy():
        if os.path.exists(proxy_path):
            if logger:
                logger.info("Proxy file found.")
            if callback:
                callback()
            return None
        elapsed = time.time() - state["start"]
        if elapsed > timeout:
            if logger:
                logger.error(f"Proxy creation timed out after {timeout} seconds.")
            if callback:
                callback()
            return None
        if logger:
            logger.info(f"Proxy not found yet... {int(elapsed)}s elapsed")
        return 1.0

    bpy.app.timers.register(_wait_for_proxy)
    return True


