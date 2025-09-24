from typing import TypedDict, Protocol, Optional

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

def get_metrics_provider() -> MetricsProvider:
    if _PROVIDER is None:
        raise NotImplementedError("No MetricsProvider configured. Call set_metrics_provider(...) first.")
    return _PROVIDER
