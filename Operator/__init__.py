import bpy

# Importiere die Operator-Klassen aus den Modulen
from .proxy_builder import CLIP_OT_proxy_builder
from .tracker_settings import CLIP_OT_tracker_settings
from .detect import TRACKING_OT_detect
from .bidirectional_track import CLIP_OT_bidirectional_track
from .clean_short_tracks import CLIP_OT_clean_short_tracks
from .tracking_pipeline import CLIP_OT_tracking_pipeline
from .clean_error_tracks import CLIP_OT_clean_error_tracks


# Liste aller Operator-Klassen zur Registrierung
classes = (
    CLIP_OT_proxy_builder,
    CLIP_OT_tracker_settings,
    TRACKING_OT_detect,
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_clean_error_tracks,
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
