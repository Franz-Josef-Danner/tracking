"""Utility: return highest frame with solved camera."""


def get_last_solved_frame(clip):
    """Return the highest frame number with a solved camera."""

    recon = clip.tracking.reconstruction
    if not recon.is_valid:
        return None
    frames = [cam.frame for cam in recon.cameras]
    return max(frames) if frames else None

