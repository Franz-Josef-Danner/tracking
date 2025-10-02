from .delete import delete_marker


def _clamp_md(md):
    # Begrenze md um Überlauf/Unsinn zu verhindern
    return max(2, min(int(md), 2048))


def control_cycle(context, nm_list, values):
    """Kontrolllogik für Anzahl der Marker.

    Rückgabe: String Aktion:
      'done'   -> Fertig
      'retry'  -> Parameter geändert, erneuter Detect nötig
      'repeat' -> Parameter geändert, neu erkannte Marker wurden gelöscht und Detect nötig
    """
    # Nur aktive Marker zählen
    active_nm = [m for m in nm_list if not getattr(m, 'mute', False)]
    am = len(active_nm)
    ug = values['ug']
    og = values['og']
    za = values['za']
    print(f'[Kaiserlich][control] am={am} (ug={ug:.2f} og={og:.2f}) tr={values["tr"]:.3f} pz={values["pz"]:.2f} md={values["md"]:.2f}')

    # Fertig?
    if ug <= am <= og:
        print('[Kaiserlich][control] Cycle finished (Toleranz erfüllt)')
        return 'done'

    # Zu wenige Marker
    if am < ug:
        values['tr'] *= 0.5
        if values['tr'] < 0.1:
            print('[Kaiserlich][control] Cycle finished (threshold zu niedrig)')
            return 'done'
        # Größeres Pattern probieren
        values['pz'] *= 1.1
        values['sz'] = values['pz'] * 2
        print(f'[Kaiserlich][control] Retry: tr={values["tr"]:.3f} pz={values["pz"]:.2f}')
        return 'retry'

    # Zu viele Marker
    if am > og:
        # Verhältnis: wir wollen ungefähr za Marker -> skaliere md proportional
        if am > 0:
            scale = am / za if za > 0 else 1.5
            md_adj = values['md'] * scale
        else:
            md_adj = values['md'] * 1.5
        values['md'] = _clamp_md(md_adj)
        print(f'[Kaiserlich][control] Too many markers → md adjusted = {values["md"]}. Lösche neue Marker und restart.')
        for marker in active_nm:
            delete_marker(marker)
        return 'repeat'

    return 'done'
