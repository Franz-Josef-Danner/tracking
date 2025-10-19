# Operator/auto_calibrate_operator.py

import bpy
from math import inf

# ----------------------------- Pfad-Resolver ------------------------------

def _resolve_attr_chain(root, dotted):
    cur = root
    for token in dotted.split("."):
        if not token:
            return None
        if not hasattr(cur, token):
            return None
        cur = getattr(cur, token)
    return cur

def _find_klt_settings(context, candidate_paths):
    # 1) explizite Kandidatenpfade testen
    for p in candidate_paths:
        node = _resolve_attr_chain(context, p)
        if node is not None:
            return node

    # 2) Heuristik: iteriere über gängige Container und suche nach *klt* / *kaiser*
    buckets = [
        ("scene", getattr(context, "scene", None)),
        ("window_manager", getattr(context, "window_manager", None)),
        ("object", getattr(context, "object", None)),
        ("view_layer", getattr(context, "view_layer", None)),
    ]
    keys = ("klt", "kaiser")

    for _, bucket in buckets:
        if bucket is None:
            continue
        for attr in dir(bucket):
            if any(k in attr.lower() for k in keys):
                try:
                    node = getattr(bucket, attr)
                except Exception:
                    continue
                # PointerProperty/PropertyGroup-Instanzen haben __annotations__ an der Klasse
                if hasattr(type(node), "__annotations__"):
                    return node
    return None

# ----------------------------- Utility -----------------------------------

def _get_settings_and_props(settings_obj):
    settings = settings_obj
    if settings is None:
        raise RuntimeError("KAISERLICHTRACKER: Keine Settings-PropertyGroup gefunden.")

    anno = getattr(type(settings), "__annotations__", {})
    prop_names = []
    for name, _ in anno.items():
        prop = getattr(type(settings), name, None)
        if not hasattr(prop, "keywords"):
            continue
        kind = prop.__class__.__name__.lower()
        if "floatproperty" in kind or "intproperty" in kind:
            prop_names.append(name)
    if not prop_names:
        raise RuntimeError("KAISERLICHTRACKER: Keine numerischen kalibrierbaren Properties in den Settings.")
    return settings, prop_names

def _get_bounds(prop_def):
    kw = getattr(prop_def, "keywords", {})
    return kw.get("min", None), kw.get("max", None), kw.get("soft_min", kw.get("min", None)), kw.get("soft_max", kw.get("max", None))

def _clamp(v, lo, hi):
    if lo is None and hi is None: return v
    if lo is None: return min(v, hi)
    if hi is None: return max(v, lo)
    return max(lo, min(v, hi))

def _evaluate_tracking_score(context) -> float:
    # TODO: durch echte Metrik ersetzen
    return 0.0

# ----------------------------- Operator ----------------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und testet danach jeden Parameter isoliert."""
    bl_idname = "kaiserlichtracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    # Optional: Pfad-Override und Suchkandidaten
    settings_path: bpy.props.StringProperty(
        name="Settings-Pfad",
        description="Dotted Path ab context.* (z. B. 'scene.klt_settings'). Leer lassen für Auto-Discovery.",
        default="scene.klt_settings"
    )
    extra_candidates: bpy.props.StringProperty(
        name="Zusätzliche Kandidaten",
        description="Kommagetrennte alternative Pfade (z. B. 'window_manager.klt_settings, scene.kaiser_settings').",
        default=""
    )

    step: bpy.props.FloatProperty(name="Schrittweite", default=0.1, min=0.0001, soft_max=10.0)
    span: bpy.props.IntProperty(name="Schritte je Seite", default=5, min=1, soft_max=100)

    def execute(self, context):
        # Kandidatenliste aufbauen
        candidates = []
        if self.settings_path.strip():
            candidates.append(self.settings_path.strip())
        if self.extra_candidates.strip():
            candidates.extend([c.strip() for c in self.extra_candidates.split(",") if c.strip()])

        settings_obj = _find_klt_settings(context, candidates or ["scene.klt_settings"])

        if settings_obj is None:
            self.report({'ERROR'}, "KAISERLICHTRACKER: Settings nicht gefunden. Lege sie an (siehe Option A) oder setze 'Settings-Pfad'.")
            return {'CANCELLED'}

        try:
            settings, prop_names = _get_settings_and_props(settings_obj)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        # 1) Alle auf 1 setzen
        for name in prop_names:
            prop_def = getattr(type(settings), name)
            lo, hi, _, _ = _get_bounds(prop_def)
            setattr(settings, name, _clamp(1, lo, hi))

        best_global = _evaluate_tracking_score(context)

        # 2) Isolierte Suche je Parameter
        for name in prop_names:
            prop_def = getattr(type(settings), name)
            lo, hi, _, _ = _get_bounds(prop_def)
            cur = getattr(settings, name)
            is_int = "intproperty" in prop_def.__class__.__name__.lower()

            candidates_vals = set([cur])
            if is_int:
                for i in range(1, self.span + 1):
                    candidates_vals.add(_clamp(int(round(1 + i)), lo, hi))
                    candidates_vals.add(_clamp(int(round(1 - i)), lo, hi))
            else:
                for i in range(1, self.span + 1):
                    candidates_vals.add(_clamp(1.0 + i * self.step, lo, hi))
                    candidates_vals.add(_clamp(1.0 - i * self.step, lo, hi))

            best_local_val, best_local_score = cur, inf
            for cand in sorted([c for c in candidates_vals if c is not None]):
                setattr(settings, name, cand)
                s = _evaluate_tracking_score(context)
                if s < best_local_score:
                    best_local_score, best_local_val = s, cand

            setattr(settings, name, best_local_val)
            best_global = min(best_global, best_local_score)

        self.report({'INFO'}, f"Auto-Calibrate fertig. Finaler Score: {best_global:.4f}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
