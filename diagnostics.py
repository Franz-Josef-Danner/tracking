"""Hilfsfunktionen zur Fehlersuche bei UTF-8 Decode Errors in Blender Addons.

In Blender-Python wird jeder .py Source beim Import als UTF-8 dekodiert. Ein Fehler
wie:  'utf-8' codec can't decode byte 0xd0 in position 0
weist fast immer auf eine Datei hin, die nicht als UTF-8 (ohne BOM) gespeichert ist
oder korrupt wurde. Dieses Modul bietet Utilities, die innerhalb von Blender
ausgeführt werden koennen, um das fehlerhafte File einzugrenzen.

Nutzung (im Blender Python Console oder Text Editor > Run Script):

    import tracking.diagnostics as diag
    diag.scan_source_tree()
    # oder detaillierter:
    diag.verbose_import_trace()

Danach die Ausgabe im System-Konsole / Blender-Konsole prüfen.
"""
from __future__ import annotations

import importlib
import io
import os
import sys
import traceback
from pathlib import Path
from types import ModuleType


def _is_probably_binary(data: bytes) -> bool:
    # Sehr einfache Heuristik: viele Nullbytes oder >30% Bytes < 9 außerhalb druckbarer Range
    if not data:
        return False
    if b"\x00" in data:
        return True
    slice_ = data[:256]
    weird = sum(1 for b in slice_ if b < 9)
    return weird / max(1, len(slice_)) > 0.30


def scan_source_tree(root: str | Path | None = None, max_bytes: int = 4096) -> None:
    """Scant alle .py Dateien unterhalb des Addon-Roots und versucht UTF-8 zu dekodieren.

    Gibt Warnungen aus bei:
      * Nicht-UTF8 Dekodierbarkeit
      * Vorhandensein einer BOM
      * Verdacht auf Binärdaten
    """
    if root is None:
        # Versuche Root aus diesem Dateiort abzuleiten (tracking Paket Oberordner)
        root = Path(__file__).resolve().parent
    root = Path(root)
    print(f"[diagnostics] Scan root={root}")
    problems = 0
    for py in root.rglob("*.py"):
        try:
            data = py.read_bytes()
        except Exception as e:  # noqa: BLE001
            problems += 1
            print(f"[diagnostics][ERROR] Kann {py} nicht lesen: {e}")
            continue
        marker = []
        if data.startswith(b"\xEF\xBB\xBF"):
            marker.append("BOM")
        if _is_probably_binary(data):
            marker.append("BINARY_SUSPECT")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as ue:
            problems += 1
            marker.append(f"DECODE_FAIL:{ue}")
        if marker:
            print(f"[diagnostics][WARN] {py.relative_to(root)} => {', '.join(marker)}")
    if problems == 0:
        print("[diagnostics] Keine offensichtlichen Encoding-Probleme gefunden.")
    else:
        print(f"[diagnostics] Fertig. Dateiprobleme gesamt: {problems}")


class _ImportTracer:
    def __enter__(self):  # noqa: D401
        self._orig_import = builtins.__import__  # type: ignore[attr-defined]

        def traced_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: D401
            print(f"[diagnostics][import] name={name} fromlist={fromlist} level={level}")
            try:
                mod = self._orig_import(name, globals, locals, fromlist, level)  # type: ignore[arg-type]
            except Exception:
                print(f"[diagnostics][import][ERROR] beim Import von {name}:\n{traceback.format_exc()}")
                raise
            return mod

        import builtins  # local import for safety
        builtins.__import__ = traced_import  # type: ignore[attr-defined]
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: D401
        import builtins  # noqa: WPS433
        builtins.__import__ = self._orig_import  # type: ignore[attr-defined]
        if exc:
            print(f"[diagnostics] Ausnahme waehrend Trace: {exc}")
        return False


def verbose_import_trace(module_name: str = "tracking") -> ModuleType | None:
    """Erzwingt einen frischen Import mit Trace-Ausgabe.

    1. Entfernt vorhandene Einträge aus sys.modules fuer das Package
    2. Aktiviert Import-Hook
    3. Importiert neu und fängt ImportError / UnicodeDecodeError ab
    """
    to_purge = [m for m in sys.modules if m == module_name or m.startswith(module_name + ".")]
    for m in to_purge:
        sys.modules.pop(m, None)
    print(f"[diagnostics] Purged {len(to_purge)} Module-Eintraege fuer '{module_name}'")
    with _ImportTracer():
        try:
            return importlib.import_module(module_name)
        except Exception:
            print("[diagnostics] Import fehlgeschlagen:\n" + traceback.format_exc())
            return None


def quick_selftest():  # pragma: no cover - rein manuell
    print("[diagnostics] Starte quick_selftest()")
    scan_source_tree()
    verbose_import_trace("tracking")
    print("[diagnostics] quick_selftest() abgeschlossen")


__all__ = [
    "scan_source_tree",
    "verbose_import_trace",
    "quick_selftest",
]
