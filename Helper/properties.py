import bpy


# --- Repeat Scope (Viewer-Box) ---
def ensure_repeat_scope_props():
    """Nur RNA-Properties registrieren; kein Zugriff auf bpy.context in Register-Phase."""
    if not hasattr(bpy.types.Scene, "kc_show_repeat_scope"):
        bpy.types.Scene.kc_show_repeat_scope = bpy.props.BoolProperty(
            name="Repeat-Scope",
            description="Zeigt eine Box im Viewer mit der Wiederholungskurve über die Szenenlänge",
            default=True,
            update=lambda s, c: _toggle_repeat_scope(s),
        )
    if not hasattr(bpy.types.Scene, "kc_repeat_scope_height"):
        bpy.types.Scene.kc_repeat_scope_height = bpy.props.IntProperty(
            name="Scope-Höhe (px)",
            default=140, min=50, soft_max=400,
            update=lambda s, c: _tag_redraw(),
        )
    if not hasattr(bpy.types.Scene, "kc_repeat_scope_bottom"):
        bpy.types.Scene.kc_repeat_scope_bottom = bpy.props.IntProperty(
            name="Scope-Abstand unten (px)",
            default=24, min=0, soft_max=400,
            update=lambda s, c: _tag_redraw(),
        )
    if not hasattr(bpy.types.Scene, "kc_repeat_scope_margin_x"):
        bpy.types.Scene.kc_repeat_scope_margin_x = bpy.props.IntProperty(
            name="Scope-Seitenrand (px)",
            default=12, min=0, soft_max=200,
            update=lambda s, c: _tag_redraw(),
        )
    if not hasattr(bpy.types.Scene, "kc_repeat_scope_show_cursor"):
        bpy.types.Scene.kc_repeat_scope_show_cursor = bpy.props.BoolProperty(
            name="Frame-Cursor im Scope",
            description="Zeigt eine vertikale Linie für den aktuellen Frame im Scope",
            default=True,
            update=lambda s, c: _tag_redraw(),
        )

def _toggle_repeat_scope(scene):
    try:
        from ..ui.repeat_scope import enable_repeat_scope, disable_repeat_scope
        if getattr(scene, "kc_show_repeat_scope", False):
            enable_repeat_scope()
        else:
            disable_repeat_scope()
    except Exception:
        pass
    _tag_redraw()


def _tag_redraw():
    try:
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'CLIP_EDITOR':
                    for r in a.regions:
                        if r.type == 'WINDOW':
                            r.tag_redraw()
    except Exception:
        # Während Register/Preferences kann bpy.context eingeschränkt sein.
        pass


def record_repeat_count(scene, frame, value):
    """Schreibt einen Repeat-Wert für einen absoluten Frame in die Serien-ID-Property."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return
    fs, fe = scene.frame_start, scene.frame_end
    n = max(0, int(fe - fs + 1))
    if n <= 0:
        return
    if scene.get("_kc_repeat_series") is None or len(scene["_kc_repeat_series"]) != n:
        scene["_kc_repeat_series"] = [0.0] * n
    idx = int(frame) - int(fs)
    if 0 <= idx < n:
        series = list(scene["_kc_repeat_series"])
        try:
            fval = float(value)
        except Exception:
            fval = 0.0
        series[idx] = float(max(0.0, fval))
        scene["_kc_repeat_series"] = series
        _tag_redraw()
