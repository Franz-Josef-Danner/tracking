# Kaiserlich Tracker

Blender Add-on Panel im Movie Clip Editor (Sidebar / UI Region) mit einem Eingabefeld
"Marker per Frame" (Default 25) und einem Button "Detect Cyclus".

## Installation
1. Ordner als ZIP packen (Inhalt des Verzeichnisses `tracking`).
2. In Blender: Edit > Preferences > Add-ons > Install... und ZIP wählen.
3. Add-on aktivieren: "Kaiserlich Tracker".

## Nutzung
1. Movie Clip Editor öffnen.
2. Sidebar (Taste N) öffnen.
3. Tab "Kaiserlich Tracker" wählen.
4. Wert für "Marker per Frame" setzen.
5. Button "Detect Cyclus" klicken (aktuell Platzhalter, schreibt Meldung ins Info-Fenster / Statuszeile).

## Weiterentwicklung
- Logik für Zyklus-Detektion in `operators/operator.py` innerhalb `execute` implementieren.
- Evtl. eigene PropertyGroup statt direkte Scene-Property nutzen.
- Persistente Einstellungen über Add-on Preferences bereitstellen.
