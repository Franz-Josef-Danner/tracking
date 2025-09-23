# Kanal-Analyse & -Selektion (Pre-Pass + Micro-Trials)


def analyze_channels(roi_id, sample_frames: list[int]) -> dict:
    """Return per-channel Pre-Scores (texture, stability, penalty)."""
    raise NotImplementedError


def trial_track_channel(roi_id, channel: str, window: int = 30) -> dict:
    """Run Micro-Trial; return {survival, corr_med, time_norm, score}."""
    raise NotImplementedError


def select_channel(roi_id, pattern: int, alpha: int) -> str:
    """Shortlist + Micro-Trial → return best channel ('Y','G','R','B','Y_EQ')."""
    raise NotImplementedError