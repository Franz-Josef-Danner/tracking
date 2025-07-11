"""Create a 50% proxy and wait for its files to appear."""

print("✅ proxy_wait.py geladen aus:", __file__)

import bpy
import os
import shutil
import sys
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
            print("Proxy-Datei gefunden")
            print("Proxy-Erstellung abgeschlossen")
            sys.stdout.flush()
            return None

        elapsed = time.time() - start
        if elapsed >= wait_seconds:
            print("Zeitüberschreitung beim Warten auf Proxy-Datei")
            print("Proxy-Erstellung abgeschlossen")
            sys.stdout.flush()
            return None

        remaining = int(wait_seconds - elapsed)
        if remaining % 10 == 0:
            print(f"⏳ Warte {remaining}s auf Proxy…")
            sys.stdout.flush()
        return 1.0

    print(
        "Warte auf die erste Proxy-Datei (Blender legt mehrere Dateien an, "
        "sobald eine erscheint, geht es weiter)"
    )
    sys.stdout.flush()

    bpy.ops.clip.rebuild_proxy('INVOKE_DEFAULT')
    bpy.app.timers.register(check)


