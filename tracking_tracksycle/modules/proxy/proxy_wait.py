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
        Clip on which the proxy should be built.
    timeout : int, optional
        Maximum time in seconds to wait for the proxy file.
    logger : :class:`TrackerLogger`, optional
        Optional logger for timeout feedback.
    """
    clip.proxy.build_50 = True
    clip.use_proxy = True

    directory = clip.proxy.directory
    proxy_path = os.path.join(directory, "proxy_50.avi") if directory else None

    start = time.time()
    while proxy_path and not os.path.exists(proxy_path):
        if time.time() - start > timeout:
            if logger:
                logger.warn("Proxy creation timed out")
            else:
                print("Proxy creation timed out")
            return False
        time.sleep(1)
    return True


