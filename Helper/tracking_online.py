# Frameweise α-Adjust + gated Pattern-Wechsel (apply-next)


def track_one_frame(roi_id) -> dict:
    """1-Step-Tracking für alle Marker im ROI; return Telemetrie-Aggregate."""
    raise NotImplementedError


def schedule_param_changes(roi_id, telemetry: dict) -> None:
    """Pro Marker: α-Adjust (cheap) live; Pattern-Change gated (apply-next)."""
    raise NotImplementedError


def apply_scheduled_next_frame(roi_id) -> None:
    """Pattern-Wechsel mit Re-Template (Medianfenster), Lock & Cooldown."""
    raise NotImplementedError