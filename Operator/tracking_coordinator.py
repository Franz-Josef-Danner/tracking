"""tracking_coordinator.py – Detect ⇒ Distanz ⇒ Count (mit Retry-Logik)
Sequenz: FIND_LOW → JUMP → DETECT → DISTANZE → COUNT → ggf. RETRY, ansonsten ENDE."""
from __future__ import annotations
import bpy

# --- Imports: Detect → Distanz → Count ---
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_basic
from ..Helper.distanze import run_distance_cleanup
from ..Helper.count import evaluate_marker_count
from ..Helper.tracker_settings import apply_tracker_settings

__all__ = ("CLIP_OT_tracking_coordinator",)

def _resolve_clip(context: bpy.types.Context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip

def _reset_margin_to_tracker_default(context: bpy.types.Context) -> None:
    """Setzt default_margin deterministisch zurück (Search-Size-Baseline)."""
    try:
        clip = _resolve_clip(context)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if not settings:
            return
        # prefer gespeicherte Tracker-Settings
        scn = context.scene
        base_margin = None
        try:
            scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=False))
            base_margin = int(scn["tco_last_tracker_settings"].get("search_size", 0)) or None
        except Exception:
            base_margin = None
        if base_margin is None and clip and getattr(clip, "size", None):
            width = int(clip.size[0])
            pattern = max(1, int(width / 100)) if width > 0 else 8
            base_margin = pattern * 2
        if base_margin is not None:
            settings.default_margin = int(base_margin)
    except Exception:
        pass

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Coordinator (Detect → Distanz → Count)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Detect→Distanz→Count)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # 1) Low-Marker-Frame bestimmen (API liefert ein Dict)
        def _clip_bounds():
            clip = _resolve_clip(context)
            scn = context.scene
            if not clip:
                return int(getattr(scn, "frame_start", 1)), int(getattr(scn, "frame_end", 1))
            try:
                c_start = int(getattr(clip, "frame_start", 1))
                c_dur   = int(getattr(clip, "frame_duration", 0))
                c_end   = c_start + max(0, c_dur - 1)
            except Exception:
                c_start = int(getattr(scn, "frame_start", 1))
                c_end   = int(getattr(scn, "frame_end", c_start))
            # Szene begrenzt zusätzlich
            c_start = max(c_start, int(getattr(scn, "frame_start", c_start)))
            c_end   = min(c_end,   int(getattr(scn, "frame_end",   c_end)))
            return c_start, c_end

        def _fallback_frame():
            scn = context.scene
            start, end = _clip_bounds()
            cur = int(getattr(scn, "frame_current", start))
            return min(max(cur, start), end)

        res_low = None
        try:
            res_low = run_find_low_marker_frame(context)
        except Exception:
            res_low = None
        frame = None
        if isinstance(res_low, dict):
            if res_low.get("status") == "FOUND":
                frame = int(res_low.get("frame"))
            else:
                frame = _fallback_frame()
        else:
            try:
                frame = int(res_low)
            except Exception:
                frame = _fallback_frame()

        # 2) Springen
        try:
            run_jump_to_frame(context, frame=frame)
        except Exception as exc:
            self.report({'ERROR'}, f"Jump fehlgeschlagen: {exc}")
            return {'CANCELLED'}

        # 3) Detect → Distanz → Count mit Retry
        scn = context.scene
        max_retries = int(scn.get("detect_max_retries", 8))
        attempt = 0

        def _collect_new_ptrs_after_cleanup(pre_ptrs: set[int], frame_i: int) -> set[int]:
            """Neue, am Frame verbleibende Tracks (unabhängig von Selektion)."""
            clip = _resolve_clip(context)
            if not clip:
                return set()
            new_set: set[int] = set()
            for tr in clip.tracking.tracks:
                try:
                    ptr = int(tr.as_pointer())
                    if ptr in pre_ptrs:
                        continue
                    try:
                        m = tr.markers.find_frame(int(frame_i), exact=True)
                    except TypeError:
                        m = tr.markers.find_frame(int(frame_i))
                    if not m:
                        continue
                    if getattr(m, "mute", False) or getattr(tr, "mute", False):
                        continue
                    new_set.add(ptr)
                except Exception:
                    continue
            return new_set

        while True:
            # 3a) DETECT (nutze run_detect_basic, liefert pre_ptrs/new_count_raw)
            try:
                res = run_detect_basic(context, start_frame=frame, repeat_count=attempt)
            except Exception as exc:
                self.report({'ERROR'}, f"Detect fehlgeschlagen: {exc}")
                return {'CANCELLED'}
            if not isinstance(res, dict) or res.get("status") != "READY":
                self.report({'ERROR'}, f"Detect nicht READY: {res!r}")
                return {'CANCELLED'}

            pre_ptrs = set(int(p) for p in (res.get("pre_ptrs") or []))

            # 3b) DISTANZE (bereinigt neue Marker zu nah an alten)
            try:
                _ = run_distance_cleanup(
                    context,
                    pre_ptrs=pre_ptrs,
                    frame=int(res.get("frame", frame)),
                    min_distance=None,              # auto aus Threshold ableiten
                    distance_unit="pixel",
                    require_selected_new=True,
                    include_muted_old=False,
                    select_remaining_new=True,
                    verbose=True,
                )
            except Exception as exc:
                self.report({'ERROR'}, f"Distanz-Cleanup fehlgeschlagen: {exc}")
                return {'CANCELLED'}

            # 3c) COUNT (entscheidet Retry)
            new_ptrs_after = _collect_new_ptrs_after_cleanup(pre_ptrs, int(res.get("frame", frame)))
            count_res = evaluate_marker_count(new_ptrs_after_cleanup=new_ptrs_after)
            status = str(count_res.get("status", "ENOUGH"))

            # Optional: Margin zurücksetzen, um Seiteneffekte zu minimieren
            _reset_margin_to_tracker_default(context)

            if status == "ENOUGH":
                self.report({'INFO'},
                            f"OK @f{frame}: {count_res.get('count')}/{count_res.get('min')}-{count_res.get('max')} neue Tracks nach Cleanup.")
                break
            attempt += 1
            if attempt > max_retries:
                self.report({'WARNING'},
                            f"Retry-Limit erreicht ({max_retries}). Letzter Status: {status} "
                            f"({count_res.get('count')}/{count_res.get('min')}-{count_res.get('max')}).")
                break

        return {'FINISHED'}
