from .delete import delete_marker


def control_cycle(context, nm_list, values, restart_callback):
    """Kontrolllogik für Anzahl der Marker.

    Rückgabe: True falls Restart initiiert, False falls abgeschlossen.
    """
    am = len(nm_list)
    ug = values['ug']
    og = values['og']
    za = values['za']
    print(f'[Kaiserlich][control] am={am} (ug={ug:.2f} og={og:.2f}) tr={values["tr"]:.3f} pz={values["pz"]:.2f} md={values["md"]:.2f}')

    # Fertig?
    if ug <= am <= og:
        print('[Kaiserlich][control] Cycle finished (Toleranz erfüllt)')
        return False

    # Zu wenige Marker
    if am < ug:
        values['tr'] *= 0.5
        if values['tr'] < 0.1:
            print('[Kaiserlich][control] Cycle finished (threshold zu niedrig)')
            return False
        # Größeres Pattern probieren
        values['pz'] *= 1.1
        values['sz'] = values['pz'] * 2
        print(f'[Kaiserlich][control] Retry: tr={values["tr"]:.3f} pz={values["pz"]:.2f}')
        restart_callback()
        return True

    # Zu viele Marker
    if am > og:
        md_adj = values['md'] / (za / am) if za > 0 else values['md'] * 1.2
        values['md'] = md_adj
        print(f'[Kaiserlich][control] Too many markers → md adjusted = {md_adj:.2f}. Lösche neue Marker und restart.')
        for marker in nm_list:
            delete_marker(marker)
        restart_callback()
        return True

    return False
