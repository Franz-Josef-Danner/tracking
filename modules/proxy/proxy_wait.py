"""Proxy management utilities for Kaiserlich Tracksycle."""

import bpy
import glob
import os
import shutil
import time
import threading
import ctypes
import sys


def log_proxy_status(clip, logger=None):
    """Log the proxy status for ``clip``.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        Movie clip whose proxy status should be reported.
    logger : :class:`TrackerLogger`, optional
        Logger used for output; when omitted ``print`` is used.
    """

    if not clip:
        return

    if clip.use_proxy:
        p = clip.proxy
        message = (
            f"[Proxy] Clip \"{clip.name}\" ist AKTIV (use_proxy=True)\n"
            f" \u2192 build_25: {p.build_25}, build_50: {p.build_50}, "
            f"build_75: {p.build_75}, build_100: {p.build_100}"
        )
    else:
        message = f"[Proxy] Clip \"{clip.name}\" ist INAKTIV (use_proxy=False)"

    if logger:
        logger.info(message)
        directory = getattr(clip.proxy, "directory", None)
        if directory:
            logger.debug(f"Proxy directory: {bpy.path.abspath(directory)}")
    else:
        print(message)


def wait_for_stable_file(path, timeout=60, check_interval=1, stable_time=3):
    """Wait until ``path`` exists and its size no longer changes."""

    start_time = time.time()
    last_size = -1
    same_size_count = 0

    while time.time() - start_time < timeout:
        if os.path.exists(path):
            current_size = os.path.getsize(path)
            if current_size == last_size:
                same_size_count += 1
                if same_size_count >= stable_time:
                    return True
            else:
                same_size_count = 0
                last_size = current_size
        time.sleep(check_interval)
    raise TimeoutError(f"Proxy file {path} not stable after {timeout} seconds")


def is_file_locked(filepath):
    """Return ``True`` if ``filepath`` is locked on Windows."""
    if os.name != "nt":
        return False

    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = -1

    handle = ctypes.windll.kernel32.CreateFileW(
        str(filepath),
        GENERIC_WRITE,
        FILE_SHARE_READ,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        return True
    ctypes.windll.kernel32.CloseHandle(handle)
    return False


def remove_existing_proxies(clip, logger=None):
    """Remove and recreate the proxy directory for ``clip``.

    This deletes the entire proxy folder along with all files inside
    and recreates it afterwards.  ``clip.use_proxy_custom_directory``
    is activated so the configured directory is honored.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        MovieClip whose proxy directory should be cleaned.
    logger : :class:`TrackerLogger`, optional
        Logger used for debug output.
    """

    clip.use_proxy_custom_directory = True
    if not clip.proxy.directory:
        clip.proxy.directory = "//proxies"

    abs_dir = bpy.path.abspath(clip.proxy.directory)

    if os.path.exists(abs_dir):
        if os.name == "nt" and is_file_locked(abs_dir):
            message = (
                f"[Tracksycle] WARNUNG: Proxy-Datei {abs_dir} ist gesperrt und kann nicht gelöscht werden."
            )
            if logger:
                logger.warn(message)
            else:
                print(message)
        else:
            try:
                shutil.rmtree(abs_dir)
                if logger:
                    logger.info(f"Proxy directory removed: {abs_dir}")
            except Exception as exc:  # pylint: disable=broad-except
                if logger:
                    logger.warn(f"Failed to remove proxy directory: {exc}")

    try:
        os.makedirs(abs_dir, exist_ok=True)
    except Exception as exc:  # pylint: disable=broad-except
        if logger:
            logger.error(f"Failed to create proxy directory: {exc}")


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

    if logger:
        logger.debug(
            f"Start proxy creation for {clip.name} with timeout {timeout}s"
        )

    # enable proxies before generating them
    clip.use_proxy = True
    # ensure proxy directory usage is enabled
    clip.use_proxy_custom_directory = True
    log_proxy_status(clip, logger)
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

    possible_proxies = glob.glob(os.path.join(directory, "proxy_50*.avi"))
    if possible_proxies:
        proxy_path = possible_proxies[0]  # Nimm die erste passende Datei
    else:
        proxy_path = os.path.join(directory, "proxy_50.avi")  # Fallback
    if logger:
        logger.info(f"Looking for proxy file: {proxy_path}")

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
            remaining = max(timeout - (time.time() - state["start"]), 0)
            try:
                wait_for_stable_file(proxy_path, timeout=remaining)
            except TimeoutError as exc:
                if logger:
                    logger.error(str(exc))
                else:
                    print(f"ERROR: {exc}")
            else:
                if logger:
                    logger.info("Proxy file found.")
                    logger.debug(
                        f"Proxy generation took {time.time() - state['start']:.2f}s"
                    )
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

    if logger:
        logger.debug(
            f"Start async proxy creation for {clip.name} with timeout {timeout}s"
        )

    # enable proxies before generating them
    clip.use_proxy = True
    clip.use_proxy_custom_directory = True
    log_proxy_status(clip, logger)
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


    possible_proxies = glob.glob(os.path.join(directory, "proxy_50*.avi"))
    if possible_proxies:
        proxy_path = possible_proxies[0]  # Nimm die erste passende Datei
    else:
        proxy_path = os.path.join(directory, "proxy_50.avi")  # Fallback
    if logger:
        logger.info(f"Looking for proxy file: {proxy_path}")

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
            remaining = max(timeout - (time.time() - state["start"]), 0)
            try:
                wait_for_stable_file(proxy_path, timeout=remaining)
            except TimeoutError as exc:
                if logger:
                    logger.error(str(exc))
                else:
                    print(f"ERROR: {exc}")
            else:
                if logger:
                    logger.info("Proxy file found.")
                    logger.debug(
                        f"Proxy generation took {time.time() - state['start']:.2f}s"
                    )
            if callback:
                if logger:
                    logger.debug("Executing proxy callback")
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


def detect_features_in_ui_context(threshold=1.0, margin=0, min_distance=0, placement="FRAME", logger=None):
    """Run feature detection in a valid Clip Editor UI context."""
    for area in bpy.context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    spaces = area.spaces
                    try:
                        space_iter = list(spaces)
                    except TypeError:
                        space_iter = [spaces.active]
                    for space in space_iter:
                        if space.type == 'CLIP_EDITOR':
                            if logger:
                                logger.info("Running feature detection in UI context")
                                logger.debug(
                                    f"threshold={threshold}, margin={margin}, "
                                    f"min_distance={min_distance}, placement={placement}"
                                )
                            with bpy.context.temp_override(
                                area=area,
                                region=region,
                                space_data=space,
                            ):
                                bpy.ops.clip.detect_features(
                                    threshold=threshold,
                                    margin=margin,
                                    min_distance=min_distance,
                                    placement=placement,
                                )
                            if logger:
                                logger.debug("Feature detection executed")
                            return True
    if logger:
        logger.error("No valid UI context found")
    else:
        print("\u274c Kein g\u00fcltiger UI-Kontext gefunden")
    return False


def wait_for_proxy_and_trigger_detection(clip, proxy_path, threshold=1.0, margin=0, min_distance=0, placement="FRAME", logger=None):
    """Wait for ``proxy_path`` to appear and then run detection in the UI context."""

    if logger:
        logger.debug(f"Waiting for proxy at {proxy_path} to trigger detection")

    def wait_loop():
        for _ in range(300):
            time.sleep(0.5)
            if os.path.exists(proxy_path):
                try:
                    with open(proxy_path, "rb"):
                        if logger:
                            logger.info("\u2705 Proxy verf\u00fcgbar")
                        bpy.app.timers.register(
                            lambda: detect_features_in_ui_context(
                                threshold,
                                margin,
                                min_distance,
                                placement,
                                logger,
                            ),
                            first_interval=0.1,
                        )
                        if logger:
                            logger.debug("Proxy found, detection scheduled")
                        return
                except PermissionError:
                    continue
        if logger:
            logger.error("Proxy nicht fertig oder blockiert.")
        else:
            print("\u274c Proxy nicht fertig oder blockiert.")

    threading.Thread(target=wait_loop).start()


__all__ = [
    "wait_for_stable_file",
    "log_proxy_status",
    "remove_existing_proxies",
    "create_proxy_and_wait",
    "create_proxy_and_wait_async",
    "detect_features_in_ui_context",
    "wait_for_proxy_and_trigger_detection",
]


