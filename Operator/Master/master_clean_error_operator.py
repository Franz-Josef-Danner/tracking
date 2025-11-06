# kaiserlich_list_tracks_by_solve_error.py
import bpy
from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty, EnumProperty

def _find_active_clip(context: bpy.types.Context):
    """Sucht zuerst Clip im Clip-Editor, fallback auf active strip (Sequencer)."""
    clip = None
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'CLIP_EDITOR':
                space = area.spaces.active
                if space and getattr(space, "clip", None):
                    return space.clip
    # fallback: sequencer active strip (wenn vorhanden)
    scene = context.scene
    if hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and getattr(strip, "clip", None):
            return strip.clip
    return None

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Listet alle Tracks und deren Solve/Error-Werte und schreibt ein Log"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Kaiserlich: List Tracks by Solve Error"
    bl_options = {'REGISTER', 'INTERNAL'}

    threshold: FloatProperty(
        name="Threshold",
        description="Nur Tracks mit Error >= Threshold zeigen (0 = alle)",
        default=0.0,
        precision=4
    )
    filter_mode: EnumProperty(
        name="Filter Mode",
        description="Wie Threshold angewendet wird",
        items=[
            ('NONE', "Keine Filterung", "Alle Tracks zeigen"),
            ('ABOVE', ">= Threshold", "Nur Tracks mit Error >= Threshold"),
            ('BELOW', "<= Threshold", "Nur Tracks mit Error <= Threshold"),
        ],
        default='NONE'
    )
    sort_desc: BoolProperty(
        name="Sort descending",
        description="Sortiere absteigend nach Error (höchste zuerst)",
        default=True
    )

    def _get_track_error(self, track) -> float | None:
        """Ermittelt den Solve Error eines Tracks über verschiedene Quellen."""
        candidates = ("average_error", "error", "solve_error", "reprojection_error")
        for name in candidates:
            val = getattr(track, name, None)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    pass

        # Fallback: Mittelwert über Marker-Fehler
        try:
            markers = getattr(track, "markers", None)
            if markers and len(markers) > 0:
                vals = []
                for m in markers:
                    v = getattr(m, "error", None)
                    if v is not None:
                        vals.append(float(v))
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass
        return None

    def _write_blender_textlog(self, lines: list[str]):
        name = "Kaiserlich_SolveError_Log"
        txt = bpy.data.texts.get(name)
        if txt is None:
            txt = bpy.data.texts.new(name)
        txt.clear()
        for ln in lines:
            txt.write(ln + "\n")

    def execute(self, context):
        scene = context.scene
        clip = _find_active_clip(context)
        if clip is None:
            self.report({'ERROR'}, "Kein Clip gefunden (Clip Editor oder Sequencer).")
            return {'CANCELLED'}

        tracks = getattr(clip.tracking, "tracks", None)
        if not tracks:
            self.report({'ERROR'}, "Clip enthält keine Tracking-Tracks.")
            return {'CANCELLED'}

        results = []
        for t in tracks:
            err = self._get_track_error(t)
            length = len(getattr(t, "markers", []))
            results.append({
                "name": t.name,
                "error": err,
                "length": length,
            })

        # Filter
        if self.filter_mode == 'ABOVE':
            results = [r for r in results if r["error"] is not None and r["error"] >= self.threshold]
        elif self.filter_mode == 'BELOW':
            results = [r for r in results if r["error"] is not None and r["error"] <= self.threshold]

        # Sortieren
        results.sort(
            key=lambda r: (r["error"] is None, -r["error"] if r["error"] is not None else 0.0)
            if self.sort_desc else
            (r["error"] is None, r["error"] if r["error"] is not None else 0.0)
        )

        # Durchschnittsberechnung
        valid_errors = [r["error"] for r in results if r["error"] is not None]
        avg_error = sum(valid_errors) / len(valid_errors) if valid_errors else None
        max_error_value = getattr(scene, "max_error_value", None)

        # Vergleichslogik
        comparison = ""
        if avg_error is not None and max_error_value is not None:
            if avg_error > max_error_value:
                comparison = f"⛔ Durchschnittsfehler {avg_error:.4f} > Max {max_error_value:.4f} — Grenzwert überschritten"
            else:
                comparison = f"✅ Durchschnittsfehler {avg_error:.4f} ≤ Max {max_error_value:.4f} — innerhalb Grenzwert"
        elif avg_error is not None:
            comparison = f"ℹ Durchschnittsfehler {avg_error:.4f} (kein Max error Value in Szene definiert)"
        else:
            comparison = "⚠ Keine gültigen Error-Werte gefunden."

        # Log-Ausgabe
        lines = []
        header = f"[Kaiserlich][SolveError] Clip='{clip.name}' — {len(results)} Tracks (Total im Clip: {len(tracks)})"
        lines.append(header)
        print(header)

        for r in results:
            name = r["name"]
            length = r["length"]
            err = r["error"]
            if err is None:
                line = f"[SolveError] {name:40s} len={length:4d} avg_err= <n/a>"
            else:
                line = f"[SolveError] {name:40s} len={length:4d} avg_err={err:8.4f}"
            lines.append(line)
            print(line)

        # Durchschnittsergebnis
        lines.append("-" * 70)
        if avg_error is not None:
            lines.append(f"[Summary] Durchschnittlicher Solve Error: {avg_error:.4f}")
        else:
            lines.append("[Summary] Kein gültiger Solve Error berechnet.")
        if max_error_value is not None:
            lines.append(f"[Summary] Max error Value (Scene): {max_error_value:.4f}")
        lines.append(f"[Summary] Vergleich: {comparison}")
        print("-" * 70)
        print(comparison)

        # Log in Text-Block schreiben
        self._write_blender_textlog(lines)

        # UI Info
        self.report({'INFO'}, f"Tracks geloggt, Durchschnitt: {avg_error:.4f}" if avg_error else "Keine gültigen Errors gefunden.")
        return {'FINISHED'}


# Registrierung
classes = (KAISERLICHTRACKER_OT_clean_error_operator,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
