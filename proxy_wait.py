"""Create a 50% proxy and wait for its files to appear."""

print("✅ proxy_wait.py geladen aus:", __file__)

import bpy
import os
import shutil
import sys
import threading
import time
import glob

PROXY_DIR = "//BL_proxy/"


def remove_existing_proxies():
    """Remove previously generated proxy files."""
    clip = bpy.context.space_data.clip
    if not clip:
        print("Kein aktiver Clip.")
        return

    proxy_dir = bpy.path.abspath(PROXY_DIR)
    if os.path.isdir(proxy_dir):
        print(f"Lösche altes Proxy-Verzeichnis {proxy_dir}")
        shutil.rmtree(proxy_dir, ignore_errors=True)


def create_proxy_and_wait(wait_time=0.0):
    print("Starte Proxy-Erstellung (50%, custom Pfad)")
    sys.stdout.flush()
    clip = bpy.context.space_data.clip
    if not clip:
        print("Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    if not os.path.isfile(clip_path):
        print("Clip-Datei existiert nicht.")
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
    print(f"Proxy wird im Ordner {full_proxy} erstellt")
    print("Proxy-Erstellung gestartet…")
    sys.stdout.flush()

    def wait_file():
        # Blender may keep the file temporarily named "proxy_50_part.*" while
        # the proxy job is running. The countdown should stop as soon as this
        # file appears, so we look for any path beginning with "proxy_50".
        proxy_pattern = os.path.join(full_proxy, "**", "proxy_50*")
        checks = int(wait_time * 2) if wait_time > 0 else 180
        for _ in range(checks):
            time.sleep(0.5)
            matches = [p for p in glob.glob(proxy_pattern, recursive=True)
                       if os.path.isfile(p)]
            if matches:
                print("Proxy-Datei gefunden")
                sys.stdout.flush()
                return
        print("Zeitüberschreitung beim Warten auf Proxy-Datei")
        sys.stdout.flush()

    wait_thread = threading.Thread(target=wait_file)
    wait_thread.start()
    print(
        "Warte auf die erste Proxy-Datei (Blender legt mehrere Dateien an, "
        "sobald eine erscheint, geht es weiter)"
    )
    sys.stdout.flush()

    countdown_thread = None
    if wait_time > 0:
        def countdown():
            remaining = int(wait_time)
            while remaining > 0 and wait_thread.is_alive():
                print(f"⏳ Warte {remaining}s auf Proxy…")
                sys.stdout.flush()
                time.sleep(1)
                remaining -= 1
        countdown_thread = threading.Thread(target=countdown)
        countdown_thread.start()

    bpy.ops.clip.rebuild_proxy('INVOKE_DEFAULT')

    wait_thread.join()
    if countdown_thread:
        countdown_thread.join()
    print("Proxy-Erstellung abgeschlossen")
    sys.stdout.flush()

