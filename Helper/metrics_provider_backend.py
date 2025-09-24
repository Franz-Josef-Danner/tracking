from __future__ import annotations
from typing import Optional
import json
import time
import urllib.parse
import urllib.request
import os

from .metrics_provider import MetricsProvider, TrackingMetrics


class BackendMetricsProvider(MetricsProvider):
    """Metrics provider that queries an external HTTP backend which returns the
    same JSON structure as `TrackingMetrics`.

    Behavior:
    - Reads backend URL template from `METRICS_BACKEND_URL` environment variable.
      Template should contain `{roi_id}` and `{frame}` placeholders, e.g.
      `http://127.0.0.1:9000/metrics?roi_id={roi_id}&frame={frame}`.
    - Uses `urllib` so no extra dependencies are required.
    - Returns safe defaults when the backend is unreachable or returns invalid data.
    """

    def __init__(self, url_template: Optional[str] = None, timeout: float = 0.5):
        self.url_template = url_template or os.environ.get(
            "METRICS_BACKEND_URL", "http://127.0.0.1:9000/metrics?roi_id={roi_id}&frame={frame}"
        )
        self.timeout = float(timeout)

    def fetch_tracking_metrics(self, roi_id: str, frame: int) -> TrackingMetrics:
        t0 = time.time()
        try:
            url = self.url_template.format(roi_id=urllib.parse.quote(str(roi_id)), frame=int(frame))
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                data = resp.read()
                parsed = json.loads(data.decode("utf-8"))
                # Ensure required keys exist, else raise to trigger fallback
                for k in ("corr", "residual_px", "lost", "jump_px", "scale_delta", "rot_delta", "time_ms"):
                    if k not in parsed:
                        raise ValueError("Incomplete payload")
                return {
                    "corr": float(parsed.get("corr", 0.0)),
                    "residual_px": float(parsed.get("residual_px", 0.0)),
                    "lost": bool(parsed.get("lost", False)),
                    "jump_px": float(parsed.get("jump_px", 0.0)),
                    "scale_delta": float(parsed.get("scale_delta", 0.0)),
                    "rot_delta": float(parsed.get("rot_delta", 0.0)),
                    "time_ms": float(parsed.get("time_ms", (time.time() - t0) * 1000.0)),
                }
        except Exception:
            # Fallback to synthetic values
            dt_ms = (time.time() - t0) * 1000.0
            return {
                "corr": 0.0,
                "residual_px": 0.0,
                "lost": True,
                "jump_px": 0.0,
                "scale_delta": 0.0,
                "rot_delta": 0.0,
                "time_ms": float(dt_ms),
            }
