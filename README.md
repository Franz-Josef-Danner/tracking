# Kaiserlich Tracker (Prototyp)

Umsetzung des bereitgestellten Pseudocode-Workflows als Blender Add-on Modulstruktur. Dieses Repository enthält nur den Python-Code – keine direkte Testumgebung (Blender muss lokal installiert sein).

## Funktionsumfang

* UI Panel im Movie Clip Editor (Sidebar -> Kaiserlich)
* Szene-Property `kaiserlich_marker_per_frame`
* Operator `clip.kaiserlich_detect_cyclus`
* Bootstrap der Startparameter (margin, min distance, pattern/search size, threshold, Zielbereich)
* Snapshot vorhandener Marker im aktuellen Frame
* Feature Detection via `bpy.ops.clip.detect_features`
* Sammlung neuer Marker
* Cleanup: Entfernt neue Marker, die zu nah an alten liegen (Pixelabstand separat horizontal/vertikal)
* Kontrolllogik: Prüft Anzahl neuer Marker gegen Toleranz und passt threshold/pattern-size oder min-distance an

## Rekursiver Zyklus

Der Ablauf läuft rekursiv bis:

* Markeranzahl im Zielbereich liegt, oder
* Threshold unter 0.1 fällt, oder
* Eine maximale Rekursionstiefe (12) erreicht ist.

## Installation

1. Ordner `kaiserlich_tracker` zippen (Inhalt inklusive `__init__.py`).
2. In Blender: Edit > Preferences > Add-ons > Install…
3. Add-on aktivieren.
4. Movie Clip laden, Frame wählen.
5. Sidebar (N) öffnen: Tab "Kaiserlich".
6. Ziel-Markeranzahl einstellen und "Detect Cyclus" drücken.

## Hinweise / ToDo

* Feintuning der Heuristiken (Faktoren 0.025, 0.01 etc.).
* Evtl. statt Muten echte Entfernung einzelner Marker (API-Recherche: Track.markers löschen).
* Logging optional auf `bpy.app.debug` konditionieren.
* Abbruchbedingung ggf. auch über Zeit / Anzahl erzeugter Marker erweitern.
* Option hinzufügen: Nur neue Marker vs. alle Marker (Mute-Strategie anpassen).

## Lizenz

Prototyp – weitere Lizenzierung nach Bedarf ergänzen.

---

Viel Erfolg beim Testen in Blender!
