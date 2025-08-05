import bpy

# Importiere die Operator-Klassen aus den Modulen
from .proxy_builder import CLIP_OT_proxy_builder
from .tracker_settings import CLIP_OT_tracker_settings
from .detect import CLIP_OT_detect
from .bidirectional_track import CLIP_OT_bidirectional_track

# Liste aller Operator-Klassen zur Registrierung
classes = (
    CLIP_OT_proxy_builder,
    CLIP_OT_tracker_settings,
    CLIP_OT_detect,
    CLIP_OT_bidirectional_track,
)

# Registrierungsfunktion
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

# Unregistrierungsfunktion
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

# Nur bei direktem Ausführen als Script:
if __name__ == "__main__":
    register()
