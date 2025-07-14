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
    """Create a 50% proxy and wait until the proxy file exists.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        MovieClip for which the proxy should be generated.
    timeout : int, optional
        Maximum time in seconds to wait for proxy generation.
    logger : :class:`TrackerLogger`, optional
        Logger used for warning output.

    Returns
    -------
    bool
        ``True`` if the proxy file exists within ``timeout``,
        otherwise ``False``.
    """

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

    if not os.access(directory, os.W_OK):
        message = f"Proxy directory is not writable: {directory}"
        if logger:
            logger.error(message)
        else:
            print(f"ERROR: {message}")
        return False

    clip.proxy.build_50 = True
    clip.use_proxy = True
    bpy.ops.clip.rebuild_proxy()

    proxy_path = os.path.join(directory, "proxy_50.avi")

    start = time.time()
    while not os.path.exists(proxy_path):
        if time.time() - start > timeout:
            return False
        time.sleep(1)
    return True


