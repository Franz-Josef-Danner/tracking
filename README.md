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
Seit Version 1.22 befindet sich oben im Panel ein Eingabefeld "Marker / Frame".
Der Proxy-Button steht nun direkt darunter und nach dem "Count"-Button erscheint
ein weiterer "Delete"-Button.
Seit Version 1.23 verwendet der "Count"-Button den Wert aus "Marker / Frame"
zur Berechnung des erwarteten Bereichs. Liegt die Anzahl der NEW_-Tracks
innerhalb dieses Bereichs, werden sie in TRACK_-Tracks umbenannt und die
Auswahl wird aufgehoben.
Der Standardwert des Feldes beträgt nun 20.
Seit Version 1.24 deaktiviert der "Detect"-Button zunächst den Proxy.
Seit Version 1.25 berechnet der "Detect"-Button den Threshold mit dem Wert aus
"Marker / Frame". Dabei wird in der Konsole ausgegeben, wenn die Formel
angewendet wird. Der "Count"-Button gibt den NM-Wert in der Konsole aus und setzt
ihn bei ausreichender Track-Anzahl wieder auf 0.
Seit Version 1.26 verwendet der "Detect"-Button den gespeicherten Wert
`Scene.nm_count`, um den Threshold zu berechnen, anstatt die NEW_-Tracks erneut
zu zählen.
Seit Version 1.27 werden Margin und Mindestabstand auf Basis von 1 % bzw.
5 % der Breite mit `log10(threshold * 10000000000) / 10` skaliert und die
Berechnungsformeln sowie Ergebnisse in der Konsole ausgegeben.
Seit Version 1.28 merkt sich der "Detect"-Button den zuletzt
verwendeten Threshold-Wert und nutzt ihn f\u00fcr die n\u00e4chste Berechnung.
Seit Version 1.29 gibt es einen "All"-Button, der alle Buttons bis auf den
Proxy-Button nacheinander ausf\u00fchrt.
Seit Version 1.30 wiederholt dieser Button den Ablauf maximal zehnmal,
bis TRACK_-Marker vorhanden sind.
Seit Version 1.31 wird im Panel nur noch ein Delete-Button angezeigt.
Seit Version 1.32 zeigt das Panel nur noch den Proxy-Button und den "All"-Button.
Seit Version 1.33 verfügt das Panel über einen "Track"-Button, der TRACK_-Marker
rückwärts und anschließend wieder vorwärts bis zum aktuellen Frame verfolgt.
Seit Version 1.34 aktiviert der "Track"-Button vor dem Tracking den Proxy.
Seit Version 1.35 gibt der "Track"-Button Ausgaben zur Marker-Selektion,
dem gespeicherten Frame und dem Zurücksetzen des Playheads in der Konsole aus.
Seit Version 1.36 verfolgt der "Track"-Button TRACK_-Marker Frame für Frame bis
 zum Endframe und meldet jeden Schritt in der Konsole.
Seit Version 1.37 bricht das Tracking ab, sobald alle selektierten Marker verloren sind.
Seit Version 1.38 aktualisiert der Track-Button die Anzeige jedes Frame und macht den Fortschritt sichtbar.
Seit Version 1.39 führt der Track-Button wieder nur ein einmaliges Rückwärts-
und Vorwärts-Tracking der TRACK_-Marker aus.
Seit Version 1.40 meldet der Track-Button jeden Arbeitsschritt in der Konsole
und pausiert beim Vorwärts-Tracking alle zehn Frames für 0,1 Sekunden.
Seit Version 1.41 verfolgt der Track-Button die ausgewählten Marker maximal
zehn Frames nach vorne und bricht am Endframe ab.
Seit Version 1.42 führt der Track-Button die TRACK_-Marker bis zu zehn Frames
rückwärts und danach wieder vorwärts, wobei er Start- und Endframe beachtet.
Seit Version 1.43 setzt der Track-Button den Frame-Bereich temporär und nutzt
`sequence=True`, um die Marker bis zu zehn Frames zurück und anschließend
vorwärts zu verfolgen.
Seit Version 1.44 verfolgt der Track-Button die TRACK_-Marker in
Zehnerschritten, bis keine mehr aktiv sind.
Seit Version 1.45 verwendet der Detect-Button einen minimalen
`detection_threshold` von 0.0001 statt 0.001.
Seit Version 1.47 prüft der Track-Button nach jedem Zehnerblock,
ob noch TRACK_-Marker aktiv sind und beendet das Tracking,
sobald keine mehr vorhanden sind.
Seit Version 1.48 erkennt der Track-Button Marker als inaktiv, wenn sie stummgeschaltet sind oder Koordinaten von (0,0) besitzen.
