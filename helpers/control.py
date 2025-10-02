from .delete import delete_marker


def _clamp_md(md):
    return max(2, min(int(md), 2048))


def control_cycle(context, total_active, new_active, values):
    """Kontrolllogik für Gesamtzahl der aktiven Marker.

    total_active: Liste aller aktiven Marker am Frame (kumuliert)
    new_active:   Liste neu hinzugekommener aktiver Marker dieser Iteration

    Rückgabe Aktionen:
      'done'   -> Fertig
      'retry'  -> Parameter anpassen & erneut erkennen (zu wenige)
      'repeat' -> Zu viele: neue Marker löschen, md angepasst, erneut erkennen
    """
    am = len(total_active)
    ug = values['ug']
    og = values['og']
    za = values['za']
    print(f'[Kaiserlich][control] am_total={am} (ug={ug:.2f} og={og:.2f}) new={len(new_active)} tr={values["tr"]:.3f} pz={values["pz"]:.2f} md={values["md"]:.2f}')

    if ug <= am <= og:
        print('[Kaiserlich][control] Cycle finished (Toleranz erfüllt)')
        return 'done'

    if am < ug:
        values['tr'] *= 0.5
        if values['tr'] < 0.1:
            print('[Kaiserlich][control] Cycle finished (threshold zu niedrig)')
            return 'done'
        values['pz'] *= 1.1
        values['sz'] = values['pz'] * 2
        print(f'[Kaiserlich][control] Retry: tr={values["tr"]:.3f} pz={values["pz"]:.2f}')
        return 'retry'

    if am > og:
        if am > 0:
            scale = am / za if za > 0 else 1.5
            md_adj = values['md'] * scale
        else:
            md_adj = values['md'] * 1.5
        values['md'] = _clamp_md(md_adj)
        print(f'[Kaiserlich][control] Too many markers → md adjusted = {values["md"]}. Lösche neue Marker (nur aktuelle) und restart.')
        for marker in new_active:  # nur neue dieser Runde löschen
            delete_marker(marker)
        return 'repeat'

    return 'done'
