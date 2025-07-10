import bpy
import os
import sys
import time

def create_proxy_and_wait(wait_time=300.0):
    print("🟡 Starte Proxy-Erstellung (50 %, custom Pfad)")
    sys.stdout.flush()

    clip = bpy.context.space_data.clip
    if not clip:
        print("❌ Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    if not os.path.isfile(clip_path):
        print("❌ Clip-Datei existiert nicht.")
        return

    # Proxy-Einstellungen setzen
    clip.use_proxy = True
    clip.use_proxy_timecode = True
    clip.proxy.timecode = 'RECORD_RUN_NO_GAPS'
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
    print(f"📁 Proxy wird im Ordner erstellt: {full_proxy}")
    sys.stdout.flush()

    # Operator sicher aufrufen
    try:
        area = next(area for area in bpy.context.window.screen.areas if area.type == 'CLIP_EDITOR')
        override = bpy.context.copy()
        override['area'] = area
        bpy.ops.clip.rebuild_proxy(override, 'EXEC_DEFAULT')
    except StopIteration:
        print("❌ Kein CLIP_EDITOR-Bereich gefunden.")
        return

    # Dateipfade
    proxy_filename = "proxy_50.avi"
    direct_path = os.path.join(full_proxy, proxy_filename)
    alt_folder = os.path.join(full_proxy, os.path.basename(clip.filepath))
    alt_path = os.path.join(alt_folder, proxy_filename)

    # 300 Sekunden auf Proxy-Datei warten
    print(f"⏳ Warte bis Proxy-Datei auftaucht (max. {wait_time}s)...")
    found = False
    for i in range(int(wait_time)):
        if os.path.exists(direct_path):
            print(f"✅ Proxy gefunden (direkt): {direct_path}")
            found = True
            break
        if os.path.exists(alt_path):
            print(f"✅ Proxy gefunden (alt): {alt_path}")
            found = True
            break
        print(f"🔎 Noch kein Proxy nach {i+1}s...")
        time.sleep(1)

    if not found:
        print("⏱️ Zeitüberschreitung: Keine Proxy-Datei gefunden.")
        return

    # Clip neu laden
    clip.reload()
    print("♻️ Clip neu geladen – Proxy sollte jetzt sichtbar sein.")
