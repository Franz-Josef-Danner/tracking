"""Proxy management utilities for Kaiserlich Tracksycle."""

import bpy
import os
import time


def remove_existing_proxies(clip):
    """Delete previously generated proxy files if they exist."""
    directory = clip.proxy.directory
    if not directory:
        return
    path = os.path.join(directory, "proxy_50.avi")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


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

    directory = clip.proxy.directory
    if directory is None:
        warning = "Proxy directory is not set; clip may not be initialized."
        if logger:
            logger.warn(warning)
        else:
            print(f"WARNING: {warning}")
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


