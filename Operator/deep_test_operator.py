"""
deep_test.py – Operator zum automatisierten Schwellenwert‑Feintuning
===============================================================

Dieser Operator implementiert einen iterativen Testalgorithmus zur
feingranularen Bestimmung von Tracking‑Schwellenwerten für Rotations‑,
Skalierungs‑ und Perspektivparameter. Er orientiert sich an den
Anforderungen aus der Aufgabenstellung und nutzt vorhandene Helper‑
Funktionen des Addons (Snapshot, Tracking und Szenenproperty‑Setter).

Die Tests werden sequentiell durchgeführt:

1. **Rotation (ΔX/ΔY)** – Der X‑Schwellenwert wird schrittweise
   reduziert. Der Y‑Schwellenwert wird dabei automatisch aus dem
   Verhältnis der Clip‑Auflösung berechnet. Nach jeder Stufe wird die
   Gesamtlänge aller Tracks gemessen und mit dem vorher definierten
   Zielwert verglichen. Verbesserungen werden übernommen, andernfalls
   erfolgt ein Reset auf den Startwert und die nächste Stufe wird
   verwendet.
2. **Skalierung (Min/Max)** – Sowohl der minimale als auch der maximale
   Skalierungsschwellenwert werden separat getestet. Während der Test
   des einen Parameters läuft, wird der jeweils andere Parameter auf
   den Neutralwert 1,0 gesetzt. Auch hier werden Verbesserungen gegen
   den Zielwert abgeprüft.
3. **Rotation + Skalierung (Rot/Scale)** – Zunächst wird die rotative
   Komponente bei deaktiviertem Skalierungsanteil (Scale = 0,0)
   getestet. Anschließend wird der Skalierungsanteil bei
   deaktivierter Rotation (Rot = 0,0) geprüft.
4. **Perspektive** – Im letzten Schritt wird der Perspektiv‑
   Schwellenwert ermittelt. Während dieses Tests werden alle zuvor
   gefundenen Schwellenwerte für die anderen Parameter gesetzt.

Nach Abschluss werden die ermittelten Optimalwerte in der Szene
gespeichert und die jeweiligen Scene‑Properties auf diese Werte
gesetzt.

Hinweis: Die Implementierung ist bewusst als blockierender Operator
gestaltet (``execute``), um deterministische Ergebnisse zu liefern.
Der Code nimmt an, dass alle benötigten Helper‑Module über das
Paketlayout ``..Helper`` verfügbar sind (wie im ursprünglichen Addon).
"""

import bpy
from bpy.types import Operator, Context
from typing import Dict, Tuple, Optional

# Helper‑Importe
from ..Helper.util_clip import get_active_clip
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.util_scene import set_scene_props

# Konstanten für die Schlüsselnamen der Zielwerte
SCENE_TOTAL_TRACK_LEN_BASE = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Kaiserlich Tracker – Deep Threshold Test

    Dieser Operator führt automatisierte, iterative Threshold‑Tests für
    Rotation, Skalierung, kombinierte Rot/Scale‑Parameter sowie
    perspektivische Abweichungen durch. Er basiert auf den im Addon
    vorhandenen Helper‑Funktionen zum Setzen von Scene‑Properties und
    Messen der Track‑Längen.
    """

    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker – Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    # Reduktionsfaktoren entsprechen den Prozentangaben:
    # -95 %, -50 %, -20 %, -10 %, -5 %, -2 %, -1 %
    _reduction_factors = [0.05, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
    _min_threshold = 0.00001

    def execute(self, context: Context):
        # Validieren, dass ein Clip aktiv ist
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden. Deep Test abgebrochen.")
            return {'CANCELLED'}

        scene = context.scene

        # Ausgangswerte sichern und alle Thresholds auf 1.0 setzen, um neutral zu starten
        initial_values = {
            'kaiserlich_rot_thresh_x': float(getattr(scene, 'kaiserlich_rot_thresh_x', 1.0)),
            'kaiserlich_rot_thresh_y': float(getattr(scene, 'kaiserlich_rot_thresh_y', 1.0)),
            'kaiserlich_scale_thresh_min': float(getattr(scene, 'kaiserlich_scale_thresh_min', 1.0)),
            'kaiserlich_scale_thresh_max': float(getattr(scene, 'kaiserlich_scale_thresh_max', 1.0)),
            'kaiserlich_rot_scale_thresh_rot': float(getattr(scene, 'kaiserlich_rot_scale_thresh_rot', 1.0)),
            'kaiserlich_rot_scale_thresh_scale': float(getattr(scene, 'kaiserlich_rot_scale_thresh_scale', 1.0)),
            'kaiserlich_perspective_thresh': float(getattr(scene, 'kaiserlich_perspective_thresh', 1.0)),
        }

        # Neutralisieren aller Thresholds vor der Baseline‐Messung
        set_scene_props(scene,
                        kaiserlich_rot_thresh_x=1.0,
                        kaiserlich_rot_thresh_y=1.0,
                        kaiserlich_scale_thresh_min=1.0,
                        kaiserlich_scale_thresh_max=1.0,
                        kaiserlich_rot_scale_thresh_rot=1.0,
                        kaiserlich_rot_scale_thresh_scale=1.0,
                        kaiserlich_perspective_thresh=1.0)

        # Baseline‑Messung (Optional: initialisieren, falls noch nicht gesetzt)
        base_length = self._track_and_measure(context)
        scene[SCENE_TOTAL_TRACK_LEN_BASE] = base_length

        # Vorhandene Zielwerte aus der Szene lesen. Sollte ein Schlüssel fehlen, wird 0 als Zielwert genutzt.
        target_step1 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0))
        target_step2 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0))
        target_step3 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0))
        target_step4 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0))

        results: Dict[str, float] = {}

        # Test 1: Rotation (X/Y)
        rot_x, rot_y = self._test_rot_pair(context, target_step1, clip)
        results['kaiserlich_rot_thresh_x'] = rot_x
        results['kaiserlich_rot_thresh_y'] = rot_y

        # Test 2: Skalierung (Min/Max)
        scale_min = self._test_single_threshold(context,
                                                prop_name='kaiserlich_scale_thresh_min',
                                                target_value=target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_max': 1.0,
                                                              'kaiserlich_rot_thresh_x': 1.0,
                                                              'kaiserlich_rot_thresh_y': 1.0,
                                                              'kaiserlich_rot_scale_thresh_rot': 1.0,
                                                              'kaiserlich_rot_scale_thresh_scale': 1.0,
                                                              'kaiserlich_perspective_thresh': 1.0})
        # Nach Abschluss des Min‑Tests wird der Wert zurückgesetzt, bevor der Max‑Test startet
        scale_max = self._test_single_threshold(context,
                                                prop_name='kaiserlich_scale_thresh_max',
                                                target_value=target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_min': 1.0,
                                                              'kaiserlich_rot_thresh_x': 1.0,
                                                              'kaiserlich_rot_thresh_y': 1.0,
                                                              'kaiserlich_rot_scale_thresh_rot': 1.0,
                                                              'kaiserlich_rot_scale_thresh_scale': 1.0,
                                                              'kaiserlich_perspective_thresh': 1.0})
        results['kaiserlich_scale_thresh_min'] = scale_min
        results['kaiserlich_scale_thresh_max'] = scale_max

        # Test 3: Rotation+Scale Paar
        rot_scale_rot, rot_scale_scale = self._test_rot_scale_pair(context, target_step3)
        results['kaiserlich_rot_scale_thresh_rot'] = rot_scale_rot
        results['kaiserlich_rot_scale_thresh_scale'] = rot_scale_scale

        # Test 4: Perspektive – Alle zuvor ermittelten Thresholds werden gesetzt
        perspective = self._test_single_threshold(context,
                                                 prop_name='kaiserlich_perspective_thresh',
                                                 target_value=target_step4,
                                                 freeze_others=results)
        results['kaiserlich_perspective_thresh'] = perspective

        # Abschließend alle gefundenen Thresholds in die Szene übertragen
        set_scene_props(scene, **results)

        # Ergebnis protokollieren
        scene['kaiserlich_deep_test_results'] = results
        self.report({'INFO'}, f"Deep Test abgeschlossen. Ergebnis: {results}")
        return {'FINISHED'}

    # ------------------------------------------------------------------
    # Helper‑Funktionen
    # ------------------------------------------------------------------
    def _track_and_measure(self, context: Context) -> int:
        """Führt eine vollständige Tracking‑Sequenz der aktuell selektierten
        Tracks aus und gibt die Gesamtlänge aller Tracks ab dem
        Szenenstart zurück.

        Hinweis: Diese Methode setzt voraus, dass die relevanten
        Scene‑Properties vor dem Aufruf korrekt gesetzt wurden.
        """
        scene = context.scene
        clip = getattr(context.space_data, 'clip', None)
        if clip is None:
            return 0

        # Selektion: Alle Tracks aktivieren (mute deaktivieren, Auswahl setzen)
        tracking = clip.tracking
        for tr in tracking.tracks:
            try:
                tr.select = True
                tr.mute = False
            except Exception:
                pass

        # Playhead auf Startframe setzen
        start_frame = scene.frame_start
        scene.frame_current = start_frame
        try:
            context.space_data.clip_user.frame_current = start_frame  # type: ignore[attr-defined]
        except Exception:
            pass

        # Tracking durchführen – sequence=True verfolgt bis zum Ende
        try:
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        except Exception:
            # Fehler beim Tracking werden ignoriert; es wird die aktuelle
            # Track‑Länge ausgewertet
            pass

        # Gesamtlänge ablesen
        total_len = int(get_total_track_length(context, start_frame=start_frame))

        # Playhead wieder auf Start setzen (für nachfolgenden Test)
        scene.frame_current = start_frame
        try:
            context.space_data.clip_user.frame_current = start_frame  # type: ignore[attr-defined]
        except Exception:
            pass

        return total_len

    def _test_rot_pair(self, context: Context, target_value: int, clip) -> Tuple[float, float]:
        """Testet das Rotations‑Threshold‑Paar (ΔX/ΔY) und ermittelt den
        optimalen ΔX‑Wert. Der ΔY‑Wert wird aus dem Verhältnis der
        Clip‑Auflösung abgeleitet.
        """
        scene = context.scene
        hz, vc = clip.size[0], clip.size[1]
        ratio = (hz / vc) if vc > 0 else 1.0

        start_value = 1.0
        min_value = self._min_threshold
        threshold_min_found = min_value
        best_x = start_value  # Default, falls keine Verbesserung erreicht wird
        best_y = start_value
        current_target = max(int(target_value), 0)

        for factor in self._reduction_factors:
            # Reset des Threshold‑Werts für diese Stufe
            current_value = start_value
            while True:
                current_value *= factor
                if current_value < min_value:
                    break
                # ΔX/ΔY setzen
                set_scene_props(scene,
                                kaiserlich_rot_thresh_x=current_value,
                                kaiserlich_rot_thresh_y=current_value * ratio)
                # Tracking und Messung
                length = self._track_and_measure(context)
                # Prüfen, ob Zielwert erreicht oder übertroffen wurde
                if length >= current_target:
                    threshold_min_found = current_value
                    best_x = current_value
                    best_y = current_value * ratio
                    if length > current_target:
                        current_target = length
                    # Threshold zurücksetzen und nächste Stufe starten
                    break
                # Wenn der aktuelle Wert kleiner oder gleich dem bisher gefundenen
                # Minimum ist, ohne das Ziel zu verbessern, Stufe verlassen
                if current_value <= threshold_min_found:
                    break
            # Beide Werte zurück auf neutral setzen
            set_scene_props(scene,
                            kaiserlich_rot_thresh_x=start_value,
                            kaiserlich_rot_thresh_y=start_value)
        return best_x, best_y

    def _test_single_threshold(self,
                               context: Context,
                               prop_name: str,
                               target_value: int,
                               freeze_others: Optional[Dict[str, float]] = None
                               ) -> float:
        """Testet einen einzelnen Scene‑Property‑Threshold. Während des Tests
        können andere Properties über ``freeze_others`` auf definierte
        Werte fixiert werden.
        """
        scene = context.scene
        start_value = 1.0
        min_value = self._min_threshold
        threshold_min_found = min_value
        best_value = start_value
        current_target = max(int(target_value), 0)

        for factor in self._reduction_factors:
            current_value = start_value
            while True:
                current_value *= factor
                if current_value < min_value:
                    break
                # Setze gefrorene Werte (andere Properties) falls vorhanden
                if freeze_others:
                    set_scene_props(scene, **freeze_others)
                # Setze den aktuellen Test‑Threshold
                set_scene_props(scene, **{prop_name: current_value})
                # Tracking und Messung
                length = self._track_and_measure(context)
                if length >= current_target:
                    threshold_min_found = current_value
                    best_value = current_value
                    if length > current_target:
                        current_target = length
                    break
                if current_value <= threshold_min_found:
                    break
            # Property zurück auf Neutralwert setzen
            if freeze_others:
                set_scene_props(scene, **freeze_others)
            set_scene_props(scene, **{prop_name: start_value})
        return best_value

    def _test_rot_scale_pair(self, context: Context, target_value: int) -> Tuple[float, float]:
        """Testet das kombinierte Rot/Scale‑Threshold‑Paar. Zuerst wird der
        Rot‑Threshold getestet (Scale auf 0), anschließend der
        Skalierungs‑Threshold (Rot auf 0).
        """
        # Rotanteil testen (Scale = 0)
        rot_value = self._test_single_threshold(
            context,
            prop_name='kaiserlich_rot_scale_thresh_rot',
            target_value=target_value,
            freeze_others={'kaiserlich_rot_scale_thresh_scale': 0.0,
                          'kaiserlich_rot_thresh_x': 1.0,
                          'kaiserlich_rot_thresh_y': 1.0,
                          'kaiserlich_scale_thresh_min': 1.0,
                          'kaiserlich_scale_thresh_max': 1.0,
                          'kaiserlich_perspective_thresh': 1.0}
        )
        # Skalierungsanteil testen (Rot = 0)
        scale_value = self._test_single_threshold(
            context,
            prop_name='kaiserlich_rot_scale_thresh_scale',
            target_value=target_value,
            freeze_others={'kaiserlich_rot_scale_thresh_rot': 0.0,
                          'kaiserlich_rot_thresh_x': 1.0,
                          'kaiserlich_rot_thresh_y': 1.0,
                          'kaiserlich_scale_thresh_min': 1.0,
                          'kaiserlich_scale_thresh_max': 1.0,
                          'kaiserlich_perspective_thresh': 1.0}
        )
        return rot_value, scale_value


# Registrierung
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)
