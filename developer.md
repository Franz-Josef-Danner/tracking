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

## Version 1.23
- `clip.count_button` verwendet jetzt den Wert aus `Scene.marker_frame` zur
  Berechnung des erwarteten Bereichs. Liegt die Anzahl der `NEW_`-Tracks in
  diesem Bereich, werden sie in `TRACK_` umbenannt, die Auswahl wird
  aufgehoben und `Scene.nm_count` zurückgesetzt. Das Feld besitzt nun einen
  Standardwert von 20.

## Version 1.24
- `clip.detect_button` deaktiviert nun zuerst den Proxy, bevor die
  Feature-Erkennung gestartet wird.

## Version 1.25
- `clip.count_button` gibt den Wert von `Scene.nm_count` in der Konsole aus und
  setzt ihn bei ausreichender Track-Anzahl wieder auf `0`.
- `clip.detect_button` nutzt nun den Wert aus `Scene.marker_frame`, um den
  Threshold anhand der Formel
  `threshold_value * ((NM + 0.1) / (marker_frame * 4))` zu berechnen und meldet,
  wann diese Formel angewendet wird.

## Version 1.26
- `clip.detect_button` verwendet jetzt den in `Scene.nm_count` gespeicherten
  NM-Wert für die Threshold-Berechnung und zählt die NEW_-Tracks nicht mehr neu.

## Version 1.27
- `clip.detect_button` berechnet Margin und Mindestabstand weiterhin aus 1 %
  bzw. 5 % der Breite und skaliert diese Werte nun zusätzlich mit dem Faktor
  `log10(threshold * 10000000000) / 10`. Die Formeln und Ergebnisse werden in der Konsole ausgegeben.

## Version 1.28
- `clip.detect_button` speichert den berechneten Threshold-Wert in
  `Scene.threshold_value` und verwendet ihn beim n\u00e4chsten Durchlauf als
  Ausgangswert.

## Version 1.29
- Neuer Operator `clip.all_buttons` f\u00fchrt Detect, NEW, Distance, Delete, Count
  und ein weiteres Delete in dieser Reihenfolge aus.
- Das Panel enth\u00e4lt nun einen "All"-Button, der diese Funktion aufruft.

## Version 1.30
- `clip.all_buttons` wiederholt den Ablauf, bis `TRACK_`-Marker
  vorhanden sind oder zehn Durchläufe erreicht wurden.

## Version 1.31
- Der zusätzliche Delete-Button im Panel wurde entfernt.

## Version 1.32
- Das Panel zeigt nur noch den Proxy-Button und den "All"-Button an.

## Version 1.33
- Neuer Operator `clip.track_sequence` verfolgt TRACK_-Marker erst rückwärts
  und anschließend wieder vorwärts bis zum gespeicherten Frame.
- Das Panel enthält nun einen zusätzlichen "Track"-Button.

## Version 1.34
- `clip.track_sequence` aktiviert nun vor dem Tracking den Proxy.

## Version 1.35
- `clip.track_sequence` gibt beim Selektieren der TRACK_-Marker,
  beim Speichern und Wiederherstellen des Playhead-Frames
  Meldungen in der Konsole aus.

## Version 1.36
- `clip.track_sequence` verfolgt die TRACK_-Marker jetzt Frame für Frame bis zum
  Endframe und gibt den Fortschritt in der Konsole aus.

## Version 1.37
- `clip.track_sequence` bricht das Tracking ab, sobald keine aktiven TRACK_-Marker
  mehr vorhanden sind.

## Version 1.38
- `clip.track_sequence` zeigt nun jeden getrackten Frame im Clip Editor an und
  pausiert kurz, um das UI-Update sichtbar zu machen.

## Version 1.39
- `clip.track_sequence` verwendet wieder die einfache Variante: TRACK_-Marker
  werden einmal rückwärts und danach vorwärts verfolgt.

## Version 1.40
- `clip.track_sequence` gibt die Arbeitsschritte aus und legt beim
  Vorwärts-Tracking nach jeweils zehn Frames eine Pause von 0,1 Sekunden ein.

## Version 1.41
- `clip.track_sequence` verfolgt nur noch die aktuell ausgewählten Marker
  schrittweise vorwärts. Es werden höchstens zehn Frames getrackt und das
  Tracking stoppt am Endframe.

## Version 1.42
- `clip.track_sequence` wählt automatisch alle `TRACK_`-Marker aus,
  verfolgt sie bis zu zehn Frames rückwärts und danach wieder vorwärts.
  Der zuvor gespeicherte Frame wird zwischen den Richtungen
  wiederhergestellt.

## Version 1.43
- `clip.track_sequence` setzt den Frame-Bereich temporär und verwendet
  `sequence=True`, um die Marker jeweils maximal zehn Frames rückwärts
  und danach wieder vorwärts zu verfolgen.

## Version 1.44
- `clip.track_sequence` arbeitet in Schritten von zehn Frames und wiederholt
  das Tracking, bis keine ausgewählten `TRACK_`-Marker mehr vorhanden sind.

## Version 1.45
- `clip.detect_button` setzt den minimalen `detection_threshold` nun auf
  `0.0001` statt `0.001`.

## Version 1.46
- `clip.track_sequence` gab nach jedem Tracking-Schritt die Anzahl
  der noch aktiven TRACK_-Marker aus.

## Version 1.47
- `clip.track_sequence` pr\xFCft am Ende jedes Zehnerblocks, ob noch
  TRACK_-Marker aktiv sind und beendet das Tracking gegebenenfalls fr\xFChzeitig.


## Version 1.48
- `clip.track_sequence` betrachtet Marker als inaktiv, wenn sie stummgeschaltet sind oder Koordinaten von (0,0) aufweisen.

## Version 1.49
- `clip.track_sequence` meldet nach jedem Tracking-Schritt die Anzahl der noch
  aktiven `TRACK_`-Marker.

## Version 1.50
- `clip.track_sequence` verwendet nun Bl\xF6cke von 25 Frames und pr\xFCft nach
  jedem dieser Abschnitte erneut, ob noch TRACK_-Marker aktiv sind.

## Version 1.51
- `clip.track_sequence` berechnet die Blockgr\xF6\xDFe dynamisch, indem der
  verbleibende Bereich in vier Teile aufgeteilt wird.

## Version 1.52
- Neue Operatoren `clip.live_track_forward` und `clip.live_track_backward`
  verwenden einen Timer, um w\u00e4hrend des UI-Trackings zu \u00fcberpr\u00fcfen,
  ob noch aktive `TRACK_`-Marker vorhanden sind und stoppen das Tracking,
  sobald keine mehr existieren.

## Version 1.53
- Neuer Operator `clip.proxy_track` ruft automatisch `clip.panel_button` auf,
  speichert den aktuellen Frame und verfolgt `TRACK_`-Marker jeweils zehn
  Frames r\u00fcckw\u00e4rts und danach wieder vorw\u00e4rts zum gespeicherten Frame.

## Version 1.54
- `clip.proxy_track` deaktiviert zun\u00e4chst den Proxy, merkt sich den
  aktuellen Frame und w\u00e4hlt alle `TRACK_`-Marker aus. Anschlie\u00dfend werden
  die Marker zehn Frames r\u00fcckw\u00e4rts getrackt, der Playhead wird
  wiederhergestellt und das Tracking l\u00e4uft vorw\u00e4rts weiter.

## Version 1.55
- `clip.proxy_track` nutzt beim Rückwärts-Tracking den dynamischen Block-Algorithmus aus `clip.track_sequence` und wiederholt die Schritte, bis keine TRACK_-Marker mehr aktiv sind. Anschließend wird der gespeicherte Frame wiederhergestellt und ohne Unterteilung vorwärts getrackt.

## Version 1.56
- `clip.proxy_track` aktiviert nun den Proxy bevor das Tracking beginnt.

## Version 1.57
- Die Buttons 'Proxy+Track', 'Live Fwd' und 'Live Back' wurden entfernt.

## Version 1.58
- Neues Eingabefeld 'Frames/Track' unterhalb von 'Marker / Frame' im Panel.

## Version 1.59
- Neuer Button 'Tracking Length' löscht TRACK_-Marker, deren Länge
  unter dem Wert aus 'Frames/Track' liegt.

## Version 1.60
- `clip.track_sequence` berechnet die Blockgröße für das Rückwärts-Tracking nur einmal als Hälfte des Bereichs.

## Version 1.61
- `clip.tracking_length` gibt den verwendeten Frames/Track-Wert in der Konsole aus.

## Version 1.62
- `clip.track_sequence` berechnet die Blockgröße beim Rückwärts-Tracking mit `GF / log10(GF*GF)`.

## Version 1.63
- `clip.tracking_length` wählt die zu kurzen TRACK_-Marker aus,
  löscht sie und benennt verbleibende TRACK_-Marker in GOOD_ um.

## Version 1.64
- Neuer Button `clip.playhead_to_frame` springt zum ersten Frame mit weniger
  GOOD_-Markern als im Feld "Marker / Frame" vorgegeben.

## Version 1.65
- `clip.all_buttons` wurde zu einem modalen Operator, der Detect,
  Track, Tracking Length und Playhead to Frame kombiniert.
  Nach jedem Durchlauf wird der Proxy neu erstellt. Der Zyklus
  endet, wenn der Benutzer Esc drückt oder kein weiterer Frame
  gefunden wird.

## Version 1.66
- `clip.all_buttons` erstellt den Proxy nicht mehr automatisch neu.
  Der Ablauf aus Detect, Track, Tracking Length und Playhead to Frame
  bleibt unverändert und kann weiterhin mit Esc beendet werden.

## Version 1.67
- `clip.all_buttons` führt wieder nur die Erkennungsschritte einmalig aus.
- Neuer Operator `clip.all_cycle` übernimmt den bisherigen Zyklus ohne
  Proxy-Bau und kann mit Esc beendet werden.

## Version 1.68
- Entfernt nahezu alle Konsolenausgaben. Beim Detect-Vorgang wird
  lediglich die angewandte Threshold-Formel ausgegeben.

## Version 1.69
- `clip.all_buttons` versucht Detect nun bis zu zwanzigmal, bevor der
  Vorgang abgebrochen wird.
- `clip.count_button` setzt den gespeicherten NM-Wert nicht mehr auf 0
  zurück.

## Version 1.70
- Die Buttons "All", "Track", "Tracking Length" und "Playhead to Frame"
  wurden aus dem Panel entfernt. Ihre Funktionen sind weiterhin über
  `clip.all_cycle` verfügbar.

## Version 1.72
- Der "Motion"-Button wechselt das Default Motion Model, das beim Anlegen
  neuer Marker verwendet wird.

## Version 1.73
- Gespeicherte Frames mit wenigen GOOD_-Markern werden in der Liste `NF`
  aufbewahrt. Tritt ein bereits bekannter Frame erneut auf,
  löst das Skript den Motion-Button aus, ansonsten wird das
  Motion Model auf `Loc` zurückgesetzt.

## Version 1.74
- Beim erneuten Auftreten eines bekannten Frames wird die Pattern Size
  um 10 % erhöht (maximal 100). Bei neuen Frames verringert sich die
  Pattern Size um 10 %.
- Die Anpassung der Pattern Size erfolgt kumulativ auf Basis des aktuellen Werts.

## Version 1.75
- Der "Motion"-Button setzt die Pattern Size auf 50 und stellt die
  Search Size auf das Doppelte ein.
- Ein neuer "Pattern+"-Button vergrößert die Pattern Size um 10 % und
  passt die Search Size entsprechend an.

## Version 1.76
- Die Buttons beeinflussen nun die Default Pattern und Search Size, die
  bei neu erstellten Markern verwendet werden.

## Version 1.77
- Beim automatischen Wechsel des Motion Models wird die Pattern Size erst
  nach allen Reset-Schritten angepasst. Das direkte Betätigen des
  Motion-Buttons setzt sie weiterhin auf 50.

## Version 1.78
- Erreicht die Pattern Size den Maximalwert von 100, wächst der Wert aus
  "Marker / Frame" um 10 %, maximal auf das Doppelte des Startwerts.
- Fällt die Pattern Size wieder unter 100, schrumpft "Marker / Frame" in
  10-%-Schritten zurück auf den Ausgangswert.

## Version 1.81
- Die Pattern Size richtet sich nach der Breite des Clips. Der Basiswert
  betr\u00e4gt ein Hundertstel der Aufl\u00f6sung. Daraus ergibt sich ein Minimum
  von einem Drittel und ein Maximum vom Dreifachen dieses Wertes.

## Version 1.82
- Verringert sich die Anzahl neu erzeugter Marker zwischen zwei Detect-
  Vorg\u00e4ngen nicht, reduziert sich die Pattern Size jeweils um 10 %.
  Diese Anpassung summiert sich \u00fcber Durchg\u00e4nge hinweg und
  bleibt innerhalb der vom Clip abh\u00e4ngigen Grenzen.

## Version 1.83
- Die Pattern Size wird erst reduziert, wenn
  wiederholt dieselbe Anzahl Marker entsteht und
  der berechnete Threshold seinen Minimalwert erreicht hat.

## Version 1.84
- Zwei neue Buttons aktivieren default_use_brute (Prepass)
  und default_use_normalization (Normalize) in den
  Track-Einstellungen f\u00fcr neue Tracks.

## Version 1.85
- Die Buttons setzen nun die Eigenschaften
  `use_default_brute` und `use_default_normalization`.

