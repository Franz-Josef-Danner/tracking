def create_proxy_and_wait(wait_time=300.0):
    print("Starte Proxy-Erstellung (50 %, custom Pfad)")
    sys.stdout.flush()

    clip = bpy.context.space_data.clip
    if not clip:
        print("Kein aktiver Clip.")
        return

    clip_path = bpy.path.abspath(clip.filepath)
    if not os.path.isfile(clip_path):
        print("Clip-Datei existiert nicht.")
        return

    clip.use_proxy = True
    clip.use_proxy_timecode = True
    clip.proxy.timecode = 'RECORD_RUN_NO_GAPS'
    clip.proxy.build_25 = False
    clip.proxy.build_50 = True
    clip.proxy.build_75 = False
    clip.proxy.build_100 = False
    clip.proxy.quality = 50
    clip.use_proxy_custom_directory = True

    proxy_dir = "//BL_proxy/"
    clip.proxy.directory = proxy_dir
    full_proxy = bpy.path.abspath(proxy_dir)
    os.makedirs(full_proxy, exist_ok=True)
    print(f"Proxy wird im Ordner {full_proxy} erstellt")
    sys.stdout.flush()

    # Proxy-Operator im richtigen Kontext aufrufen
    try:
        area = next(area for area in bpy.context.window.screen.areas if area.type == 'CLIP_EDITOR')
        override = bpy.context.copy()
        override['area'] = area
        bpy.ops.clip.rebuild_proxy(override, 'EXEC_DEFAULT')
    except StopIteration:
        print("❌ Kein CLIP_EDITOR-Bereich gefunden.")
        return

    print("⏳ Warte bis Proxy intern verfügbar ist (max. 300s)...")
    sys.stdout.flush()

    # Warten auf interne Verfügbarkeit oder Dateisystem
    proxy_filename = "proxy_50.avi"
    direct_path = os.path.join(full_proxy, proxy_filename)
    alt_folder = os.path.join(full_proxy, os.path.basename(clip.filepath))
    alt_path = os.path.join(alt_folder, proxy_filename)

    start_time = time.time()
    while (time.time() - start_time) < wait_time:
        clip.reload()

        # Überprüfe, ob der Proxy intern registriert ist
        proxy_ready = clip.proxy.build_50 is False and clip.proxy.build_25 is False
        file_ready = os.path.exists(direct_path) or os.path.exists(alt_path)

        if proxy_ready and file_ready:
            print("✅ Proxy fertig und sichtbar in Blender.")
            sys.stdout.flush()
            return

        time.sleep(1)

    print("⏱️ Zeitüberschreitung: Proxy-Dateien nicht verfügbar oder nicht registriert.")
    sys.stdout.flush()
