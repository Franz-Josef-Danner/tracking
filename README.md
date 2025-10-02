# Kaiserlich Tracker

Blender Add-on für einen adaptiven Feature-Detection-Zyklus im Movie Clip Editor.

## Installation

1. Ordner `tracking` zippen (Inhalt muss `__init__.py` an der Wurzel enthalten)
2. Blender > Edit > Preferences > Add-ons > Install...
3. Zip auswählen und aktivieren.

## Nutzung

- Öffne den Movie Clip Editor und lade einen Clip.
- Sidebar (N) öffnen, Tab "Kaiserlich" wählen.
- Zielwert "Marker per Frame" anpassen.
- Button "Detect Cyclus" drücken.

Das Add-on führt mehrere Iterationen aus, um eine Markeranzahl innerhalb eines Toleranzbandes (`ug` bis `og`) zu erreichen. Parameter wie Threshold und Mindestabstand werden dynamisch angepasst.

## Ablauf (Kurz)

1. `bootstrap` berechnet abgeleitete Parameter.
2. Bestehende Marker des aktuellen Frames werden gemerkt (`snapshot`).
3. Neue Features werden detektiert (`detect_features`).
4. Direkte Duplikate (räumliche Nähe) werden bereinigt (`cleanup`).
5. `control_cycle` bewertet Ergebnis und entscheidet über Abbruch oder Anpassung und Wiederholung.

Die Implementierung ist iterativ (max 15 Zyklen) statt rekursiv.

## Module

- UI/ui.py: Panel + Property
- Operator/operator.py: Startpunkt des Zyklus
- Helper/*.py: Logik-Bausteine

## Anpassungen / Ideen

- Parameter `pz` und `sz` werden aktuell nicht aktiv genutzt – könnten für skalierte Region-of-Interest Strategien dienen.
- Logging auf `bpy.types.WindowManager` Report-Log erweitern.
- Optionales Limit für Gesamtmarker im Clip.

## Lizenz

MIT (optional anpassen)
