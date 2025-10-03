# Kaiserlich Tracker (Blender Add-on)

Adaptiver Mehrfach-Zyklus zur automatischen Marker / Feature Detection im Movie Clip Editor.

## Features
- Zielbereich für Markerzahl pro Frame (abgeleitet von Property)
- Dynamische Anpassung von Threshold, Pattern Size und Min Distance
- Abbruchbedingungen (max Zyklen, Mindest-Threshold)
- Cleanup von Duplikaten zwischen Iterationen
- UI Panel im Clip Editor (Sidebar > Kaiserlich)

## Installation
1. Ordner `kaiserlich_tracker` zippen (Inhalt, nicht den gesamten Repo-Ordner):
2. In Blender: Edit > Preferences > Add-ons > Install... > ZIP wählen
3. Add-on aktivieren.

## Nutzung
1. Movie Clip öffnen & zu gewünschtem Frame navigieren
2. Sidebar (N) > Tab "Kaiserlich" öffnen
3. Wert "Marker / Frame" einstellen (Richtwert)
4. "Detect Cycle" klicken
5. Fortschritt in der Konsole / Status im Panel beobachten

## Interne Logik (Kurzfassung)
1. Bootstrap berechnet Start-Parameter
2. Pro Zyklus:
   - Snapshot alte Marker
   - Neue Features detektieren
   - Duplikate löschen (Abstand < min_distance)
   - Kontrolle: Markeranzahl im Zielband?
   - Falls nicht: Parameter anpassen und erneut
3. Erfolg speichert Pattern Size & letzte Markeranzahl

## Erweiterungsideen
- KD-Tree für Duplicate Detection (Performance)
- Logging Panel / Debug Switch
- Speicherung pro Clip statt Scene-Property
- Optional: Adaptive search_size Nutzung

## Lizenz
Ohne explizite Lizenz – bitte ergänzen falls Verteilung geplant.

---
Generated Grundgerüst – passe es nach Bedarf an.
