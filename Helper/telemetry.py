# KPIs/Logs, Score-Aggregation, Zeitbudget


def log_step(scope: str, payload: dict) -> None:
    """Persistente JSON/CSV-Logs (ROI/Cluster/Marker)."""
    raise NotImplementedError


def aggregate_kpis() -> dict:
    """Globaler Score: Error_norm, (1-Coverage), Time_norm, Outlier, (1-Parallax_norm)."""
    raise NotImplementedError


def time_budget_hit(roi_id) -> bool:
    """Zeit-Slice-Guard je ROI."""
    raise NotImplementedError