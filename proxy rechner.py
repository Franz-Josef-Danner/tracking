import bpy
import os

# === RAM-basierte Einschätzung ===

def classify_resolution(width, height):
    if width >= 3840:
        return '4K'
    elif width >= 1920:
        return '1080p'
    else:
        return 'SD'

def estimate_uncompressed_ram_need(width, height, frames, bits_per_channel=8, channels=3):
    bytes_per_channel = bits_per_channel / 8
    bytes_per_frame = width * height * channels * bytes_per_channel
    total_bytes = bytes_per_frame * frames
    total_gb = total_bytes / (1024 ** 3)
    return total_gb

def suggest_proxy_percentage(ratio):
    if ratio <= 0.85:
        return None
    elif ratio <= 1.5:
        return 75
    elif ratio <= 3.0:
        return 50
    else:
        return 25

def estimate_proxy_need_from_ram(clip, user_ram_gb):
    width = clip.size[0]
    height = clip.size[1]
    fps = clip.fps
    frame_count = clip.frame_duration
    duration_min = frame_count / fps / 60

    resolution_label = classify_resolution(width, height)
    uncompressed_ram_gb = estimate_uncompressed_ram_need(width, height, frame_count)
    tracking_overhead = 0.25 * uncompressed_ram_gb
    total_need = uncompressed_ram_gb + tracking_overhead
    ram_ratio = total_need / user_ram_gb
    proxy_suggestion = suggest_proxy_percentage(ram_ratio)

    result = [
        f"📁 Datei: {os.path.basename(bpy.path.abspath(clip.filepath))}",
        f"🖐️ Auflösung: {width}x{height} ({resolution_label})",
        f"🎮 Dauer: {duration_min:.2f} min @ {fps:.1f} fps",
        f"🧠 RAM-Verbrauch geschätzt: {uncompressed_ram_gb:.2f} GB",
        f"➕ Tracking-Zuschlag (25%): +{tracking_overhead:.2f} GB",
        f"🧮 Gesamt-RAM-Bedarf: {total_need:.2f} GB",
        f"💻 Eingestellter System-RAM: {user_ram_gb:.2f} GB",
    ]

    if proxy_suggestion:
        result.append(f"⚠️ RAM-Knappheit erkannt – Proxy empfohlen.")
        result.append(f"🔧 Empfohlene Proxy-Auflösung: {proxy_suggestion}%")
    else:
        result.append("✅ RAM ausreichend – kein Proxy notwendig.")

    return "\n".join(result), proxy_suggestion

# === UI & Operator ===


class CLIP_OT_check_proxy_ram(bpy.types.Operator):
    bl_idname = "clip.check_proxy_ram"
    bl_label = "RAM-Prognose prüfen"

    def execute(self, context):
        props = context.scene.proxy_check_props
        clip = context.space_data.clip

        if not clip:
            self.report({'WARNING'}, "❌ Kein Clip geladen.")
            return {'CANCELLED'}

        result, proxy_size = estimate_proxy_need_from_ram(clip, props.user_ram_gb)
        props.result = result
        props.proxy_recommendation = str(proxy_size) if proxy_size else ""
        return {'FINISHED'}

class CLIP_OT_build_recommended_proxy(bpy.types.Operator):
    bl_idname = "clip.build_recommended_proxy"
    bl_label = "Empfohlenen Proxy erstellen"

    def execute(self, context):
        clip = context.space_data.clip
        props = context.scene.proxy_check_props
        proxy_size = props.proxy_recommendation

        if not clip or proxy_size == "":
            self.report({'WARNING'}, "❌ Kein Proxy empfohlen oder Clip fehlt.")
            return {'CANCELLED'}

        clip.use_proxy = True
        proxy = clip.proxy
        proxy.quality = 50
        proxy.directory = bpy.path.abspath("//BL_proxy/")
        proxy.timecode = 'FREE_RUN_NO_GAPS'

        # Reset aller Proxy-Flags
        proxy.build_25 = proxy.build_50 = proxy.build_75 = proxy.build_100 = False

        # Empfohlene Größe aktivieren
        if proxy_size == "25":
            proxy.build_25 = True
        elif proxy_size == "50":
            proxy.build_50 = True
        elif proxy_size == "75":
            proxy.build_75 = True
        else:
            self.report({'WARNING'}, "Ungültige Proxy-Größe.")
            return {'CANCELLED'}

        # Undistorted deaktivieren
        proxy.build_undistorted_25 = False
        proxy.build_undistorted_50 = False
        proxy.build_undistorted_75 = False
        proxy.build_undistorted_100 = False

        # Proxy-Dateien erstellen lassen (mit vollständigem override inkl. Region)
        override = bpy.context.copy()
        override['area'] = next(area for area in bpy.context.screen.areas if area.type == 'CLIP_EDITOR')
        override['region'] = next(region for region in override['area'].regions if region.type == 'WINDOW')
        override['space_data'] = override['area'].spaces.active
        override['clip'] = clip

        with bpy.context.temp_override(**override):
            bpy.ops.clip.rebuild_proxy()

        self.report({'INFO'}, f"✅ Proxy {proxy_size}% wird erstellt.")
        return {'FINISHED'}

class ProxyCheckProperties(bpy.types.PropertyGroup):
    result: bpy.props.StringProperty(name="Ergebnis", default="")
    user_ram_gb: bpy.props.FloatProperty(
        name="System-RAM (GB)",
        default=16.0,
        min=1.0,
        max=1024.0,
        description="Gib deinen verfügbaren Arbeitsspeicher in GB an"
    )
    proxy_recommendation: bpy.props.StringProperty(name="Empfohlene Proxy-Auflösung", default="")

# === Registrierung ===

classes = [
    ProxyCheckProperties,
    CLIP_OT_check_proxy_ram,
    CLIP_OT_build_recommended_proxy
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.proxy_check_props = bpy.props.PointerProperty(type=ProxyCheckProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.proxy_check_props

if __name__ == "__main__":
    register()
