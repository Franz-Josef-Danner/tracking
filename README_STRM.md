# STRM Feature Tracker (Blender Add-on)

Ein minimales Add-on für Blender 3.6+, das eine STRM (Spatio-Temporal Region Map) Analyse auf dem aktiven Movie Clip ausführt. Es teilt das Bild in Tiles (z. B. 4x6) und berechnet pro Tile einfache Metriken: Texture, Motion, Divergence.

## Installation

1. Dieses Verzeichnis zippen (nur den Ordner `strm_tracker/` mit Inhalt):
   - Unter Linux/macOS im Terminal im Workspace-Root:

     ```bash
     zip -r strm_tracker.zip strm_tracker
     ```
2. Blender öffnen > Edit > Preferences > Add-ons > Install... > `strm_tracker.zip` wählen und installieren.
3. Add-on aktivieren.

## Nutzung

- Wechsle in den Movie Clip Editor und lade einen Clip.
- Rechts in der Sidebar findest du die Kategorie "STRM" und den Button "STRM Analyse".
- Es werden 10 Frames ab dem Start (Frame 0) gelesen, in 4x6 Tiles unterteilt und Werte in der Konsole ausgegeben.

Hinweis: Die API `bpy` ist nur innerhalb von Blender verfügbar. Lint-Fehler in externen Editoren sind normal.

## Abhängigkeiten

- NumPy (wird mit Blender in der Regel gebündelt)
- OpenCV-Python (optional; aktuelles Minimalbeispiel nutzt nur NumPy)

Falls OpenCV fehlt, kannst du es in der Python-Umgebung von Blender nachinstallieren:

```bash
/path/to/blender/python/bin/python3 -m ensurepip --upgrade
/path/to/blender/python/bin/pip install --upgrade pip
/path/to/blender/python/bin/pip install opencv-python
```

## Nächste Schritte

- Overlay der Tile-Ergebnisse im Viewer zeichnen
- Weitere Metriken: Flicker, Gradienten-Divergenz, KLT-Seed-Vorschläge
- Operator-Properties für Tile-Größe, Frame-Bereich
- Logging/KPIs und Presets
