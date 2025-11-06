# Operator/Master/master_clean_error_operator.py
import bpy
import traceback
from bpy.types import Operator, Context

LOG_PREFIX = "[CleanError-Diag]"

# ---------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------

def _log(msg):
    print(f"{LOG_PREFIX} {msg}")

def _safe_get(obj, attr, default=None):
    return getattr(obj, attr, default) if hasattr(obj, attr) else default

def _find_clip_editor_override():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        _log(f"→ Prüfe Screen '{screen.name}' in Window {window.as_pointer()}")
        for area in screen.areas:
            _log(f"   • Area={area.type}")
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            _log(f"     ↳ Space={space}, Clip={_safe_get(space,'clip',None)}")
            if not (space and space.clip):
                continue
            region_window = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if not region_window:
                _log("     ⚠️ Keine WINDOW-Region gefunden – überspringe")
                continue
            override = {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region_window,
                "space_data": space,
                "edit_movieclip": space.clip,
            }
            dbg = (f"win={window.as_pointer()}, scr='{screen.name}', "
                   f"area='{area.type}', region='WINDOW', clip='{space.clip.name}'")
            _log(f"✅ Gültiger Clip-Kontext gefunden: {dbg}")
            return override, space.clip, dbg
    _log("❌ Kein Clip-Editor-Kontext gefunden!")
    return None, None, "kein CLIP_EDITOR mit aktivem Clip gefunden"


def _snapshot_tracks(clip):
    data = {}
    for t in clip.tracking.tracks:
        markers = [m.frame for m in t.markers]
        seg_len = (max(markers)-min(markers)+1) if markers else 0
        data[t.name] = {
            "muted": bool(getattr(t, "is_muted", False)),
            "markers": len(markers),
            "first": markers[0] if markers else None,
            "last": markers[-1] if markers else None,
            "seg_len": seg_len,
        }
    return data


def _diff(before, after):
    before_names, after_names = set(before), set(after)
    deleted = sorted(before_names - after_names)
    new = sorted(after_names - before_names)
    changed = []
    for n in sorted(before_names & after_names):
        b, a = before[n], after[n]
        if a["markers"] != b["markers"] or a["seg_len"] != b["seg_len"] or a["muted"] != b["muted"]:
            changed.append(n)
    return deleted, new, changed


def _print_dict_sample(title, dct, limit=10):
    _log(f"{title}: {len(dct)} Einträge")
    for i, (k, v) in enumerate(dct.items()):
        if i >= limit:
            _log(f"  … (+{len(dct)-limit} weitere)")
            break
        _log(f"  {k}: {v}")


# ---------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Führt bpy.ops.clip.clean_error() mit umfangreichem Logging aus"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Clean Error (Diagnostic)"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(default=20.0, min=0.0, soft_max=100.0)
    action: bpy.props.EnumProperty(
        items=[
            ('SELECT', "Select", ""),
            ('DELETE_TRACK', "Delete Track", ""),
            ('DELETE_SEGMENTS', "Delete Segments", ""),
        ],
        default='DELETE_TRACK'
    )

    def execute(self, context: Context):
        _log("──────────────────────────────────────────────────────────────")
        _log(f"Starte Diagnose für CleanError | Threshold={self.threshold:.2f}, Action={self.action}")
        _log(f"Current context: area={_safe_get(context,'area',None)}, space={_safe_get(context,'space_data',None)}")

        override, clip, dbg = _find_clip_editor_override()
        if not clip:
            self.report({'ERROR'}, "Kein gültiger Clip im Clip-Editor.")
            return {'CANCELLED'}

        # --- Tracking Settings prüfen ---
        settings = clip.tracking.settings
        _log(f"Tracking Settings vor dem Clean:")
        _log(f"  clean_action={settings.clean_action}")
        _log(f"  clean_error={settings.clean_error}")
        _log(f"  use_default_red_channel={_safe_get(settings,'use_default_red_channel')}")
        _log(f"  use_default_refine={_safe_get(settings,'use_default_refine')}")

        # --- Snapshot vor dem Clean ---
        before = _snapshot_tracks(clip)
        _print_dict_sample("Vorher Snapshot", before, 5)

        # --- Parameter setzen ---
        settings.clean_action = self.action
        settings.clean_error = self.threshold
        _log(f"→ Setze settings.clean_action='{self.action}', settings.clean_error={self.threshold}")

        # --- API-Verfügbarkeit prüfen ---
        if not hasattr(bpy.ops.clip, "clean_error"):
            _log("❌ bpy.ops.clip.clean_error existiert nicht – möglicherweise kein CLIP-Kontext")
            self.report({'ERROR'}, "Operator bpy.ops.clip.clean_error nicht vorhanden.")
            return {'CANCELLED'}
        _log("✅ bpy.ops.clip.clean_error ist im bpy.ops.clip verfügbar.")

        # --- Operator ausführen ---
        try:
            _log("→ Primärversuch: bpy.ops.clip.clean_error(override)")
            result = bpy.ops.clip.clean_error(override)
            _log(f"   Ergebnis: {result}")
        except Exception as e1:
            _log(f"⚠️ Exception beim Primärversuch: {e1}")
            _log(traceback.format_exc())
            try:
                _log("→ Zweitversuch: bpy.ops.clip.clean_error('EXEC_DEFAULT')")
                result = bpy.ops.clip.clean_error('EXEC_DEFAULT')
                _log(f"   Ergebnis: {result}")
            except Exception as e2:
                _log(f"❌ Auch Zweitversuch fehlgeschlagen: {e2}")
                _log(traceback.format_exc())
                self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e2}")
                return {'CANCELLED'}

        # --- Snapshot nach dem Clean ---
        after = _snapshot_tracks(clip)
        deleted, new, changed = _diff(before, after)
        _log(f"→ Diff: deleted={len(deleted)}, new={len(new)}, changed={len(changed)}")
        _print_dict_sample("Nachher Snapshot", after, 5)

        if deleted:
            _log(f"Gelöschte Tracks ({len(deleted)}): {deleted[:15]}{' …' if len(deleted)>15 else ''}")
        if new:
            _log(f"Neue Tracks ({len(new)}): {new}")
        if changed:
            _log(f"Geänderte Tracks ({len(changed)}): {changed[:15]}{' …' if len(changed)>15 else ''}")

        # --- Abschluss ---
        _log(f"✅ CleanError erfolgreich (Action={self.action}, Threshold={self.threshold:.2f})")
        _log("──────────────────────────────────────────────────────────────")
        self.report({'INFO'}, f"CleanError abgeschlossen ({len(deleted)} gelöscht, {len(changed)} geändert)")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_operator)

if __name__ == "__main__":
    register()
