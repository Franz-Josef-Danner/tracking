from typing import TypedDict, Protocol, Optional
from .telemetry import log_batch

class TrackingMetrics(TypedDict):
    corr: float
    residual_px: float
    lost: bool
    jump_px: float
    scale_delta: float
    rot_delta: float
    time_ms: float

class MetricsProvider(Protocol):
    def fetch_tracking_metrics(self, roi_id: str, frame: int) -> TrackingMetrics: ...

_PROVIDER: Optional[MetricsProvider] = None

def set_metrics_provider(p: MetricsProvider) -> None:
    global _PROVIDER
    _PROVIDER = p
    # Banner: log configured provider for debugging/wiring checks
    try:
        provider_name = getattr(p, "__class__", type(p)).__name__
        clip = getattr(p, "clip", None)
        clip_name = None
        tracks_total = None
        if clip is not None:
            try:
                clip_name = getattr(clip, "name", None)
            except Exception:
                clip_name = None
            try:
                tracks_total = len(getattr(getattr(clip, "tracking", None), "tracks", []) or [])
            except Exception:
                tracks_total = None
        log_batch("provider.banner", "set_metrics_provider", {"provider": provider_name, "clip": clip_name, "tracks_total": tracks_total})
    except Exception:
        # never fail provider setup due to logging
        pass

def get_metrics_provider() -> MetricsProvider:
    if _PROVIDER is None:
        raise NotImplementedError("No MetricsProvider configured. Call set_metrics_provider(...) first.")
    return _PROVIDER
