# Entwicklerhinweise

## Version 1.1
- Neues Panel im Clip Editor unter *Track* mit einem Button, der den Operator `clip.panel_button` aufruft.

## Version 1.2
- Der Button befindet sich jetzt in einem eigenen Panel (`CLIP_PT_button_panel`).

## Version 1.3
- Das Button-Panel liegt nun im separaten Tab `Addon`.

## Version 1.4
- Der Operator `clip.panel_button` baut jetzt 50%-Proxys mit Qualit\u00e4t 50 im Ordner `//proxies`.

## Version 1.4.1
- Das Addon verwendet nur `clip.proxy.directory`. Ein explizites `clip.proxy.use_proxy_custom_directory` ist nicht mehr erforderlich.

## Version 1.5
- Vor dem Proxy-Bau wird das Proxy-Verzeichnis (falls vorhanden) gel\u00f6scht, bevor neue Proxys erstellt werden.

- Neuer Button "Marker", der einen Timeline Marker setzt.

## Version 1.7
- Neuer Operator `clip.clean_new_tracks` entfernt `NEW_`-Tracks, die im aktuellen
  Frame näher als die berechnete Pixel-Distanz zu `GOOD_`-Tracks liegen.

## Version 1.7.1
- `clip.clean_new_tracks` besitzt jetzt eine Option `detect`, um die Feature-
  Erkennung wahlweise zu überspringen.
- Fehler beim Löschen von Tracks werden abgefangen.

## Version 1.8
- Der "Marker"-Button setzt nun einen Clip Marker (Movie Tracking Marker) im
  Clip Editor statt eines Timeline Markers.

## Version 1.9
- Der "Marker"-Button führt nun `clip.detect_features()` aus. Dabei werden
  `detection_threshold`, `min_distance` und `detection_margin` gesetzt.

## Version 1.10
- Die Parameter für `clip.detect_features()` werden nun direkt beim
  Operatoraufruf übergeben, da die entsprechenden Eigenschaften im
  `SpaceClipEditor` nicht mehr existieren.

## Version 1.11
- Der Parameter `detection_distance` wurde durch `min_distance`
  ersetzt, der nun beim Aufruf von `clip.detect_features()`
  verwendet wird.

## Version 1.12
- Beim Aufruf von `clip.detect_features()` werden die verwendeten Werte für
  `margin` und `min_distance` in der Konsole ausgegeben. Beide Werte sind
  nun ganze Zahlen.

## Version 1.13
- Der "Marker"-Button führt jetzt eine dynamische Feature-Erkennung durch und
  entfernt NEW_-Tracks, die zu nahe an GOOD_-Tracks liegen.

## Version 1.14
- Der aktive Track wird über `space.tracking.active_track` ermittelt,
  wodurch keine Attribute mehr auf `clip.tracking` fälschlich
  zugegriffen werden.

## Version 1.15
- Neue Operatoren: `clip.detect_button`, `clip.prefix_new`,
  `clip.distance_button`, `clip.delete_selected` und `clip.count_button`.
- Das Panel zeigt nun diese Buttons für einen modularen Workflow.

## Version 1.16
- `clip.detect_button` verwendet nun einen Mindestabstand von 5 % der
  Clip-Breite und einen Margin von 1 % der Breite.

## Version 1.17
- `clip.distance_button` deselektiert jetzt alle Tracks und
  markiert ausschließlich NEW_-Tracks, die innerhalb des
  Mindestabstands zu GOOD_-Tracks liegen.

## Version 1.18
- `clip.delete_selected` überprüft jetzt, ob überhaupt Tracks
  ausgewählt sind und bricht andernfalls mit einer Warnung ab.


## Version 1.19
- `clip.count_button` selektiert nun alle `NEW_`-Tracks, zählt sie und hebt die Selektion auf, wenn die Anzahl im erwarteten Bereich liegt.

## Version 1.20
- `clip.detect_button` berechnet den Threshold anhand der Anzahl vorhandener
  `NEW_`-Tracks und gibt sowohl diese Zahl als auch den Wert des Thresholds in
  der Konsole aus.

## Version 1.21
- `clip.count_button` speichert die gezählte Anzahl als `Scene.nm_count`.
- Liegt sie außerhalb des Zielbereichs, werden stattdessen alle `TRACK_`-Tracks
  selektiert.

## Version 1.22
- Das Panel enthält nun ein Eingabefeld "Marker / Frame" über dem Proxy-Button.
- Der Proxy-Button steht direkt am Anfang des Panels.
- Nach dem "Count"-Button wird ein zusätzlicher "Delete"-Button angezeigt.
