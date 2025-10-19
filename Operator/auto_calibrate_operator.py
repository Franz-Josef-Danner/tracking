# Operator/auto_calibrate_operator.py

import bpy
from math import inf

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_settings_and_props(context):
    """
    Ermittelt die PropertyGroup und deren kalibrierbare Properties.
    Annahme: Settings liegen unter context.scene.klt_settings (anpassen falls anders).
    Wir lesen die Annotationen, um nur echte bpy.props (Int/Float) zu bekommen.
    """
    settings = getattr(context.scene, "klt_settings", None)
    if settings is None:
        raise RuntimeError("KAISERLICHTRACKER: 'context.scene.klt_settings' nicht gefunden.")

    # Nur numerische Properties (Float/Int) berücksichtigen
    anno = getattr(type(settings), "__annotations__", {})
    prop_names = []
    for name, _def in anno.items():
        prop = getattr(type(settings), name, None)
        if not hasattr(prop, "keywords"):
            continue
        kw = prop.keywords
        subtype = prop.__class__.__name__.lower()
        if "floatproperty" in subtype or "intproperty" in subtype:
            prop_names.append(name)

    if not prop_names:
        raise RuntimeError("KAISERLICHTRACKER: Keine kalibrierbaren numerischen Properties gefunden.")
    return settings, prop_names


def _get_bounds(prop_def):
    """Liest (min, max, soft_min, soft_max) aus einem Property-Definition-Objekt."""
    kw = getattr(prop_def, "keywords", {})
    hard_min = kw.get("min", None)
    hard_max = kw.get("max", None)
    soft_min = kw.get("soft_min", hard_min)
    soft_max = kw.get("soft_max", hard_max)
    return hard_min, hard_max, soft_min, soft_max


def _clamp(value, low, high):
    if low is None and high is None:
        return value
    if low is None:
        return min(value, high)
    if high is None:
        return max(value, low)
    return max(low, min(value, high))


def _evaluate_tracking_score(context) -> float:
    """
    Domain-spezifische Bewertungsfunktion.
    TODO: Ersetzen durch echte Metrik (z.B. reprojection error, tracking loss, o.ä.)
    Muss einen Score liefern, bei dem *niedriger besser* ist.
    """
    # Platzhalter: ohne echte Pipeline kein verlässlicher Score.
    # Wir geben 0.0 zurück, damit der Flow steht – bitte projektintern ersetzen.
    return 0.0


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: setzt initial alle relevanten Werte auf 1 und testet danach jeden Parameter isoliert."""
    bl_idname = "kaiserlichtracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    # Optional: Schrittweite und Testwerte konfigurieren
    step: bpy.props.FloatProperty(
        name="Schrittweite",
        description="Inkrement für die Einzelsuche pro Parameter (nur für Floats)",
        default=0.1,
        min=0.0001,
        soft_max=10.0,
    )
    span: bpy.props.IntProperty(
        name="Schritte je Seite",
        description="Anzahl Schritte in beide Richtungen um den Startwert",
        default=5,
        min=1,
        soft_max=100,
    )

    def execute(self, context):
        try:
            settings, prop_names = _get_settings_and_props(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        # 1) Baseline: alle relevanten Properties (Float/Int) hart auf 1 setzen
        for name in prop_names:
            prop_def = getattr(type(settings), name)
            hard_min, hard_max, soft_min, soft_max = _get_bounds(prop_def)

            # 1 als Startwert clampen (respektiert harte Grenzen)
            start_val = _clamp(1, hard_min, hard_max)
            setattr(settings, name, start_val)

        # Recompute Baseline-Score
        best_global_score = _evaluate_tracking_score(context)

        # 2) Isolierte Einzelsuche pro Parameter
        for name in prop_names:
            prop_def = getattr(type(settings), name)
            hard_min, hard_max, soft_min, soft_max = _get_bounds(prop_def)
            current_val = getattr(settings, name)

            # Kandidatenwerte generieren (um 1 herum, geklemmt). Für Int/Float getrennt behandeln.
            is_int = "intproperty" in prop_def.__class__.__name__.lower()

            candidates = set([current_val])
            if is_int:
                # Int: diskret um 1 herum durchsuchen
                for i in range(1, self.span + 1):
                    candidates.add(_clamp(int(round(1 + i)), hard_min, hard_max))
                    candidates.add(_clamp(int(round(1 - i)), hard_min, hard_max))
            else:
                # Float: kontinuierlich um 1 herum durchsuchen
                for i in range(1, self.span + 1):
                    candidates.add(_clamp(1.0 + i * self.step, hard_min, hard_max))
                    candidates.add(_clamp(1.0 - i * self.step, hard_min, hard_max))

            # Normalisieren: raus mit Nones, NaNs, Grenzen-respektierend
            candidates = [c for c in sorted(candidates) if c is not None]

            best_local_val = current_val
            best_local_score = inf

            # Jeden Kandidaten isoliert testen
            for cand in candidates:
                setattr(settings, name, cand)
                score = _evaluate_tracking_score(context)

                if score < best_local_score:
                    best_local_score = score
                    best_local_val = cand

            # Bestwert für diesen Parameter setzen
            setattr(settings, name, best_local_val)

            # Optional: globalen Score tracken (informativ)
            best_global_score = min(best_global_score, best_local_score)

        self.report({'INFO'}, f"Auto-Calibrate abgeschlossen. Finaler Score: {best_global_score:.4f}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
