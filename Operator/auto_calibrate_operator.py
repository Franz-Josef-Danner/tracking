import bpy
from typing import Tuple, List
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Operator.detect_adapt_operator import KAISERLICHTRACKER_OT_detect_adapt
from ..Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Threshold-Scene-Variablen"""
    bl_idname = "kaiserlichttracker.auto_calibrate"
    bl_label = "Auto Calibrate Thresholds"
    bl_options = {'REGISTER', 'UNDO'}

    min_threshold: bpy.props.FloatProperty(
        name="Min Threshold",
        default=1e-8,
        description="Minimaler Grenzwert für adaptive Suche"
    )

    step_value: bpy.props.FloatProperty(
        name="Step Value",
        default=140.0,
        description="Initialer Schrittwert für Feinkalibrierung"
    )

    max_iterations: bpy.props.IntProperty(
        name="Max Iterations",
        default=20,
        description="Maximale Anzahl an Kalibrierungsiterationen"
    )

    def execute(self, context):
        self.report({'INFO'}, "Starte automatische Kalibrierung...")

        # --- Einzelne Thresholds ---
        single_thresholds = [
            'kaiserlich_rot_thresh_x',
            'kaiserlich_perspective_thresh'
        ]

        # --- Threshold-Paare (z. B. min/max, rot/scale etc.) ---
        pair_thresholds = [
            ('kaiserlich_scale_thresh_min', 'kaiserlich_scale_thresh_max'),
            ('kaiserlich_rot_scale_thresh_rot', 'kaiserlich_rot_scale_thresh_scale'),
        ]

        # === Einzelsuche ===
        for name in single_thresholds:
            if not hasattr(context.scene, name):
                self.report({'WARNING'}, f"Scene Property {name} existiert nicht, übersprungen.")
                continue

            base_value = getattr(context.scene, name)
            best_value, best_length = self._tune_single_threshold(
                context,
                name=name,
                base_value=base_value,
                min_threshold=self.min_threshold,
                initial_step=self.step_value,
                max_iter=self.max_iterations
            )
            setattr(context.scene, name, best_value)
            self.report({'INFO'}, f"{name} optimiert → {best_value:.6f} (Länge {best_length})")

        # === Paarsuche ===
        for names in pair_thresholds:
            if not all(hasattr(context.scene, n) for n in names):
                self.report({'WARNING'}, f"Mindestens eine Scene Property in {names} fehlt, übersprungen.")
                continue

            base_values = (getattr(context.scene, names[0]), getattr(context.scene, names[1]))
            best_values, best_length = self._tune_pair_threshold(
                context,
                names=names,
                base_values=base_values,
                min_threshold=self.min_threshold,
                initial_step=self.step_value,
                max_iter=self.max_iterations
            )
            setattr(context.scene, names[0], best_values[0])
            setattr(context.scene, names[1], best_values[1])

            self.report(
                {'INFO'},
                f"{names[0]} / {names[1]} optimiert → "
                f"{best_values[0]:.6f}, {best_values[1]:.6f} (Länge {best_length})"
            )

        self.report({'INFO'}, "Automatische Kalibrierung abgeschlossen.")
        return {'FINISHED'}

    # =====================================================================
    #  Kernlogik
    # =====================================================================

    def _run_and_measure(self, context) -> float:
        """Führt Tracker-Lauf aus und misst aktuelle Track-Länge."""
        bpy.ops.kaiserlichttracker.detect_adapt()
        bpy.ops.kaiserlichttracker.track_cycle()
        start = get_start_frame(context)
        reset_to_frame(context, start)
        return get_total_track_length(start, context)

    def _tune_single_threshold(
        self,
        context,
        name: str,
        base_value: float,
        min_threshold: float,
        initial_step: float,
        max_iter: int
    ) -> Tuple[float, float]:
        """Optimiert einen einzelnen Scene-Threshold."""
        setattr(context.scene, name, base_value)
        best_length = self._run_and_measure(context)
        best_value = base_value

        # Test Minimalwert
        setattr(context.scene, name, min_threshold)
        length_min = self._run_and_measure(context)
        if length_min > best_length:
            best_length = length_min
            best_value = min_threshold

        step = initial_step
        current_value = best_value

        for _ in range(max_iter):
            step /= 2.0
            if step < 1.0:
                break

            candidate = max(min_threshold, best_value / step)
            setattr(context.scene, name, candidate)
            cand_len = self._run_and_measure(context)

            if cand_len >= best_length:
                best_length = cand_len
                best_value = candidate
                current_value = candidate
            else:
                candidate_alt = best_value * (2.0 / step)
                setattr(context.scene, name, candidate_alt)
                cand_alt_len = self._run_and_measure(context)

                if cand_alt_len > best_length:
                    best_length = cand_alt_len
                    best_value = candidate_alt
                    current_value = candidate_alt
                else:
                    setattr(context.scene, name, current_value)

        setattr(context.scene, name, best_value)
        return best_value, best_length

    def _tune_pair_threshold(
        self,
        context,
        names: Tuple[str, str],
        base_values: Tuple[float, float],
        min_threshold: float,
        initial_step: float,
        max_iter: int
    ) -> Tuple[Tuple[float, float], float]:
        """Optimiert zwei gekoppelte Scene-Thresholds gleichzeitig."""
        setattr(context.scene, names[0], base_values[0])
        setattr(context.scene, names[1], base_values[1])

        best_length = self._run_and_measure(context)
        best_values = base_values

        # Test Minimalwerte
        setattr(context.scene, names[0], min_threshold)
        setattr(context.scene, names[1], min_threshold)
        length_min = self._run_and_measure(context)
        if length_min > best_length:
            best_length = length_min
            best_values = (min_threshold, min_threshold)

        step = initial_step
        current_values = best_values

        for _ in range(max_iter):
            step /= 2.0
            if step < 1.0:
                break

            cand1 = (
                max(min_threshold, best_values[0] / step),
                max(min_threshold, best_values[1] / step)
            )
            setattr(context.scene, names[0], cand1[0])
            setattr(context.scene, names[1], cand1[1])
            len1 = self._run_and_measure(context)

            cand2 = (
                best_values[0] * (2.0 / step),
                best_values[1] * (2.0 / step)
            )
            setattr(context.scene, names[0], cand2[0])
            setattr(context.scene, names[1], cand2[1])
            len2 = self._run_and_measure(context)

            if len1 > best_length or len2 > best_length:
                if len1 >= len2:
                    best_length = len1
                    best_values = cand1
                else:
                    best_length = len2
                    best_values = cand2
                current_values = best_values
            else:
                setattr(context.scene, names[0], current_values[0])
                setattr(context.scene, names[1], current_values[1])

        setattr(context.scene, names[0], best_values[0])
        setattr(context.scene, names[1], best_values[1])
        return best_values, best_length


# Registrierung für Blender
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
