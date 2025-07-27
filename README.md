# Simple Blender Addon

Dieses Verzeichnis enthaelt ein minimales Blender Addon für Blender 4.4 oder neuer. Kopiere den Ordner `t` in deinen Blender Addons-Ordner und aktiviere das Addon in den Einstellungen.

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
Seit Version 1.69 erhöht sich diese Grenze auf zwanzig Durchläufe.
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
Seit Version 1.49 gibt der Track-Button nach jedem Tracking-Schritt die Anzahl
der aktiven Marker aus.
Seit Version 1.50 arbeitet der Track-Button in 25er-Schritten und pr\u00FCft nach
jeder Passage von 25 Frames erneut die verbleibenden TRACK_-Marker.
Seit Version 1.51 passt der Track-Button die Blockgr\xF6\xDFe dynamisch an und
verteilt den verbleibenden Bereich auf vier Abschnitte.
Seit Version 1.52 gibt es experimentelle "Live Track"-Operatoren, die per
Timer laufendes Tracking \xFCberwachen und stoppen, sobald keine TRACK_-Marker
mehr aktiv sind.
Seit Version 1.53 f\u00fchrt der neue "Proxy Track"-Button automatisch den Proxy-Befehl aus,
speichert den aktuellen Frame und verfolgt TRACK_-Marker zehn Frames r\u00fcckw\u00e4rts
und anschlie\xDFend wieder vorw\u00e4rts.
Seit Version 1.54 deaktiviert der "Proxy Track"-Button zun\u00e4chst den Proxy,
speichert den aktuellen Frame, w\u00e4hlt alle TRACK_-Marker aus und verfolgt sie
zehn Frames r\u00fcckw\u00e4rts. Danach setzt er den Playhead zur\u00fcck und trackt
vorw\u00e4rts.
Seit Version 1.55 verwendet der "Proxy Track"-Button beim Rückwärts-Tracking denselben dynamischen Block-Algorithmus wie der Track-Button. Die Marker werden in Abschnitten eines Viertels des verbleibenden Bereichs verfolgt, bis keine aktiven TRACK_-Marker mehr übrig sind. Danach wird der gespeicherte Frame wiederhergestellt und ohne Unterteilung vorwärts getrackt.
Seit Version 1.56 aktiviert der "Proxy Track"-Button den Proxy, bevor er das Tracking startet.
Seit Version 1.57 wurden die Buttons "Proxy Track", "Live Fwd" und "Live Back" entfernt.
Seit Version 1.58 gibt es ein neues Eingabefeld "Frames/Track" direkt unter "Marker / Frame".
Seit Version 1.59 bietet das Panel einen Button "Tracking Length", der alle TRACK_-Marker löscht,
deren Länge unter dem Wert aus "Frames/Track" liegt.
Seit Version 1.60 legt der Track-Button die Blockgröße beim Rückwärts-Tracking einmalig auf die Hälfte des verbleibenden Bereichs fest.
Seit Version 1.61 gibt der "Tracking Length"-Button den verwendeten Frames/Track-Wert in der Konsole aus.
Seit Version 1.62 verwendet der Track-Button beim Rückwärts-Tracking eine Blockgröße nach der Formel `GF / log10(GF*GF)`.
Seit Version 1.63 löscht der "Tracking Length"-Button die kurzen TRACK_-Marker,
selektiert danach alle verbleibenden TRACK_-Marker und benennt sie in GOOD_ um.
Seit Version 1.64 gibt es einen Button "Playhead to Frame", der den Playhead
zum ersten Frame springt, in dem weniger GOOD_-Marker aktiv sind als im Feld
"Marker / Frame" angegeben.
Seit Version 1.67 gibt es einen neuen Button "All Cycle", der Detect,
Track, Tracking Length und Playhead to Frame in einem Zyklus ausführt.
Der Proxy wird dabei nicht automatisch neu erstellt und der Ablauf kann
mit Esc beendet werden. Der "All"-Button führt wieder nur die einzelnen
Erkennungsschritte einmalig aus.
Seit Version 1.68 werden alle Konsolenausgaben bis auf die ausgegebene
Threshold-Formel entfernt.
Seit Version 1.69 wird der NM-Wert nach dem Umbenennen der NEW_-Tracks
nicht mehr auf 0 gesetzt. Der "All"-Button versucht Detect nun bis zu
zwanzig Mal.
Seit Version 1.70 wurden die Buttons "All", "Track", "Tracking Length" und
"Playhead to Frame" aus dem Panel entfernt. Die kombinierte Funktionalität
ist weiterhin über den Button "All Cycle" erreichbar.
Seit Version 1.72 bietet das Panel zusätzlich einen Button "Motion", der
das Default Motion Model für neue Marker zyklisch durchschaltet.
Seit Version 1.73 merkt sich das Skript jeden gefundenen Frame mit zu wenig
GOOD_-Markern. Wird erneut derselbe Frame gefunden, wechselt das Motion
Model, andernfalls wird es auf den Standard "Loc" zurückgesetzt.
Seit Version 1.74 wird die Pattern Size bei bekannten Frames um 10 %
erhöht und bei neuen Frames um 10 % reduziert. Der Wert überschreitet
nie 100.
Die Anpassung erfolgt kumulativ, also basierend auf dem jeweils aktuellen Wert.
Seit Version 1.75 setzt der "Motion"-Button die Pattern Size auf 50 und
passt die Search Size entsprechend an. Ein weiterer Button "Pattern+"
erhöht die Pattern Size um 10 % und verdoppelt die Search Size.
Seit Version 1.76 wirken sich diese Änderungen auf die Default Pattern
und Search Size aus, die für neue Marker gelten.
Seit Version 1.77 setzt das Skript die Pattern Size nur noch einmal
nach allen zurücksetzenden Schritten. Der Motion-Button selbst kann die
Größe weiterhin auf 50 zurücksetzen.
Seit Version 1.78 wird "Marker / Frame" um 10 % erhöht, wenn die
Pattern Size 100 erreicht. Sinkt die Pattern Size wieder unter 100,
verringert sich der Wert schrittweise zurück bis zum Ausgangswert.
Seit Version 1.81 richtet sich die Pattern Size nach der horizontalen
Aufl\u00f6sung des Clips. Der Basiswert betr\u00e4gt ein Hundertstel der Breite.
Die Pattern Size kann h\u00f6chstens das Dreifache und mindestens ein Drittel
dieses Basiswerts betragen.
Seit Version 1.82 verringert sich die Pattern Size um 10 %,
wenn bei aufeinanderfolgenden Detect-Durchg\u00e4ngen dieselbe Anzahl
neuer Marker entsteht. Diese Anpassung erfolgt kumulativ und bleibt
innerhalb der dynamischen Mindest- und Maximalgrenzen.
Seit Version 1.83 wird die Pattern Size erst reduziert,
wenn bei wiederholten Detect-Durchgängen dieselbe Anzahl
neuer Marker entsteht und der Threshold seinen Minimalwert
erreicht hat.
Seit Version 1.84 bietet das Panel zwei Buttons,
die Prepass und Normalize in den Standardeinstellungen
für neue Tracks aktivieren.
Seit Version 1.85 setzen diese Buttons die Eigenschaften
`use_default_brute` und `use_default_normalization`
in den Tracking-Einstellungen.
Seit Version 1.86 aktiviert der "All Cycle"-Button
nach dem Proxy-Wechsel automatisch Prepass und Normalize.
Seit Version 1.87 wurden die Buttons Motion, Pattern+, Prepass und Normalize aus dem Panel entfernt. Prepass und Normalize werden beim All Cycle weiterhin automatisch aktiviert.
Seit Version 1.88 gibt es einen "Defaults"-Button unter dem Proxy. Er setzt die Pattern Size auf 10, passt die Search Size an, stellt das Motion Model auf "Loc", verwendet Keyframe-Matching und aktiviert Prepass, Normalize sowie alle Farbkanäle.
Seit Version 1.89 stellt der Button zusätzlich die Tracking-Defaults
`default_correlation_min` auf 0.85 und `default_margin` auf 10 Pixel ein.
Beim Ausführen wird außerdem eine Meldung mit den gesetzten Werten, einschließlich Mindestkorrelation und Margin, in der Konsole ausgegeben.
Seit Version 1.90 löst der Button nach dem Setzen der Werte automatisch
`clip.detect_features()` aus.
Seit Version 1.91 wiederholt der Detect-Button die Feature-Erkennung,
bis die Anzahl neuer Marker zwischen 90 % und 110 % von (Marker / Frame) / 3 liegt.
Ansonsten passt er Threshold, Margin und Distance an und startet die Erkennung erneut.
Seit Version 1.93 befinden sich unter "Defaults" weitere Buttons zum Detekten, Zählen, Tracken, Löschen, Anpassen der Pattern Size,
zum Wechseln des Motion Models und des Pattern Match sowie zum Ein- und Ausschalten der Farbkanäle.
Seit Version 1.94 wurde der Button "Defaults + Test" entfernt. Neu ist "Name Test", der TEST_-Präfixe setzt. Pattern+ und Pattern- haben keine Größenbegrenzung mehr und Detect löscht Marker wie der Delete-Button.
Seit Version 1.95 berechnet der Detect-Button den Threshold mit einem Drittel von "Marker / Frame" (mf_base) statt des NM-Werts.
Seit Version 1.96 f\u00fchrt der Button "Auto Detect" zun\u00e4chst die Defaults einmal aus und wiederholt dann Detect und Count. Liegt die Markeranzahl nicht zwischen 90 % und 110 % von (Marker / Frame) / 3, werden die Marker gel\u00f6scht und die Erkennung startet erneut.
Seit Version 1.97 vergibt der Detect-Button nach jeder Feature-Erkennung automatisch das TEST_-Präfix an neu entstandene Marker.
Seit Version 1.98 passt der Detect-Button den Threshold mit der Formel
`aktueller * ((letzte Markeranzahl + 0.1) / (Marker / Frame / 3))` an.
Seit Version 1.99 w\u00e4hlt der "Auto Detect"-Button alle TEST_-Tracks aus,
startet das Tracking und aktualisiert den gespeicherten Test-Frame samt
Einstellungen, wenn das Ergebnis besser ist.
Der Startframe wird dabei in `TEST_START_FRAME` gesichert, der Endframe in
`TEST_END_FRAME`. Die verwendeten Einstellungen (Pattern Size, Motion Model,
Pattern Match und aktive RGB-Kanäle) landen in `TEST_SETTINGS`.
Seit Version 1.100 gibt "Auto Detect" den Start, jeden Durchlauf und das
Tracking in der Konsole aus.
Seit Version 1.101 gibt "Auto Detect" am Ende die Anzahl der getrackten Frames
sowie Pattern Size, Motion Model, Pattern Match und die aktiven RGB-Kanäle in
der Konsole aus.
Seit Version 1.102 werden die TEST_-Tracks nach dem Tracking nicht mehr in
TRACK_ umbenannt. Stattdessen wählt "Auto Detect" alle TEST_-Tracks aus,
löst den Delete-Operator aus und führt anschließend Pattern+ aus.
Seit Version 1.103 wiederholt "Auto Detect" Detect, Track, Delete und Pattern+
so lange, bis der neu getrackte Endframe kleiner ist als der zuvor gespeicherte
Endframe.
Seit Version 1.105 sucht "Auto Detect" jeweils viermal nach einem hoeheren Endframe. Wird kein besseres Ergebnis erzielt, endet der Vorgang.
Seit Version 1.106 sucht "Auto Detect" nun sechsmal in einem Block nach einem hoeheren Endframe und bricht ab, wenn keine Verbesserung erreicht wird.
Seit Version 1.107 sucht "Auto Detect" nur noch in Zweierblöcken nach einem höheren Endframe und speichert das Ergebnis nur, wenn es besser ist. Der Zyklus endet, sobald der nächste Track früher stoppt als der bereits gespeicherte Endframe.
Seit Version 1.108 sucht "Auto Detect" wieder in Viererblöcken nach einem höheren Endframe. Der Vorgang endet, wenn der nächste Track früher stoppt als der gespeicherte Endframe.
Seit Version 1.109 gibt "Auto Detect" am Ende den gespeicherten Endframe und dessen Einstellungen in der Konsole aus.
Seit Version 1.110 testet ein neuer Button "Auto Detect CH" verschiedene RGB-Kombinationen, speichert das beste Ergebnis und gibt Pattern Size, Motion Model sowie die Farbkanäle in der Konsole aus.
Seit Version 1.111 setzt ein neuer Button "Apply Detect" unter "Auto Detect CH" die gespeicherten Werte für Pattern Size, Motion Model und die aktiven RGB-Kanäle. Zusätzlich stellt er die Mindestkorrelation auf 0,9 und den Margin-Wert auf das Doppelte der Pattern Size ein.
Seit Version 1.112 ruft "Auto Detect" zu Beginn nicht mehr "Defaults" auf, sondern verwendet die aktuellen Tracking-Einstellungen.
Seit Version 1.113 gibt es einen Button 'Detect', der den Detect-Schritt aus 'All Cycle' separat ausführt.
Seit Version 1.114 befindet sich der Button im API-Panel und verwendet eine eigene Threshold-Formel.
Seit Version 1.115 gibt dieser Button zus\u00e4tzliche Konsolenausgaben zum Threshold und der Anzahl neuer Marker aus.
Seit Version 1.116 berechnet der Button Margin und Min Distance logarithmisch aus dem Threshold.
Seit Version 1.117 findet im Detect-Button keine automatische Umbenennung der Marker mehr statt.
Seit Version 1.118 bleiben neu erkannte Marker nach dem Detect-Button ausgewählt.
Seit Version 1.119 bietet das API-Panel einen Button "Name New", der selektierte Tracks mit dem Präfix NEW_ versieht.
Seit Version 1.120 bietet das API-Panel einen Button "Name Track", der selektierte Tracks mit dem Präfix TRACK_ versieht.
Seit Version 1.121 entfernt dieser Button vorhandene Präfixe, bevor er TRACK_ einfügt.
Seit Version 1.122 wurde der Button "All Cycle" aus dem Panel entfernt.
Seit Version 1.123 gibt es einen Button 'Track Partial', der ausgew\u00e4hlte Marker blockweise r\u00fcckw\u00e4rts verfolgt und anschlie\u00dfend f\u00fcr eine begrenzte Anzahl von Frames vorw\u00e4rts trackt.
Seit Version 1.125 bietet das API-Panel einen Button "Select TRACK", der alle aktiven TRACK_-Marker im aktuellen Frame auswählt.
Seit Version 1.126 bricht der Button "Track Partial" ab, wenn der Playhead am Szenenanfang oder -ende steht.
Seit Version 1.127 überspringt der Button "Track Partial" das rückwärts Tracking am Szenenanfang und das vorwärts Tracking am Szenenende.
Seit Version 1.128 zeigt der Button "Track Partial" den Fortschritt der Tracking-Frames in der Konsole an.
Seit Version 1.129 verschiebt der Button "Track Partial" den Playhead einen Frame ins Innere, wenn dieser am Szenenanfang oder -ende steht.
Seit Version 1.130 protokolliert "Track Partial" Markeranzahl und Tracking-Bereich in der Konsole und listet neu erkannte Marker mit Position auf.
Seit Version 1.131 befindet sich unter dem Proxy ein Button "Track Nr. 1", der den Detect-Button auslöst.
Seit Version 1.132 gibt es im API-Panel einen Button "Frame jump", der den Playhead um "Frames/Track" nach vorne bewegt.
Seit Version 1.133 löst der Button "Track Nr. 1" nach dem Detect-Schritt zusätzlich "Select TRACK" aus.
Seit Version 1.134 löst der Button "Track Nr. 1" im Anschluss "Track Partial" aus.
Seit Version 1.135 löst der Button "Track Nr. 1" am Ende "Frame Jump" aus.
Seit Version 1.136 bietet das API-Panel einen Button "Defaults", der Pattern Size 50, Search Size 100, Motion Model "Loc", Keyframe-Matching, Prepass, Normalize, alle RGB-Kanäle, Gewicht 1, Mindestkorrelation 0.9 und Margin 100 einstellt.
Seit Version 1.137 gibt es im API-Panel die Buttons "Proxy on" und "Proxy off", die das Proxy aktivieren bzw. deaktivieren.
Seit Version 1.138 schaltet der Button "Track Nr. 1" zunächst das Proxy aus und aktiviert es erneut direkt vor "Track Partial".
Seit Version 1.139 wiederholt der Button "Track Nr. 1" den gesamten Ablauf, bis der Szenenendframe erreicht ist.
Seit Version 1.140 setzen die Buttons "Track Nr. 1" und "Step Track" nach dem "Track Partial" erneut Marker, um l\u00fcckenlose TRACK_-Marker zu erhalten.
Seit Version 1.141 bietet das API-Panel einen Button "Short Track", der TRACK_-Marker ausw\u00e4hlt, deren L\u00e4nge unter dem Wert aus "Frames/Track" liegt.
Seit Version 1.142 l\u00f6st der Button "Track Nr. 1" am Szenenende automatisch "Short Track" und danach "Delete" aus.
Seit Version 1.143 bietet das API-Panel einen Button "Name GOOD", der alle TRACK_-Marker in GOOD_-Marker umbenennt.
Seit Version 1.144 führt der Button "Track Nr. 1" nach dem Tracking keine automatische Feature-Erkennung mehr aus.
Seit Version 1.145 l\u00f6st der Button "Track Nr. 1" am Ende automatisch "Name GOOD" aus.
Seit Version 1.146 bietet das API-Panel einen Button "Low Marker Frame", der zum ersten Frame springt, in dem weniger Marker aktiv sind als im Feld "Marker / Frame" angegeben.
Seit Version 1.147 ruft der Button "Track Nr. 1" zu Beginn automatisch "Defaults" auf.
Seit Version 1.148 besitzt das API-Panel die Buttons "Marker Position" und "GOOD Marker Position". Sie geben die Pixelkoordinaten der Marker in ausgewählten Tracks beziehungsweise aller GOOD_-Marker im aktuellen Frame aus.
Seit Version 1.149 gibt der Button "Marker Position" die Pixelkoordinaten aller Marker in den selektierten Tracks aus.
Seit Version 1.150 bietet das API-Panel einen Button "Kamera solve", der den Camera Solver ausführt.
Seit Version 1.151 enthält das Final-Panel ein Eingabefeld "Error Threshold" mit dem Standardwert 2.
Seit Version 1.152 besitzt das API-Panel einen Button "Track Cleanup", der GOOD_-Tracks anhand ihrer Positionen löscht.
Seit Version 1.153 verfügt das Stufen-Panel über einen Button "Cleanup", der
"Short Track" und danach "Track Cleanup" ausführt.
Seit Version 1.154 unterteilt "Track Cleanup" das Bild in Viertel und Achtel
und verwendet dabei halbierte bzw. geviertelte Error-Threshold-Werte.
Seit Version 1.155 springt der "Cleanup"-Button nach jedem Durchlauf einen Frame
vor, wiederholt den Vorgang bis zum vorletzten Szenenframe und meldet jeden
Schritt in der Konsole.
Seit Version 1.156 führt der Button "Track Nr. 1" am Szenenende keinen "Short Track" mehr aus.
Seit Version 1.157 löscht oder benennt der Button "Track Nr. 1" am Ende keine Tracks mehr um.
Seit Version 1.158 wendet "Track Cleanup" seinen Löschvorgang auf TRACK_-Marker an.
Seit Version 1.159 löscht der Button "Short Track" die ausgewählten TRACK_-Marker sofort.
Seit Version 1.160 ist "Short Track" modular aufgebaut: Ein neuer Button "Select Short" wählt kurze TRACK_-Marker aus, der Button "Short Track" löscht sie anschließend.
Seit Version 1.161 entfällt der Button "Select Short" wieder. "Track Cleanup" heißt nun "Track Error Selekt" und markiert fehlerhafte TRACK_-Marker, ohne sie zu löschen.
Seit Version 1.162 kehrt der Button als "Select Short Tracks" zurück, während "Short Track" entfernt wurde. "Track Error Selekt" heißt jetzt "Select Error Tracks".
Seit Version 1.163 ruft der "Cleanup"-Button nacheinander "Select Short Tracks", "Select Error Tracks" und "Delete" auf.
Seit Version 1.164 verfolgt der Button "Track Partial" ausgewählte Marker rückwärts bis zum Szenenanfang und anschließend vorwärts bis zum Szenenende. Der Vorgang wird beendet, wenn beim Vorwärtstracking weniger Frames erreicht werden als im Feld "Frames/Track" angegeben.
Seit Version 1.165 führt "Cycle Detect" wiederholte Feature-Erkennungen ohne Proxy aus, entfernt Marker in der Nähe von GOOD_- und TRACK_-Spuren und vergibt danach das Präfix NEW_. "Track Partial" trackt nun einfach in beide Richtungen bis zum Anschlag. "Track Nr. 1" kombiniert Defaults, Cycle Detect und Track Partial in einem Zyklus und verschiebt den Playhead, bis das Szenenende erreicht ist. Abschließend erhalten alle Marker das TRACK_-Präfix.
Seit Version 1.166 gibt "Track Nr. 1" Start- und Endframe in der Konsole aus und beendet den Zyklus, wenn beim Vorwärtstracking weniger Frames als in "Frames/Track" erreicht werden.
Seit Version 1.167 springt der Playhead nach jedem Durchlauf um "Frames/Track" nach vorn, sofern dabei noch Fortschritt erzielt wird. Erst wenn weniger oder gar kein Fortschritt mehr erreicht wird, werden alle Marker abschließend mit TRACK_ umbenannt.
Seit Version 1.168 prüft "Cycle Detect" nun auch den Abstand zu vorhandenen NEW_-Markern, sodass neu erkannte Marker ebenfalls ausreichend Abstand zu ihnen einhalten müssen.
Seit Version 1.169 bietet das API-Panel einen Button "Select NEW", der alle Marker mit dem Präfix NEW_ auswählt.
Seit Version 1.170 wählt "Track Nr. 1" vor dem Umbenennen alle NEW_-Marker aus.
Seit Version 1.171 löscht der "Cleanup"-Button nach "Select Short Tracks" direkt die ausgewählten Marker.
Seit Version 1.172 ruft derselbe Button danach "Select Error Tracks" und erneut "Delete" auf.
Seit Version 1.173 setzt "Track Nr. 1" nach jedem Durchlauf den Playhead mit "Low Marker Frame" auf den nächsten Frame mit zu wenigen Markern. Der Zyklus endet, wenn kein solcher Frame mehr gefunden wird.
Seit Version 1.174 löscht "Track Nr. 1" nach jedem Durchlauf zunächst kurze TRACK_-Marker mit "Select Short Tracks" und "Delete" und springt danach mit "Low Marker Frame" zum nächsten Start.
Seit Version 1.175 wird dieser Ablauf modular ausgeführt, sodass die Bereinigung und der Sprung zum nächsten Start nacheinander erfolgen.
Seit Version 1.176 ruft der "Cleanup"-Button nur noch 'Select Error Tracks' und danach 'Delete' auf.
Seit Version 1.177 wiederholt derselbe Button 'Select Error Tracks' und 'Delete', wobei der Error Threshold auf 90% des jeweils größten Fehlers gesetzt wird, bis der Wert unter 10 fällt.
Seit Version 1.178 setzt der "Cleanup"-Button zunächst den größten gefundenen Fehler in
"Error Threshold" und löscht TRACK_-Marker iterativ. Dabei verringert er den Threshold
nach jedem Durchlauf auf 90 % des vorherigen Werts, bis der ursprüngliche
Schwellwert erreicht ist.
Seit Version 1.179 gibt der "Cleanup"-Button nach jedem Durchlauf nur noch die
Anzahl der gelöschten Marker und den jeweils verwendeten Error Threshold in der
Konsole aus.
Seit Version 1.180 benennt "Track Nr. 1" nach jedem "Cycle Detect" die Marker
mit "Name New" um. Findet "Low Marker Frame" keinen weiteren Frame, wird
zuerst "Select NEW" und anschließend "Name Track" ausgeführt.
Seit Version 1.181 besitzt das API-Unterpanel einen Button "TEST select", der alle Marker mit dem Präfix TEST_ auswählt.
Seit Version 1.182 gibt es dort zusätzlich einen Button "Test Detect", der Marker erkennt, bis ihre Anzahl im Zielbereich liegt.
Seit Version 1.183 besitzt dieses Unter-Panel auch einen Button "Test Track", der selektierte Marker bis zum Sequenzende vorwärts verfolgt.
Seit Version 1.184 werten die Testfunktionen zusätzlich den Fehler der Markerpositionen aus. Nach jedem der vier Tracking-Durchgänge wird der Error berechnet und aufsummiert. Bei der Pattern-Größe wird der Test beendet, sobald keine Fortschritte mehr erzielt werden oder der Fehlerwert um mehr als 15 % über dem bisherigen Minimum liegt. Motion Model und Farbkanäle wählen direkt die Kombination mit dem besten Verhältnis aus maximaler Frame-Anzahl und minimalem Error.
Seit Version 1.185 führt "Test Pattern" jeden Größenwert zweimal aus und verwendet das bessere Ergebnis, um Ausreißer durch Tracking-Fehler zu vermeiden.
Seit Version 1.186 schalten die Testfunktionen den Proxy vor der Feature-Erkennung aus und vor dem Tracking wieder ein, damit alle Schritte mit konsistenten Einstellungen ausgeführt werden.
Seit Version 1.187 erhöht sich die Abbruchschwelle für den Fehler beim Pattern-Test auf 20 %.
Seit Version 1.188 wird beim Pattern-Test nach einem Rückgang der Frame-Anzahl noch vier weitere Größenwerte getestet, bevor der Vorgang abgebrochen wird.
Seit Version 1.189 sind die Abläufe der Testfunktionen in modulare Schritte unterteilt, um die Wartbarkeit des Codes zu verbessern.
Seit Version 1.190 testet "Test Pattern" jede Größe nur noch einmal mit vier Durchgängen.
Seit Version 1.191 führt "Test Pattern" pro Größe nur noch drei Tracking-Durchgänge aus.
Seit Version 1.192 führt "Test Pattern" pro Größe nur noch einen Tracking-Durchgang aus.
Seit Version 1.193 verringert sich die Abbruchschwelle für den Fehler beim Pattern-Test auf 15 %.
Seit Version 1.194 f\u00fchrt der Button "Track Nr. 1" am Ende einmalig "Select Short Tracks" und anschlie\u00dfend "Delete" aus.
Seit Version 1.195 verf\u00fcgt das API-Panel \u00fcber einen Button "Marker/Frame+", der den Wert im Feld "Marker/Frame" um 10 % erh\u00f6ht.
Seit Version 1.196 gibt es zus\u00e4tzlich einen Button "Marker/Frame-", der diesen Wert um 10 % senkt. "Track Nr. 2" merkt sich nun f\u00fcr jeden Frame die Anzahl der Tracking-Versuche, erh\u00f6ht den Wert bei Wiederholungen und reduziert ihn bei neuen Frames. Nach zehn erfolglosen Versuchen bricht der Vorgang ab.
Seit Version 1.197 passt "Track Nr. 1" den Threshold dynamisch an, bis die Markeranzahl im Zielbereich liegt.

## License

Dieses Projekt steht unter der MIT-Lizenz. Siehe [LICENSE](LICENSE) für Details.
