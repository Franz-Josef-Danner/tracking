import bpy
import os
import time
import threading

def create_proxy_and_wait():
    print("🟡 Starte Proxy-Erstellung (50%, custom Pfad)")
    clip = bpy.context.space_data.clip
    if not clip:
        print("❌ Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    print(f"📂 Clip-Pfad: {clip_path}")
    if not os.path.isfile(clip_path):
        print("❌ Clip-Datei existiert nicht.")
        return

    print("⚙️ Setze Proxy-Optionen…")
    clip.use_proxy = True
    clip.proxy.build_25 = False
    clip.proxy.build_50 = True
    clip.proxy.build_75 = False
    clip.proxy.build_100 = False
    print("✅ Proxy-Build 50% aktiviert")

    clip.proxy.quality = 50
    print("✅ Qualität auf 50 gesetzt")
    
    clip.use_proxy_custom_directory = True
    print("✅ Custom Directory aktiviert")

    proxy_dir = "//BL_proxy/"
    clip.proxy.directory = proxy_dir
    full_proxy = bpy.path.abspath(proxy_dir)
    print(f"📁 Proxy-Zielverzeichnis: {full_proxy}")
    os.makedirs(full_proxy, exist_ok=True)

    print("⚠️ Wenn Zeitcode nötig: bitte manuell in der UI setzen.")
    print("🚧 Starte Proxy-Rebuild…")
    bpy.ops.clip.rebuild_proxy()
    print("🕓 Warte auf erste Proxy-Datei…")

    def wait_file():
        proxy_filename = "proxy_50.avi"
        # Option 1: Direkter Pfad
        direct_path = os.path.join(full_proxy, proxy_filename)
        # Option 2: Pfad mit Clipname-Ordner (falls Blender es doch dort ablegt)
        alt_folder = os.path.join(full_proxy, os.path.basename(clip.filepath))
        alt_path = os.path.join(alt_folder, proxy_filename)

        print(f"🔍 Suche nach Datei: {direct_path} oder {alt_path}")

        for i in range(300):
            # Short pause to avoid busy waiting while the proxy is built
            time.sleep(0.5)
            if os.path.exists(direct_path):
                print(f"✅ Proxy-Datei gefunden: {direct_path}")
                return
            if os.path.exists(alt_path):
                print(f"✅ Proxy-Datei gefunden (alternativ): {alt_path}")
                return
            if i % 10 == 0:
                print(f"⏳ Warte… {i}/300")
        print("⚠️ Zeitüberschreitung")

    threading.Thread(target=wait_file).start()

class CLIP_OT_proxy_custom_operator(bpy.types.Operator):
    bl_idname = "clip.proxy_custom_operator"
    bl_label = "Proxy 50% erstellen"

    def execute(self, context):
        print("🔘 Button gedrückt!")
        create_proxy_and_wait()
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_proxy_custom_operator)
    print("✅ Proxy-Operator registriert")

def unregister():
    bpy.utils.unregister_class(CLIP_OT_proxy_custom_operator)
    print("❎ Proxy-Operator entfernt")

if __name__ == "__main__":
    register()
