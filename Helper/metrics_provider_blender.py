from .metrics_provider import TrackingMetrics, MetricsProvider

class BlenderMetricsProvider(MetricsProvider):
    def __init__(self, *, clip=None):
        self.clip = clip

    def fetch_tracking_metrics(self, roi_id: str, frame: int) -> TrackingMetrics:
        # TODO: Replace with real bpy reads
        return {
            "corr": 0.87,
            "residual_px": 0.7,
            "lost": False,
            "jump_px": 0.6,
            "scale_delta": 0.004,
            "rot_delta": 0.15,
            "time_ms": 4.8,
        }
