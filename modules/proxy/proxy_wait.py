"""Proxy management utilities for Kaiserlich Tracksycle."""

import bpy
import os
import time


def remove_existing_proxies(clip, logger=None):
    """Delete previously generated proxy files if they exist.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        MovieClip for which old proxies should be removed.
    logger : :class:`TrackerLogger`, optional
        Logger used for warning output.
    """

    if not clip.proxy.directory:
        clip.proxy.directory = "//proxy/"
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
    """Create a 50% proxy and wait until the proxy file exists."""

    if not clip.proxy.directory:
        if logger:
            logger.warn("Proxy directory was not set; using default '//proxy/'")
        clip.proxy.directory = "//proxy/"

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

    if logger:
        logger.info(f"Waiting for proxy file: {proxy_path}")

    start = time.time()
    while not os.path.exists(proxy_path):
        elapsed = time.time() - start
        if elapsed > timeout:
            if logger:
                logger.error("Proxy creation timed out after 300 seconds.")
            return False
        if logger:
            logger.info(f"Proxy not found yet... {int(elapsed)}s elapsed")
        time.sleep(10)

    if logger:
        logger.info("Proxy file found.")
    return True


