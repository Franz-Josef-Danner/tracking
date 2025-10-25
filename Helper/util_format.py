def fmt8(x: float) -> str:
    """Max. 8 Nachkommastellen, ohne unnötige Nullen/Dezimalpunkt."""
    try:
        s = f"{float(x):.8f}".rstrip("0").rstrip(".")
        return s if s != "-0" else "0"
    except Exception:
        return str(x)