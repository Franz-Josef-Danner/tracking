import bpy
from typing import List, Tuple, Dict, Optional, Callable
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kalibriert automatisch die Schwellenwerte für Bewegungsmodelle
    via einseitiger Abwärtssuche (Start->Untergrenze) mit Zielwert aus Kurztest.
    - Kein bidirektionales Suchen.
    - Kein zweiter Durchlauf pro Stufe.
    - Doppel-Threshold-Paare werden kombiniert getestet.
    """
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Einseitige Downward-Search mit Zielwert aus Kurztest; unterstützt Einzel- und Doppel-Thresholds."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging während der Kalibrierung",
    )

    # Globale Klammern
    MIN_THRESHOLD: float = 1e-8
    MAX_THRESHOLD: float = 1.0

    # Einzel-Thresholds (werden einzeln getestet)
    _single_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_perspective_thresh",
    ]

    # Doppel-Threshold-Paare (werden kombiniert getestet)
    _pair_props = [
        ("kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max"),
        ("kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"),
    ]

    # Downward-Search Schrittstrategie (relativ multiplikativ)
    # = nur nach unten, grob -> fein; keine Gegenrichtung
    _down_steps = [0.05, 0.2, 0.5, 0.7, 0.9, 0.99]  # multiplikative Faktoren

    # ----------------------------------------------------
    # Utilities / Logging
    # ----------------------------------------------------
    def _round(self, v: float, decimals: int = 8) -> float:
        return round(float(v), decimals)

    def _clip_set(self, scene, prop: str, value: float) -> float:
        v = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(value)))
        setattr(scene, prop, self._round(v))
        scene.update_tag()
        if self.verbose:
            print(f"[Kaiserlich Tracker][AutoCalibrate] SET {prop}={getattr(scene, prop):.8f}")
        return getattr(scene, prop)

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # ----------------------------------------------------
    # Tracking-Durchlauf (detektieren + tracken + messen)
    # ----------------------------------------------------
    def _detect_track_length(self, context, start_frame: int) -> int:
        clip = context.space_data.clip
        tracking = clip.tracking

        old_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        # Detektion (angepasster Operator deines Add-ons)
        bpy.ops.kaiserlich_tracker.detect_adapt()

        # nur neu hinzugekommene Tracks selektieren
        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        for tr in tracking.tracks:
            tr.select = (tr.name in new_names)

        # tracken (0 = gesamte Sequenz)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)

        # Länge messen
        length = get_total_track_length(context, start_frame)

        # Aufräumen
        delete_tracks_by_names(context, new_names)
        return length

    # ----------------------------------------------------
    # Kurztest – generiert Zielwert (target_length)
    # Einzel-Property: vergleicht MIN vs. 1.0
    # ----------------------------------------------------
    def _short_test_single(self, context, start_frame: int, prop: str) -> Tuple[bool, int]:
        """Return (is_improvement, target_length)."""
        scene = context.scene

        # Neutral
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop, 1.0)
        length_neutral = self._detect_track_length(context, start_frame)
        self._log(f"[Kurztest][{prop}] neutral@1.0 -> {length_neutral}")

        # Min
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop, self.MIN_THRESHOLD)
        length_min = self._detect_track_length(context, start_frame)
        self._log(f"[Kurztest][{prop}] min@{self.MIN_THRESHOLD} -> {length_min}")

        # Zielwert = besserer der beiden – aber nur, wenn Min besser als Neutral
        if length_min > length_neutral:
            target = length_min
            self._log(f"[Kurztest][{prop}] IMPROVEMENT -> target={target}")
            return True, target
        else:
            self._log(f"[Kurztest][{prop}] NO IMPROVEMENT")
            return False, length_neutral

    # ----------------------------------------------------
    # Kurztest – generiert Zielwert (target_length)
    # Paar: beide bei 1.0 vs. beide bei MIN; Zielwert aus MIN-Fall
    # ----------------------------------------------------
    def _short_test_pair(self, context, start_frame: int, prop_a: str, prop_b: str) -> Tuple[bool, int]:
        scene = context.scene

        # Neutral (beide 1.0)
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, 1.0)
        self._clip_set(scene, prop_b, 1.0)
        length_neutral = self._detect_track_length(context, start_frame)
        self._log(f"[Kurztest][{prop_a},{prop_b}] neutral (1.0/1.0) -> {length_neutral}")

        # Min (beide MIN)
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, self.MIN_THRESHOLD)
        self._clip_set(scene, prop_b, self.MIN_THRESHOLD)
        length_min = self._detect_track_length(context, start_frame)
        self._log(f"[Kurztest][{prop_a},{prop_b}] min ({self.MIN_THRESHOLD}/{self.MIN_THRESHOLD}) -> {length_min}")

        if length_min > length_neutral:
            target = length_min
            self._log(f"[Kurztest][{prop_a},{prop_b}] IMPROVEMENT -> target={target}")
            return True, target
        else:
            self._log(f"[Kurztest][{prop_a},{prop_b}] NO IMPROVEMENT")
            return False, length_neutral

    # ----------------------------------------------------
    # Haupttest – Downward-Search (einseitig, stufenweise)
    # Abbruchkriterium: target_length erreicht/überboten
    # Startpunkt: initial 1.0 (oder vom Aufrufer vorgegeben)
    # Wird Ziel erreicht -> aktueller Threshold => neuer min threshold;
    #                       vorheriger Wert    => neuer Startpunkt.
    # Wenn Untergrenze erreicht ohne Treffer -> reset auf Start, nächste Stufe.
    # ----------------------------------------------------
    def _downward_search_single(
        self,
        context,
        start_frame: int,
        prop: str,
        target_length: int,
        initial_start: float = 1.0,
    ) -> Tuple[float, float, bool, int]:
        """
        Return (new_min_threshold, new_start_value, hit, best_found_length).
        hit=True, wenn target erreicht/überboten.
        """
        scene = context.scene
        current = initial_start
        prev_value = current
        best_length = -1

        # Setze Startwert
        self._clip_set(scene, prop, current)

        for f in self._down_steps:
            # "Stufe": multiplikative Reduktion bis MIN
            while True:
                next_value = self._round(current * f)
                if next_value < self.MIN_THRESHOLD:
                    next_value = self.MIN_THRESHOLD

                # Abbruch, wenn keine Änderung mehr möglich
                if next_value == current:
                    break

                self._clip_set(scene, prop, next_value)
                reset_to_frame(context, start_frame)
                length = self._detect_track_length(context, start_frame)
                self._log(f"[Haupttest][{prop}] {current:.8f} -> {next_value:.8f} | length={length}")

                # best_length/wachsendes Ziel
                if length > best_length:
                    best_length = length

                # Regel: wenn höher als aktuelles Ziel, Ziel wird angehoben
                if length > target_length:
                    target_length = length
                    self._log(f"[Haupttest][{prop}] NEW TARGET -> {target_length}")

                # Ziel erreicht/überboten?
                if length >= target_length:
                    # Aktueller Threshold wird neuer min threshold,
                    # vorheriger Wert wird neuer Startwert
                    new_min = next_value
                    new_start = prev_value
                    self._log(f"[Haupttest][{prop}] HIT -> new_min={new_min:.8f} new_start={new_start:.8f}")
                    return new_min, new_start, True, best_length

                # Weiter nach unten
                prev_value = current
                current = next_value

                # Untergrenze erreicht, ohne Treffer -> Stufe beenden
                if current <= self.MIN_THRESHOLD:
                    self._log(f"[Haupttest][{prop}] REACHED MIN without hit (stufe end)")
                    break

        # Kein Treffer
        return self.MIN_THRESHOLD, initial_start, False, best_length

    # ----------------------------------------------------
    # Haupttest – Downward-Search (kombiniert für Paare)
    # Beide werden synchron reduziert. Zielwertmanagement wie oben.
    # ----------------------------------------------------
    def _downward_search_pair(
        self,
        context,
        start_frame: int,
        prop_a: str,
        prop_b: str,
        target_length: int,
        start_a: float = 1.0,
        start_b: float = 1.0,
    ) -> Tuple[Tuple[float, float], Tuple[float, float], bool, int]:
        """
        Return ((new_min_a, new_min_b), (new_start_a, new_start_b), hit, best_found_length).
        """
        scene = context.scene
        cur_a, cur_b = start_a, start_b
        prev_a, prev_b = cur_a, cur_b
        best_length = -1

        self._clip_set(scene, prop_a, cur_a)
        self._clip_set(scene, prop_b, cur_b)

        for f in self._down_steps:
            while True:
                next_a = self._round(cur_a * f)
                next_b = self._round(cur_b * f)
                if next_a < self.MIN_THRESHOLD: next_a = self.MIN_THRESHOLD
                if next_b < self.MIN_THRESHOLD: next_b = self.MIN_THRESHOLD

                if next_a == cur_a and next_b == cur_b:
                    break

                self._clip_set(scene, prop_a, next_a)
                self._clip_set(scene, prop_b, next_b)

                reset_to_frame(context, start_frame)
                length = self._detect_track_length(context, start_frame)
                self._log(f"[Haupttest][{prop_a},{prop_b}] "
                          f"({cur_a:.8f},{cur_b:.8f})->({next_a:.8f},{next_b:.8f}) | length={length}")

                if length > best_length:
                    best_length = length

                if length > target_length:
                    target_length = length
                    self._log(f"[Haupttest][{prop_a},{prop_b}] NEW TARGET -> {target_length}")

                if length >= target_length:
                    new_min_a, new_min_b = next_a, next_b
                    new_start_a, new_start_b = prev_a, prev_b
                    self._log(f"[Haupttest][{prop_a},{prop_b}] HIT -> "
                              f"new_min=({new_min_a:.8f},{new_min_b:.8f}) "
                              f"new_start=({new_start_a:.8f},{new_start_b:.8f})")
                    return (new_min_a, new_min_b), (new_start_a, new_start_b), True, best_length

                prev_a, prev_b = cur_a, cur_b
                cur_a, cur_b = next_a, next_b

                if (cur_a <= self.MIN_THRESHOLD) and (cur_b <= self.MIN_THRESHOLD):
                    self._log(f"[Haupttest][{prop_a},{prop_b}] REACHED MIN without hit (stufe end)")
                    break

        return (self.MIN_THRESHOLD, self.MIN_THRESHOLD), (start_a, start_b), False, best_length

    # ----------------------------------------------------
    # rot_thresh_y aus x & Clip-Seitenverhältnis ableiten (wie bisher)
    # ----------------------------------------------------
    def _auto_set_rot_thresh_y(self, context):
        scene = getattr(context, "scene", None) or bpy.context.scene
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)

        if clip is None:
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for sp in area.spaces:
                            if sp.type == 'CLIP_EDITOR' and getattr(sp, "clip", None):
                                clip = sp.clip
                                break
                    if clip:
                        break
                if clip:
                    break

        if clip is None or not hasattr(clip, "size"):
            return

        if not hasattr(scene, "kaiserlich_rot_thresh_x"):
            return

        ha, va = clip.size
        if not va:
            return

        rx = float(getattr(scene, "kaiserlich_rot_thresh_x"))
        ry = min(1.0, self._round(rx * (ha / va)))
        setattr(scene, "kaiserlich_rot_thresh_y", ry)
        scene.update_tag()

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()

        if self.verbose:
            print(f"[Kaiserlich Tracker][AutoCalibrate] SET kaiserlich_rot_thresh_y={ry:.8f}")

    # ----------------------------------------------------
    # Execute
    # ----------------------------------------------------
    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

        # Auswahl sichern/neutralisieren
        selected_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = (tr.name in selected_names)

        start_frame = get_start_frame(context)

        # Init: alle bekannten Properties auf 1.0 (falls vorhanden)
        all_props = set(self._single_props)
        for a, b in self._pair_props:
            all_props.add(a); all_props.add(b)
        for p in all_props:
            if hasattr(scene, p):
                self._clip_set(scene, p, 1.0)

        # Baseline (nur Info)
        reset_to_frame(context, start_frame)
        baseline_length = self._detect_track_length(context, start_frame)
        self._log(f"[Baseline] length={baseline_length}")

        # ---------------------------
        # Einzel-Properties
        # ---------------------------
        for prop in self._single_props:
            if not hasattr(scene, prop):
                continue

            # Kurztest -> Zielwert
            improvement, target_length = self._short_test_single(context, start_frame, prop)
            if not improvement:
                # Kein Haupttest, nächstes Property
                continue

            # Haupttest (Downward-Search)
            new_min, new_start, hit, _ = self._downward_search_single(
                context=context,
                start_frame=start_frame,
                prop=prop,
                target_length=target_length,
                initial_start=1.0,
            )

            # Ergebnis festschreiben (gemäß Regelwerk)
            if hit:
                # min threshold = Treffer; Startpunkt = Wert davor
                self._clip_set(scene, prop, new_min)        # hält min für nächste Runde fest (optional)
                # Startpunkt nur „merken“? – hier als Setzen auf new_start, damit Folge-Tests davon ausgehen könnten
                self._clip_set(scene, prop, new_start)      # Startpunkt zurücksetzen
            else:
                # Kein Treffer: zurück auf Startpunkt für nächste Stufe (hier: 1.0)
                self._clip_set(scene, prop, 1.0)

        # ---------------------------
        # Paare (kombiniert)
        # ---------------------------
        for prop_a, prop_b in self._pair_props:
            if not (hasattr(scene, prop_a) and hasattr(scene, prop_b)):
                continue

            improvement, target_length = self._short_test_pair(context, start_frame, prop_a, prop_b)
            if not improvement:
                continue

            (new_min_a, new_min_b), (new_start_a, new_start_b), hit, _ = self._downward_search_pair(
                context=context,
                start_frame=start_frame,
                prop_a=prop_a,
                prop_b=prop_b,
                target_length=target_length,
                start_a=1.0,
                start_b=1.0,
            )

            if hit:
                # min thresholds setzen
                self._clip_set(scene, prop_a, new_min_a)
                self._clip_set(scene, prop_b, new_min_b)
                # Startpunkte zurücksetzen (Wert davor)
                self._clip_set(scene, prop_a, new_start_a)
                self._clip_set(scene, prop_b, new_start_b)
            else:
                # kein Treffer: auf Start zurück
                self._clip_set(scene, prop_a, 1.0)
                self._clip_set(scene, prop_b, 1.0)

        # Cleanup/Restore
        reset_to_frame(context, start_frame)
        _restore_selection()

        # rot_thresh_y automatisch aus x ableiten
        self._auto_set_rot_thresh_y(context)

        self.report({'INFO'}, "Auto-Calibrate (Downward-Search) abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()
