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
- `clip.proxy.use_custom_directory` ersetzt durch `clip.proxy.use_proxy_custom_directory` (API-Anpassung ab Blender 4.4).

## Version 1.5
- Vor dem Proxy-Bau wird das Proxy-Verzeichnis (falls vorhanden) gel\u00f6scht, bevor neue Proxys erstellt werden.
