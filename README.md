# Simple Blender Addon

Dieses Verzeichnis enthaelt ein minimales Blender Addon für Blender 4.4 oder neuer. Kopiere den Ordner `my_blender_addon` in deinen Blender Addons-Ordner und aktiviere das Addon in den Einstellungen.

Das Addon stellt einen simplen Operator bereit, der im Info-Bereich eine Meldung ausgibt.

Seit Version 1.1 gibt es im Clip Editor unter *Track* ein neues Panel mit einem Button. Dieser Button ruft einen Operator auf, der eine Meldung in Blender ausgibt.

Seit Version 1.2 befindet sich der Button in einem eigenen Panel.
Seit Version 1.3 liegt dieses Panel in einem separaten Tab "Addon" im Clip Editor.
Seit Version 1.4 baut der Button Proxys mit 50 % Gr\u00f6\u00dfe und einer Qualit\u00e4t von 50 im benutzerdefinierten Verzeichnis `//proxies`.
Seit Version 1.4.1 wird nur `clip.proxy.directory` gesetzt. Das Attribut `clip.proxy.use_proxy_custom_directory` entfällt.
Seit Version 1.5 entfernt der Button vorhandene Proxy-Verzeichnisse, bevor neue Proxys erstellt werden.
Seit Version 1.6 gibt es einen zusätzlichen "Marker"-Button, der einen Timeline Marker setzt.
Seit Version 1.7 bietet das Panel einen Button "Clean NEW Tracks", der neu erkannte Tracks l\u00f6scht, wenn sie zu nah an bestehenden GOOD_ Tracks liegen.
Seit Version 1.7.1 kann derselbe Operator auch ohne erneute Feature-Erkennung ausgef\u00fchrt werden.
Seit Version 1.8 setzt der "Marker"-Button nun einen Clip Marker (Movie Tracking
Marker) im Clip Editor anstatt eines Timeline Markers.
Seit Version 1.9 ruft der "Marker"-Button `clip.detect_features()` auf und setzt
vorher die Parameter `detection_threshold`, `min_distance` und
`detection_margin`.
Seit Version 1.10 werden diese Parameter direkt an den Operator
`clip.detect_features()` übergeben, da sie nicht mehr als
Eigenschaften von `SpaceClipEditor` verfügbar sind.
Seit Version 1.11 heißt der Parameter für den Mindestabstand
`min_distance` und ersetzt das bisherige `detection_distance`.
Seit Version 1.12 werden die verwendeten Werte für `margin` und `min_distance`
beim Aufruf von `clip.detect_features()` in der Konsole ausgegeben.
Seit Version 1.13 führt der "Marker"-Button eine erweiterte
Feature-Erkennung mit dynamischen Parametern aus.
Seit Version 1.14 wird der aktive Track direkt über
`space.tracking.active_track` angesprochen, um die Pattern- und
Search-Size zu setzen.
Seit Version 1.15 bietet das Addon separate Buttons zum Detecten,
Umbenennen, Distanzprüfen, Löschen und Zählen von Tracks.
Seit Version 1.16 verwendet die Feature-Erkennung einen Margin von 1 %
und einen Mindestabstand von 5 % der Clip-Breite.
Seit Version 1.17 wählt der "Distance"-Button nur noch NEW_-Tracks aus,
die zu nah an GOOD_-Tracks liegen.
Seit Version 1.18 führt der "Delete"-Button nur dann eine
Löschung aus, wenn tatsächlich Tracks ausgewählt sind.
Seit Version 1.19 wählt der "Count"-Button alle NEW_-Tracks aus, zählt sie und hebt die Selektion wieder auf, wenn ihre Anzahl im erwarteten Bereich liegt.
Seit Version 1.20 gibt der "Detect"-Button die Zahl der NEW_-Tracks und den berechneten Threshold in der Konsole aus.
Seit Version 1.21 speichert der "Count"-Button das Ergebnis als `Scene.nm_count` und
wählt bei Abweichungen stattdessen alle TRACK_-Tracks aus.
