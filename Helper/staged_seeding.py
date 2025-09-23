# /5-Stufen-Setzung inkl. Dedup & Mengensteuerung


def staged_detect_with_dedup(roi_id, pattern: int, alpha: int, total_target: int, scene) -> dict:
    """
    Implementiert 5 Stufen (thr: 1.0→0.0001) mit:
      - Dedup gegen Alt+Acc (min_distance aus feedback)
      - per_stage=scene['marker_stage_target'] ±10% (lo/hi)
      - Micro-Validation (10f)
      - trim/refill nach Band
    Return Summary {placed, stages, time_ms}.
    """
    raise NotImplementedError