# Entwicklerhinweise

Dieses Dokument fasst die genutzten Funktionen der Blender Python API zusammen. Es dient als Referenz für die im Add-on verwendeten Varianten und Methoden.

## Allgemeines

Bei der Erstellung und Bearbeitung von Blender Skripten und Add-ons sollten stets die aktuellen Blender Code Standards und die verfügbaren Kommandos konsultiert werden, um funktionsfähigen Code zu gewährleisten.

## Zentrale Klassen und Funktionen

- `bpy.types.Operator` – Basisklasse für eigene Operatoren.
- `bpy.types.Panel` – Grundlage für UI-Panels im Clip Editor.
- `bpy.ops.clip.detect_features()` – startet die Feature-Erkennung; wichtige Parameter sind `threshold`, `margin` und `min_distance`.
- `bpy.ops.clip.rebuild_proxy()` – erzeugt Proxys für Movie Clips.
- `bpy.ops.clip.delete_track()` – löscht ausgewählte Tracks.
- `bpy.path.abspath(path)` – wandelt einen relativen in einen absoluten Pfad um.
- `bpy.utils.register_class()` und `bpy.utils.unregister_class()` – registrieren bzw. entfernen Klassen.
- `bpy.props.IntProperty` und `bpy.props.FloatProperty` – definieren eigene Properties für Szenen und Operatoren.

## Eigene Operatoren

Das Add-on implementiert mehrere Operatoren wie `clip.panel_button`, `clip.detect_button`, `clip.prefix_new` und andere. Sie leiten sich von `bpy.types.Operator` ab und greifen über `context.space_data.clip` direkt auf den aktiven Movie Clip zu.

## Panels

Benutzeroberflächen werden mit Klassen auf Basis von `bpy.types.Panel` erstellt. Das Haupt-Panel befindet sich im Clip Editor unter dem Tab "Addon" und bietet Zugriff auf die beschriebenen Operatoren.

## Registrierung der Klassen

Alle Operator- und Panel-Klassen werden innerhalb der Funktion `register()` mit `bpy.utils.register_class` registriert. Zusätzlich fügt `register()` der Szene eigene Properties wie `marker_frame` oder `nm_count` hinzu. Beim Beenden des Add-ons entfernt `unregister()` diese Elemente wieder.

