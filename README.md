# Kaiserlich Tracksycle

Ein Blender-Add-on, das das automatische Tracking von Markern vereinfacht.

## Installation
1. Dieses Repository als ZIP herunterladen.
2. In Blender unter **Edit → Preferences → Add-ons → Install...** die ZIP-Datei auswählen.
3. Das Add-on **Kaiserlich Tracksycle** aktivieren.

## Verwendung
1. Movie Clip Editor öffnen und einen Clip laden.
2. In der Sidebar den Tab **"Kaiserlich"** wählen.
3. **Auto Track** drücken. Das Add-on erkennt Features, verfolgt sie und bereinigt neue Marker.
4. **Detect Features** führt nur die Feature-Erkennung aus.
5. **Tracking Marker** startet den benutzerdefinierten Workflow.
6. Optional können im Panel weitere Parameter angepasst werden:
   - **Minimale Markeranzahl**
   - **Tracking-Länge**
   - **Fehler-Schwelle**
   - **Debug Output aktivieren**
   - **Detection-Einstellungen des Clip Editors** (Threshold, Distance, Margin)

## Bekannte Einschränkungen
- Blender **4.0** oder neuer erforderlich.
- Proxy-Funktionen werden automatisch ein- und ausgeschaltet.

Weitere technische Details und Informationen zur Code-Architektur findest du in [DEVELOPER.md](DEVELOPER.md).

## Lizenz
Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
