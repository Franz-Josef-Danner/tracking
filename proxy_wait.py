import bpy
import os
import sys
import time

def create_proxy_and_wait(wait_time=300.0):
    print("🔹 Proxy-Erstellung (50%, Timecode) starten …")
    sys.stdout.flush()

    clip = bpy.context.space_data.clip
    if not clip:
        print("❌ Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    print("📄 Clip-Pfad:", clip_path)
    if not os.path.isfile(clip_path):
        print("❌ Clip-Datei existiert nicht.")
        return

    # Proxy + Timecode Einstellungen setzen
    clip.use_proxy = True
    clip.use_proxy_custom_directory = True
    clip.use_proxy_timecode = True
    clip.proxy.timecode = 'RECORD_RUN_NO_GAPS'
    clip.proxy.build_25 = False
    clip.proxy.build_50 = True
    clip.proxy.build_75 = False
    clip.proxy.build_100 = False
    clip.proxy.build_record_run = True
    clip.proxy.quality = 50

    proxy_dir = "//BL_proxy/"
    clip.proxy.directory = proxy_dir
    full_proxy = bpy.path.abspath(proxy_dir)
    os.makedirs(full_proxy, exist_ok=True)

    print("📁 Zielordner:", full_proxy)
    sys.stdout.flush()

    # Operator im Clip Editor aufrufen
    try:
        area = next(a for a in bpy.context.window.screen.areas if a.type == 'CLIP_EDITOR')
        override = bpy.context.copy()
        override['area'] = area
        print("🚀 rebuild_proxy() ausführen …")
        result = bpy.ops.clip.rebuild_proxy(override, 'EXEC_DEFAULT')
        print("🔁 Operator-Result:", result)
    except Exception as e:
        print("❌ Fehler beim rebuild_proxy():", e)
        return

    # Warten auf die erzeugten Proxys
    proxy_file = os.path.join(full_proxy, "proxy_50.avi")
    start = time.time()
    print(f"⏳ Warte max. {wait_time}s auf Proxy-Datei …")
    found = False
    while time.time() - start < wait_time:
        if os.path.isfile(proxy_file):
            print("✅ Proxy-Datei gefunden:", proxy_file)
            found = True
            break
        time.sleep(1)
        sys.stdout.flush()

    if not found:
        print("⏱️ Timeout: Keine Proxy-Datei.")
        print("🔍 Einstellungen:",
              f"build_50={clip.proxy.build_50}",
              f"build_record_run={clip.proxy.build_record_run}",
              f"directory={clip.proxy.directory}")
        return

    # Clip neu laden
    clip.reload()
    print("♻️ Clip neu geladen. Proxy + Timecode sollten jetzt aktiv sein.")
    print(f"🔍 Finaler Zustand: build_record_run={clip.proxy.build_record_run}")
