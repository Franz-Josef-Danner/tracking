import bpy
from typing import Tuple, Optional, Union, List
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Threshold-Kalibrierung gemäß Kurztest/Haupttest-Algorithmus mit sf-/Gate-Logik"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Algorithmus: Kurztest → Haupttest mit deterministischer Stufensteuerung (sf) und Gates."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Minimalistische Logs für Threshold-Test, Segmentlänge, sf und aktive Stufe"
    )

    # numerische Konstanten
    MIN_THRESHOLD: float = 1e-8
    MAX_THRESHOLD: float = 1.0
    EPS: float = 1e-9
    SF_START: float = 140.0
    SF_MIN: float = 1.0

    # ——————————————————————————————————————————————————————————————
    # Helper: Low-Level
    # ——————————————————————————————————————————————————————————————
    def _round(self, v: float, decimals: int = 8) -> float:
        return round(float(v), decimals)

    def _clip(self, v: float) -> float:
        return max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(v)))

    def _clip_set_prop(self, scene, prop: str, value: float) -> float:
        v = self._round(self._clip(value))
        setattr(scene, prop, v)
        scene.update_tag()
        return v

    def _detect_and_track(self, context):
        # Snapshot neue Marker ermitteln, dann detekten & tracken, danach neue Tracks wieder löschen
        clip = context.space_data.clip
        tracking = clip.tracking
        old_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        bpy.ops.kaiserlich_tracker.detect_adapt()
        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        for tr in tracking.tracks:
            tr.select = (tr.name in new_names)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        return new_names

    def _segment_laenge(self, context, start_frame: int) -> int:
        return get_total_track_length(context, start_frame)

    def _detect_track_measure(self, context, start_frame: int) -> int:
        new_names = self._detect_and_track(context)
        length = self._segment_laenge(context, start_frame)
        delete_tracks_by_names(context, new_names)
        return length

    # ——————————————————————————————————————————————————————————————
    # Helper: Threshold-Wrapper (ths)
    # ——————————————————————————————————————————————————————————————
    class _THS:
        """Kapselt Zugriffe auf Scene-Properties und erlaubt generische Set/Get für single/pair Items."""
        def __init__(self, op_ref, context):
            self._op = op_ref
            self._context = context
            self.scene = context.scene
            # generische Slots aus der Vorlage (werden pro Item gemappt):
            self.thresh_alle = 1.0
            self.thresh1 = 1.0
            self.thresh2 = 1.0
            self.thresh = 1.0

        # Mappings für das gerade aktive Item
        def bind_single(self, name: str):
            self._mode = "SINGLE"
            self._a = name
            self._b = None

        def bind_pair(self, a: str, b: str):
            self._mode = "PAIR"
            self._a = a
            self._b = b

        # Write convenience
        def write_single(self, v: float):
            self._op._clip_set_prop(self.scene, self._a, v)

        def write_pair(self, v1: float, v2: float):
            self._op._clip_set_prop(self.scene, self._a, v1)
            self._op._clip_set_prop(self.scene, self._b, v2)

        # Read convenience
        def read_single(self) -> float:
            return float(getattr(self.scene, self._a))

        def read_pair(self) -> Tuple[float, float]:
            return float(getattr(self.scene, self._a)), float(getattr(self.scene, self._b))

    # ——————————————————————————————————————————————————————————————
    # Execute: Neuer Algorithmus (Kurztest/Haupttest)
    # ——————————————————————————————————————————————————————————————
    def execute(self, context: bpy.types.Context):
        # Grundchecks
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

        # Auswahl konservieren & deselektieren (wie zuvor)
        selected = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore():
            for tr in tracking.tracks:
                tr.select = (tr.name in selected)

        # Startpunkt (st) aus Helper
        st = get_start_frame(context)
        reset_to_frame(context, st)

        # --- Variablen analog Vorlage ---
        eg: Optional[float] = None         # End Gate (Marker, kein direkter Scene-Wert)
        th: Optional[float] = None         # zuletzt gesetzter Threshold-Wert des aktiven Items
        za: float = float("-inf")          # globaler Zielwert (best length)
        sf: float = self.SF_START          # aktuelle Stufe
        sl: int = 0                        # letzte Segmentlänge (Info/Log)
        min_threshold: float = self.MIN_THRESHOLD
        EPS: float = self.EPS
        sf_min: float = self.SF_MIN

        # THS-Wrapper
        ths = self._THS(self, context)

        # Threshold-Liste aus Szene ermitteln (nur existierende Props verwenden)
        def _has(p): return hasattr(context.scene, p)

        seq: List[Union[Tuple[str, str, str], Tuple[str, str]]] = []
        # Reihenfolge gemäß Vorgabe:
        if _has("kaiserlich_rot_thresh_x"):
            seq.append(("SINGLE", "kaiserlich_rot_thresh_x"))
        if _has("kaiserlich_scale_thresh_min") and _has("kaiserlich_scale_thresh_max"):
            seq.append(("PAIR", "kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max"))
        if _has("kaiserlich_rot_scale_thresh_rot") and _has("kaiserlich_rot_scale_thresh_scale"):
            seq.append(("PAIR", "kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"))
        if _has("kaiserlich_perspective_thresh"):
            seq.append(("SINGLE", "kaiserlich_perspective_thresh"))

        thresh_count = len(seq)
        thresh_idx = 0

        # Standard-Init (alle auf 1)
        for item in seq:
            if item[0] == "SINGLE":
                self._clip_set_prop(context.scene, item[1], 1.0)
            else:
                self._clip_set_prop(context.scene, item[1], 1.0)
                self._clip_set_prop(context.scene, item[2], 1.0)

        # Hilfsfunktionen für Kurztest/Haupttest
        def _detect_track_len() -> int:
            reset_to_frame(context, st)
            return self._detect_track_measure(context, st)

        def _bind_item():
            nonlocal th
            item = seq[thresh_idx]
            if item[0] == "SINGLE":
                ths.bind_single(item[1])
                th = ths.read_single()
            else:
                ths.bind_pair(item[1], item[2])
                a, b = ths.read_pair()
                th = a  # definieren „th“ als primären aktuellen Schreibwert (kontextabhängig)
            return item

        # ---------------- KURZTEST ----------------
        def kurztest() -> Tuple[bool, float, Optional[float]]:
            """Rückgabe: (improved, z_candidate, eg_candidate)"""
            item = seq[thresh_idx]

            # Erstmessung (alle Werte aktuell)
            sl1 = _detect_track_len()

            # Voreinstellung für Zweittest
            if item[0] == "PAIR":
                ths.write_pair(min_threshold, min_threshold)
            else:
                ths.write_single(min_threshold)

            # Zweitmessung
            sl2 = _detect_track_len()

            if self.verbose:
                print(f"[Kurztest idx={thresh_idx}] sl1={sl1} sl2={sl2}")

            # Verbesserung?
            if sl2 > sl1 + EPS:
                local_best = sl2
                za_local = sl2
                eg_local = min_threshold

                # Sonderlogik für Position 2 (Index==2 in der Gesamtreihenfolge)
                if thresh_idx == 2 and item[0] == "PAIR":
                    # Ihre Vorgabe: thresh1=1, thresh2=min_threshold
                    ths.write_pair(1.0, min_threshold)
                else:
                    # „robust“: thresh = 1 * sf
                    if item[0] == "PAIR":
                        ths.write_pair(self._clip(1.0 * sf), self._clip(1.0 * sf))
                    else:
                        ths.write_single(self._clip(1.0 * sf))
                return True, za_local, eg_local
            else:
                return False, float(sl1), None

        # ---------------- HAUPTTEST ----------------
        def haupttest():
            nonlocal sf, za, eg, th

            item = seq[thresh_idx]
            # (Re-)Bind + aktuellen th lesen
            _bind_item()

            # Index 2: Sonderlogik
            if thresh_idx == 2 and item[0] == "PAIR":
                # Falls thresh2 ~ min_threshold => skaliere thresh1
                a, b = ths.read_pair()
                if b <= min_threshold + EPS:
                    ths.write_pair(self._clip(a * sf), b)
                    sl_probe = _detect_track_len()

                    if abs(sl_probe - za) <= EPS:
                        eg = float(ths.read_pair()[0])  # Gate auf thresh1
                        th = a
                        sf = max(sf / 2.0, sf_min)
                        if sf >= sf_min:
                            ths.write_pair(self._clip(th / sf), b)
                        return
                    else:
                        # reset + alternative Route
                        sf = self.SF_START
                        ths.write_pair(a, self._clip(1.0 * sf))
                        return
                else:
                    # normaler Vergleich
                    sl_probe = _detect_track_len()
                    if sl_probe > za + EPS:
                        za = sl_probe
                        eg = ths.read_pair()[0]
                        th = ths.read_pair()[0]
                        sf = max(sf / 2.0, sf_min)
                        if sf >= sf_min:
                            ths.write_pair(self._clip(th / sf), ths.read_pair()[1])
                    else:
                        sf = self.SF_START
                        ths.write_pair(ths.read_pair()[0], self._clip(1.0 * sf))
                    return

            # Allgemeiner Pfad (nicht Index 2)
            sl_probe = _detect_track_len()

            if abs(sl_probe - za) <= EPS:
                eg = (ths.read_pair()[0] if item[0] == "PAIR" else ths.read_single())
                th = eg
                sf = max(sf / 2.0, sf_min)
                if sf >= sf_min:
                    if item[0] == "PAIR":
                        a, b = ths.read_pair()
                        ths.write_pair(self._clip(a / sf), self._clip(b / sf))
                    else:
                        v = ths.read_single()
                        ths.write_single(self._clip(v / sf))
            elif sl_probe > za + EPS:
                za = sl_probe
                eg = (ths.read_pair()[0] if item[0] == "PAIR" else ths.read_single())
                th = eg
                sf = max(sf / 2.0, sf_min)
                if sf >= sf_min:
                    if item[0] == "PAIR":
                        a, b = ths.read_pair()
                        ths.write_pair(self._clip(a / sf), self._clip(b / sf))
                    else:
                        v = ths.read_single()
                        ths.write_single(self._clip(v / sf))
            else:
                # Keine Verbesserung
                sf = max(sf / 2.0, sf_min)

        # ——————————————————————————————————————————————
        # Hauptablauf
        # ——————————————————————————————————————————————
        while thresh_idx < thresh_count:
            improved, z_candidate, eg_candidate = kurztest()

            if improved:
                za = max(za, z_candidate)
                if eg_candidate is not None:
                    eg = eg_candidate
                sf = self.SF_START
                haupttest()
            else:
                sf = max(sf / 2.0, sf_min)
                haupttest()

            # Fortschrittskontrolle + Exit
            if sf <= sf_min + EPS:
                thresh_idx += 1
                sf = self.SF_START
            else:
                # „Nur einmal pro Runde erhöhen – Doppelinkrement entfernt“
                thresh_idx += 1

            if self.verbose:
                print(f"[Loop] idx={thresh_idx}/{thresh_count} za={za} eg={eg} sf={sf}")

        # Abschlusspflege
        reset_to_frame(context, st)
        _restore()
        self._auto_set_rot_thresh_y(context)
        self.report({'INFO'}, "Auto-Calibrate (neuer Algorithmus) abgeschlossen.")
        return {'FINISHED'}

    # ----------------------------------------------------
    # Ableitung rot_thresh_y (wie zuvor)
    # ----------------------------------------------------
    def _auto_set_rot_thresh_y(self, context):
        scene = context.scene
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
        if not clip or not hasattr(scene, "kaiserlich_rot_thresh_x"):
            return
        ha, va = clip.size
        if not va:
            return
        rx = float(getattr(scene, "kaiserlich_rot_thresh_x"))
        ry = min(1.0, self._round(rx * (ha / va)))
        setattr(scene, "kaiserlich_rot_thresh_y", ry)
        scene.update_tag()


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()