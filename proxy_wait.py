""import bpy
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
    print(f"📄 Clip-Pfad: {clip_path}")
    if not os.path.isfile(clip_path):
        print("❌ Clip-Datei existiert nicht.")
        return

    print("🔧 Setze Proxy-Einstellungen …")
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
    print(f"📁 Proxy-Zielordner: {full_proxy}")
    print(f"📦 Erwartete Proxy-Datei: proxy_50.avi")
    sys.stdout.flush()

    try:
        area = next(area for area in bpy.context.window.screen.areas if area.type == 'CLIP_EDITOR')
        override = bpy.context.copy()
        override['area'] = area
        print("🚀 Starte rebuild_proxy() Operator …")
        result = bpy.ops.clip.rebuild_proxy(override, 'EXEC_DEFAULT')
        print(f"🔁 Operator-Rückgabe: {result}")
    except StopIteration:
        print("❌ Kein CLIP_EDITOR-Bereich gefunden.")
        return
    except Exception as e:
        print(f"❌ Fehler beim Aufruf von rebuild_proxy: {e}")
        return

    proxy_filename = "proxy_50.avi"
    direct_path = os.path.join(full_proxy, proxy_filename)
    alt_folder = os.path.join(full_proxy, os.path.basename(clip.filepath))
    alt_path = os.path.join(alt_folder, proxy_filename)

    print(f"⏳ Warte bis Proxy-Datei erscheint (max. {wait_time}s)…")
    found = False
    for i in range(int(wait_time)):
        print(f"⏱️ Sekunde {i+1}:")
        if os.path.exists(direct_path):
            print(f"✅ Proxy gefunden (direkt): {direct_path}")
            found = True
            break
        if os.path.exists(alt_path):
            print(f"✅ Proxy gefunden (alt): {alt_path}")
            found = True
            break
        print("… noch kein Proxy vorhanden.")
        time.sleep(1)

    if not found:
        print("❌ Zeitüberschreitung: Keine Proxy-Datei gefunden.")
        print(f"🔍 Prüfe directory: {clip.proxy.directory}")
        print(f"🔍 build_50: {clip.proxy.build_50}, quality: {clip.proxy.quality}")
        return

    print("♻️ Rufe clip.reload() auf …")
    clip.reload()
    print("✅ Clip neu geladen – Proxy sollte nun sichtbar sein.")
    print(f"🔍 Aktueller Zustand: build_50={clip.proxy.build_50}, build_25={clip.proxy.build_25}")
    print(f"📂 Verwendetes Verzeichnis laut Clip: {bpy.path.abspath(clip.proxy.directory)}")
    print(f"🧪 Dateiexistenz-Check: {os.path.exists(direct_path)=}, {os.path.exists(alt_path)=}")
    sys.stdout.flush()"
