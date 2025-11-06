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
    bl_idname = "kaiserlich_tracker.list_tracks_by_solve_error"
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
        """
        Versucht mehrere mögliche Quellen für einen 'solve error' zu lesen.
        Falls kein direkter Wert vorhanden ist, werden Marker-errors gemittelt (falls vorhanden).
        Wenn nichts gefunden wird, None zurückgeben.
        """
        # mögliche Property-Namen prüfen (häufige Bezeichnungen / Fallbacks)
        candidates = ("average_error", "error", "solve_error", "reprojection_error")
        for name in candidates:
            val = getattr(track, name, None)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    pass

        # Fallback: Mittelwert über marker-Fehler (falls Marker.error existiert)
        try:
            markers = getattr(track, "markers", None)
            if markers and len(markers) > 0:
                vals = []
                for m in markers:
                    v = getattr(m, "error", None)
                    if v is not None:
                        try:
                            vals.append(float(v))
                        except Exception:
                            pass
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
        # Clear existing content
        txt.clear()
        for ln in lines:
            txt.write(ln + "\n")

    def execute(self, context):
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
                "track": t
            })

        # Filter nach Threshold
        if self.filter_mode == 'ABOVE':
            results = [r for r in results if r["error"] is not None and r["error"] >= self.threshold]
        elif self.filter_mode == 'BELOW':
            results = [r for r in results if r["error"] is not None and r["error"] <= self.threshold]

        # Sortieren (Tracks mit None-Error an Ende)
        results.sort(key=lambda r: (r["error"] is None, -r["error"] if r["error"] is not None else 0.0) if self.sort_desc else (r["error"] is None, r["error"] if r["error"] is not None else 0.0))

        # Log-Ausgabe (Konsole + Report + Blender Textblock)
        lines = []
        header = f"[Kaiserlich][ListTracksBySolveError] Clip='{clip.name}' — Tracks: {len(results)} (Total in Clip: {len(tracks)})"
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

        # Schreibe in Blender Text-Editor zur Persistenz
        self._write_blender_textlog(lines)

        # Kurze Rückmeldung im UI
        self.report({'INFO'}, f"Tracks geloggt ({len(results)}) — Text: Kaiserlich_SolveError_Log")
        return {'FINISHED'}
