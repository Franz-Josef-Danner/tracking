"""Create a 50% proxy and wait for its files to appear."""

import bpy
import os
import shutil
import threading
import time


def remove_existing_proxies():
    """Remove previously generated proxy files."""
    clip = bpy.context.space_data.clip
    if not clip:
        print("Kein aktiver Clip.")
        return

    proxy_dir = bpy.path.abspath("//BL_proxy/")
    if os.path.isdir(proxy_dir):
        print(f"Lösche altes Proxy-Verzeichnis {proxy_dir}")
        shutil.rmtree(proxy_dir, ignore_errors=True)


def create_proxy_and_wait(wait_time=0.0):
    print("Starte Proxy-Erstellung (50%, custom Pfad)")
    clip = bpy.context.space_data.clip
    if not clip:
        print("Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    if not os.path.isfile(clip_path):
        print("Clip-Datei existiert nicht.")
        return

    clip.use_proxy = True
    clip.proxy.build_25 = False
    clip.proxy.build_50 = True
    clip.proxy.build_75 = False
    clip.proxy.build_100 = False
    clip.proxy.quality = 50
    clip.use_proxy_custom_directory = True
    proxy_dir = "//BL_proxy/"
    clip.proxy.directory = proxy_dir
    full_proxy = bpy.path.abspath(proxy_dir)
    os.makedirs(full_proxy, exist_ok=True)
    bpy.ops.clip.rebuild_proxy()
    print("Warte auf erste Proxy-Datei…")

    def wait_file():
        proxy_filename = "proxy_50.avi"
        direct_path = os.path.join(full_proxy, proxy_filename)
        alt_folder = os.path.join(full_proxy, os.path.basename(clip.filepath))
        alt_path = os.path.join(alt_folder, proxy_filename)
        for _ in range(180):
            time.sleep(0.5)
            if os.path.exists(direct_path) or os.path.exists(alt_path):
                print("Proxy-Datei gefunden")
                return
        print("Zeitüberschreitung beim Warten auf Proxy-Datei")

    wait_thread = threading.Thread(target=wait_file)
    wait_thread.start()
    if wait_time > 0:
        wait_thread.join(timeout=wait_time)

