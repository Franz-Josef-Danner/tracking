"""Create a 50% proxy and wait for its files to appear.

The optional ``on_finish`` callback is invoked with the active clip once
the first proxy file is detected or the timeout expires.
"""
# Debug print of this file's path was removed to keep the console clean.

import bpy
import os
import shutil
import sys
import time
import glob
import logging

# Import the helper from this add-on's utils module, not Blender's internal one.
from .utils import get_active_clip

PROXY_DIR = "//BL_proxy/"

logger = logging.getLogger(__name__)


def remove_existing_proxies(clip=None):
    """Remove previously generated proxy files for ``clip`` or the active one."""
    if clip is None:
        clip = get_active_clip(bpy.context)
    if not clip:
        logger.info("Kein aktiver Clip.")
        return

    proxy_dir = bpy.path.abspath(PROXY_DIR)
    if os.path.isdir(proxy_dir):
        logger.info(f"Lösche altes Proxy-Verzeichnis {proxy_dir}")
        shutil.rmtree(proxy_dir, ignore_errors=True)


def create_proxy_and_wait(wait_time=0.0, on_finish=None, clip=None):
    """Build proxies and invoke ``on_finish`` with the given clip."""
    logger.info("Starte Proxy-Erstellung (50%, custom Pfad)")
    sys.stdout.flush()
    if clip is None:
        clip = get_active_clip(bpy.context)
    if not clip:
        logger.info("Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    if not os.path.isfile(clip_path):
        logger.info("Clip-Datei existiert nicht.")
        return

    clip.use_proxy = True
    # Proxy-Timecode aktivieren
    if hasattr(clip, "use_proxy_timecode"):
        clip.use_proxy_timecode = True
    if hasattr(clip.proxy, "timecode"):
        clip.proxy.timecode = 'FREE_RUN_NO_GAPS'
    clip.proxy.build_25 = False
    clip.proxy.build_50 = True
    clip.proxy.build_75 = False
    clip.proxy.build_100 = False
    clip.proxy.quality = 50
    clip.use_proxy_custom_directory = True
    clip.proxy.directory = PROXY_DIR
    full_proxy = bpy.path.abspath(PROXY_DIR)
    os.makedirs(full_proxy, exist_ok=True)
    logger.info(f"Proxy wird im Ordner {full_proxy} erstellt")
    logger.info("Proxy-Erstellung gestartet…")
    sys.stdout.flush()

    proxy_pattern = os.path.join(full_proxy, "**", "proxy_50.*")
    wait_seconds = wait_time if wait_time > 0 else 180
    start = time.time()

    def check():
        matches = [
            p
            for p in glob.glob(proxy_pattern, recursive=True)
            if os.path.isfile(p) and "_part" not in os.path.basename(p)
        ]
        if matches:
            logger.info("Proxy-Datei gefunden")
            logger.info("Proxy-Erstellung abgeschlossen")
            if on_finish:
                logger.info("Führe nachgelagerte Schritte aus")
            sys.stdout.flush()
            if on_finish:
                on_finish(clip)
            return None

        elapsed = time.time() - start
        if elapsed >= wait_seconds:
            logger.info("Zeitüberschreitung beim Warten auf Proxy-Datei")
            logger.info("Proxy-Erstellung abgeschlossen")
            if on_finish:
                logger.info("Führe nachgelagerte Schritte aus")
            sys.stdout.flush()
            if on_finish:
                on_finish(clip)
            return None

        remaining = int(wait_seconds - elapsed)
        if remaining % 10 == 0:
            logger.info(f"⏳ Warte {remaining}s auf Proxy…")
            sys.stdout.flush()
        return 1.0

    logger.info(
        "Warte auf die erste Proxy-Datei (Blender legt mehrere Dateien an, "
        "sobald eine erscheint, geht es weiter)"
    )
    sys.stdout.flush()

    bpy.ops.clip.rebuild_proxy('INVOKE_DEFAULT')
    bpy.app.timers.register(check)


