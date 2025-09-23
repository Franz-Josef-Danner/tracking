def run_autotrack(context, clip) -> dict:
    """
    Orchestriert den Autotrack-Ablauf (dünn, nur Verkabelung):
      1) ROI-Analyse & Priorisierung
      2) Startwerte (pattern/alpha) + Kanalwahl
      3) Detect-Profil vorschlagen/feinjustieren
      4) Gestufte Setzung mit Dedup + Micro-Validation
      5) Online-Tracking-Loop mit Parametrierung, Model-Fit/Selektion, Peer-Stabilisierung
      6) Periodischer Cleanup, Zeitbudget/Telemetrie, KPI-Aggregation
    Return: globale KPIs.
    """
    raise NotImplementedError
