# Helper/find_low_marker_frame.py (Ausschnitt: run_find_low_marker_frame)
def run_find_low_marker_frame(
    context,
    *,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Orchestrator-kompatibel:
      - Liefert {"status": "FOUND", "frame": F} | {"status": "NONE"} | {"status":"FAILED","reason":...}
      - Schwellwert: **marker_basis** (nicht marker_min/marker_adapt)
      - Beachtet Clipgrenzen
    """
    try:
        clip, scn = _resolve_clip_and_scene(context)
        if not clip:
            return {"status": "FAILED", "reason": "Kein MovieClip im Kontext."}

        # >>> WICHTIG: BASISWERT verwenden
        marker_basis = int(scn.get("marker_basis", getattr(scn, "marker_frame", 25)))
        if marker_basis < 1:
            marker_basis = 1

        # Frames clampen
        fs = int(frame_start) if frame_start is not None else int(clip.frame_start)
        fe = int(frame_end)   if frame_end   is not None else _clip_frame_end(clip, scn)

        # Logging zeigt jetzt den BASIS-Wert
        frame = find_low_marker_frame_core(
            clip,
            marker_min=int(marker_basis),
            frame_start=fs,
            frame_end=fe,
            exact=True,
            ignore_muted_marker=True,
            ignore_muted_track=True,
        )

        if frame is None:
            return {"status": "NONE"}
        return {"status": "FOUND", "frame": int(frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}
