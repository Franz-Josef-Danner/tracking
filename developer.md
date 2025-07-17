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

## Version 1.6
- Neues Eingabefeld "Marker / Frame" oberhalb des Panels
- Neuer Button "Marker", der einen Timeline Marker am angegebenen Frame setzt.

## Version 1.7
- Neuer Operator `clip.clean_new_tracks` entfernt `NEW_`-Tracks, die im aktuellen
  Frame näher als die berechnete Pixel-Distanz zu `GOOD_`-Tracks liegen.

## Version 1.7.1
- `clip.clean_new_tracks` besitzt jetzt eine Option `detect`, um die Feature-
  Erkennung wahlweise zu überspringen.
- Fehler beim Löschen von Tracks werden abgefangen.
