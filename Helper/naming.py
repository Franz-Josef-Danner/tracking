# Helper/naming.py
def _safe_name(obj):
    """Gibt einen robusten Track-Namen zurück oder None bei Problemen."""
    try:
        n = getattr(obj, "name", None)
        if n is None:
            return None
        if isinstance(n, bytes):
            n = n.decode("utf-8", errors="ignore")
        else:
            n = str(n)
        n = n.strip()
        return n or None
    except Exception:
        return None
