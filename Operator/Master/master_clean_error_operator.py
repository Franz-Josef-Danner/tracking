# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty


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

    sort_desc: BoolProperty(
        name="Sort descending",
        description="Sortiere absteigend nach Error (höchste zuerst)",
        default=True
    )

    # ------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------
    def _get_track_error(self, track) -> float | None:
        """Versucht Solve Error oder Marker-Fehler zu ermitteln."""
        for name in ("average_error", "error", "solve_error", "reprojection_error"):
            val = getattr(track, name, None)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    pass
        # Fallback: Durchschnitt aus Marker.errors
        try:
            vals = [float(m.error) for m in track.markers if hasattr(m, "error")]
            return sum(vals) / len(vals) if vals else None
        except Exception:
            return None

    def _write_blender_textlog(self, lines: list[str]):
        name = "Kaiserlich_SolveError_Log"
        txt = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        txt.clear()
        for ln in lines:
            txt.write(ln + "\n")

    # ------------------------------------------------------------
    # Hauptausführung
    # ------------------------------------------------------------
    def execute(self, context):
        scene = context.scene
        clip = _find_active_clip(context)
        if clip is None:
            self.report({'ERROR'}, "Kein Clip gefunden.")
            return {'CANCELLED'}

        tracks = getattr(clip.tracking, "tracks", None)
        if not tracks:
            self.report({'ERROR'}, "Keine Tracking-Tracks im Clip.")
            return {'CANCELLED'}

        results = []
        for t in tracks:
            err = self._get_track_error(t)
            results.append({
                "name": t.name,
                "error": err,
                "track": t,
                "length": len(t.markers)
            })

        # Sortieren
        results.sort(
            key=lambda r: (r["error"] is None, -r["error"] if r["error"] else 0.0)
            if self.sort_desc else
            (r["error"] is None, r["error"] if r["error"] else 0.0)
        )

        # Durchschnittsfehler
        valid = [r["error"] for r in results if r["error"] is not None]
        avg_error = sum(valid) / len(valid) if valid else None
        max_error_value = getattr(scene, "max_error_value", None)
        lines = []
        header = f"[Kaiserlich][SolveError] Clip='{clip.name}' — {len(results)} Tracks"
        lines.append(header)
        print(header)

        for r in results:
            name = r["name"]
            err = r["error"]
            length = r["length"]
            line = f"[SolveError] {name:40s} len={length:4d} avg_err={err if err is not None else '<n/a>'}"
            lines.append(line)
            print(line)

        lines.append("-" * 70)

        if avg_error is None or max_error_value is None:
            lines.append("[Summary] Kein gültiger Durchschnitt oder Max error Value gefunden.")
            self._write_blender_textlog(lines)
            self.report({'WARNING'}, "Keine gültigen Werte für Vergleich.")
            return {'FINISHED'}

        # Vergleich + ggf. Löschung
        if avg_error > max_error_value:
            limit = avg_error * 2.0
            lines.append(f"[Summary] ⛔ Durchschnitt {avg_error:.4f} > Max {max_error_value:.4f}")
            lines.append(f"[Summary] Löschgrenze = Durchschnitt * 2 = {limit:.4f}")
           
            # --- Verwendung des bestehenden Helpers delete_track_by_name ---
            try:
                from ...Helper.delete import delete_track_by_name
            except Exception as e:
                self.report({'ERROR'}, f"Helper delete_track_by_name konnte nicht importiert werden: {e}")
                return {'CANCELLED'}

            delete_count = 0
            for r in results:
                if r["error"] is not None and r["error"] > limit:
                    ok = False
                    try:
                        ok = delete_track_by_name(context, r["name"])
                    except Exception as e:
                        msg = f"[Delete][ERROR] {r['name']} → {e}"
                        lines.append(msg)
                        print(msg)

                    if ok:
                        delete_count += 1
                        msg = f"[Delete] ❌ {r['name']} (Error {r['error']:.4f} > {limit:.4f})"
                        lines.append(msg)
                        print(msg)
                    else:
                        msg = f"[Delete][SKIP] {r['name']} konnte nicht gelöscht werden."
                        lines.append(msg)
                        print(msg)

            lines.append(f"[Summary] → {delete_count} Tracks gelöscht.")
            print(f"[Summary] → {delete_count} Tracks gelöscht.")

        else:
            lines.append(f"[Summary] ✅ Durchschnitt {avg_error:.4f} ≤ Max {max_error_value:.4f}")
            lines.append("[Summary] Keine Tracks gelöscht.")
            print(f"[Summary] Durchschnitt {avg_error:.4f} ≤ Max {max_error_value:.4f} — keine Aktion.")

        # Log speichern
        self._write_blender_textlog(lines)
        self.report({'INFO'}, "Solve Error Analyse abgeschlossen.")

        # ------------------------------------------------------------
        # 🧩 Nach Abschluss direkt an MasterCycle übergeben
        # ------------------------------------------------------------
        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            self.report({'INFO'}, "Übergabe an MasterCycleOperator gestartet.")
        except Exception as e:
            self.report({'ERROR'}, f"Fehler bei Übergabe an MasterCycleOperator: {e}")

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
