# ------------------------- Modal Operator (2-Phasen) -------------------------

class CLIP_OT_refine_high_error_modal(Operator):
    """Scannt erst alle Frames, wählt die Top-N mit höchstem Gesamtfehler und refin’t dort."""
    bl_idname = "clip.refine_high_error_modal"
    bl_label = "Refine Highest Error Frames (Modal)"
    bl_options = {"REGISTER", "INTERNAL"}

    # Beibehalten (für Rückwärtskompatibilität, wird hier nicht verwendet)
    error_track: bpy.props.FloatProperty(default=2.0)  # type: ignore

    # Neue/angepasste Parameter
    top_n_frames: bpy.props.IntProperty(default=20, min=1)  # type: ignore
    only_selected_tracks: bpy.props.BoolProperty(default=False)  # type: ignore
    wait_seconds: bpy.props.FloatProperty(default=0.05, min=0.0, soft_max=0.5)  # type: ignore
    ui_sleep_s: bpy.props.FloatProperty(default=0.04, min=0.0, soft_max=0.2)  # type: ignore
    max_refine_calls: bpy.props.IntProperty(default=20, min=1)  # type: ignore
    tracking_object_name: bpy.props.StringProperty(default="")  # type: ignore

    # intern
    _timer = None
    _ovr: Optional[dict] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _tob = None
    _tracks: List = []
    _frame_scene: int = 0
    _frame_end: int = 0
    _ops_left: int = 0

    # 2-Phasen-Steuerung
    _phase: str = "scan"  # "scan" -> "refine"
    _scan_errors: dict[int, float] = {}         # scene_frame -> error_sum
    _targets: List[int] = []                    # scene_frames (Top-N)
    _target_index: int = 0

    def invoke(self, context: Context, event):
        # Kontext/Clip ermitteln
        self._ovr = _find_clip_area_ctx(context)
        if not self._ovr:
            self.report({"ERROR"}, "Kein Movie Clip Editor im aktuellen Screen")
            return {"CANCELLED"}
        self._clip = self._ovr.get("edit_movieclip") or getattr(self._ovr.get("space_data"), "clip", None)
        if not self._clip:
            self.report({"ERROR"}, "Kein Movie Clip aktiv")
            return {"CANCELLED"}

        tracking = self._clip.tracking
        recon = getattr(tracking, "reconstruction", None)
        if not recon or not getattr(recon, "is_valid", False):
            self.report({"ERROR"}, "Rekonstruktion ist nicht gültig. Erst solve durchführen.")
            return {"CANCELLED"}

        self._tob = (tracking.objects.get(self.tracking_object_name)
                     if self.tracking_object_name else tracking.objects.active)
        if self._tob is None:
            self.report({"ERROR"}, "Kein Tracking-Objekt aktiv")
            return {"CANCELLED"}

        # Track-Menge festlegen (ggf. nur selektierte)
        self._tracks = list(self._tob.tracks)
        if self.only_selected_tracks:
            self._tracks = [t for t in self._tracks if getattr(t, "select", False)]
        if not self._tracks:
            self.report({"WARNING"}, "Keine passenden Tracks gefunden")
            return {"CANCELLED"}

        scn = context.scene
        self._frame_scene = int(scn.frame_start)
        self._frame_end = int(scn.frame_end)
        self._ops_left = int(self.max_refine_calls)

        # Phasen-Init
        self._phase = "scan"
        self._scan_errors = {}
        self._targets = []
        self._target_index = 0

        # Flag: läuft
        scn["refine_active"] = True

        # Timer
        step = max(0.01, min(0.2, float(self.wait_seconds) * 0.5))
        self._timer = context.window_manager.event_timer_add(step, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        try:
            if self._phase == "scan":
                if self._frame_scene > self._frame_end:
                    # Scan abgeschlossen -> Top-N bestimmen
                    self._prepare_targets_after_scan()
                    if not self._targets:
                        # nichts zu tun
                        return self._finish(context, cancelled=False)
                    # Refine-Phase starten
                    self._phase = "refine"
                    self._target_index = 0
                    return {"RUNNING_MODAL"}

                # --- Scan-Schritt: Fehler-Summe für aktuellen Szenen-Frame ---
                f_scene = self._frame_scene
                f_clip = _scene_to_clip_frame(context, self._clip, f_scene)
                err_sum = 0.0
                found = False

                for tr in _iter_tracks_with_marker_at_clip_frame(self._tracks, f_clip):
                    v = _marker_error_on_clip_frame(tr, f_clip)
                    if v is not None:
                        err_sum += float(v)
                        found = True

                # nur speichern, wenn Marker vorhanden waren (optional)
                self._scan_errors[f_scene] = (err_sum if found else 0.0)

                # nächster Frame
                self._frame_scene += 1
                return {"RUNNING_MODAL"}

            # -------- Refine-Phase --------
            if self._ops_left <= 0 or self._target_index >= len(self._targets):
                return self._finish(context, cancelled=False)

            f_scene = int(self._targets[self._target_index])
            f_clip = _scene_to_clip_frame(context, self._clip, f_scene)
            active_tracks = list(_iter_tracks_with_marker_at_clip_frame(self._tracks, f_clip))

            if active_tracks:
                # Playhead zeigen
                _force_visible_playhead(context, self._ovr, self._clip, f_scene,
                                        sleep_s=float(self.ui_sleep_s))

                # Auswahl setzen (nur Marker dieses Frames)
                _set_selection_for_tracks_on_clip_frame(self._tob, f_clip, active_tracks)

                # refine vorwärts
                if self._ops_left > 0:
                    with context.temp_override(**self._ovr):
                        bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=False)
                    self._ops_left -= 1
                    with context.temp_override(**self._ovr):
                        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

                # refine rückwärts (wenn Budget)
                if self._ops_left > 0:
                    if float(self.wait_seconds) > 0.0:
                        time.sleep(min(0.2, float(self.wait_seconds)))
                    with context.temp_override(**self._ovr):
                        bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=True)
                    self._ops_left -= 1
                    with context.temp_override(**self._ovr):
                        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            # nächstes Ziel
            self._target_index += 1
            return {"RUNNING_MODAL"}

        except Exception as ex:
            print(f"[RefineModal] Error: {ex!r}")
            return self._finish(context, cancelled=True)

    # Hilfsfunktion: Top-N Ziele bestimmen
    def _prepare_targets_after_scan(self) -> None:
        # Sortiere Szene-Frames nach Fehler-Summe absteigend
        pairs = sorted(self._scan_errors.items(), key=lambda kv: kv[1], reverse=True)
        # nimm nur Frames mit > 0 Fehler (optional) und begrenze auf top_n_frames
        filtered = [f for (f, s) in pairs if s > 0.0]
        if not filtered:
            # falls alle 0.0 sind, nimm trotzdem die ersten N (damit wenigstens was passiert)
            filtered = [f for (f, _) in pairs]
        self._targets = filtered[:int(self.top_n_frames)]

    def _finish(self, context: Context, *, cancelled: bool):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        try:
            context.scene["refine_active"] = False
        except Exception:
            pass
        print(f"[RefineModal] DONE ({'CANCELLED' if cancelled else 'FINISHED'})")
        return {"CANCELLED" if cancelled else "FINISHED"}


# ------------------------- Public API ----------------------------------------

def start_refine_modal(
    context: Context,
    *,
    error_track: float = 2.0,         # bleibt für API-Kompatibilität, wird in dieser Variante ignoriert
    top_n_frames: int = 20,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.05,
    ui_sleep_s: float = 0.04,
    max_refine_calls: int = 20,
    tracking_object_name: str | None = None,
) -> dict:
    """
    Startet den 2-Phasen-Modal-Operator:
      1) Scan aller Frames, Ermittlung des kumulierten Fehlerwertes pro Frame
      2) Auswahl der Top-N Frames und Refine an diesen Frames (vorwärts + rückwärts)
    Rückgabe: {'status': 'STARTED'|'BUSY'|'FAILED'}.
    Ein äußerer Koordinator kann über scene['refine_active'] warten.
    """
    scn = context.scene
    if scn.get("refine_active"):
        return {"status": "BUSY"}

    ovr = _find_clip_area_ctx(context)
    if not ovr:
        return {"status": "FAILED", "reason": "no_clip_editor"}

    kwargs = dict(
        error_track=float(error_track),  # wird intern nicht genutzt
        top_n_frames=int(top_n_frames),
        only_selected_tracks=bool(only_selected_tracks),
        wait_seconds=float(wait_seconds),
        ui_sleep_s=float(ui_sleep_s),
        max_refine_calls=int(max_refine_calls),
        tracking_object_name=str(tracking_object_name or ""),
    )
    with context.temp_override(**ovr):
        bpy.ops.clip.refine_high_error_modal('INVOKE_DEFAULT', **kwargs)
    return {"status": "STARTED", **kwargs}
