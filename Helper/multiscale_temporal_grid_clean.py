# am Ende von multiscale_temporal_grid_clean(...):

def _micro_outlier_pass(area, region, space, tracks, frame_range, width, height, ee, grid):
    gx, gy = grid
    frame_start, frame_end = frame_range
    deleted = 0
    with bpy.context.temp_override(area=area, region=region, space_data=space):
        # wie bisher: 3-Frame-Beschleunigungscheck pro Zelle
        cell_w, cell_h = width/gx, height/gy
        for fi in range(frame_start+1, frame_end-1):
            # Marker in Zellen sammeln
            buckets = {}
            for tr in tracks:
                m1 = tr.markers.find_frame(fi-1)
                m2 = tr.markers.find_frame(fi)
                m3 = tr.markers.find_frame(fi+1)
                if not (m1 and m2 and m3): 
                    continue
                x, y = m2.co[0]*width, m2.co[1]*height
                cx = min(gx-1, max(0, int(x//cell_w)))
                cy = min(gy-1, max(0, int(y//cell_h)))
                vx = (m2.co[0]-m1.co[0]) + (m3.co[0]-m2.co[0])
                vy = (m2.co[1]-m1.co[1]) + (m3.co[1]-m2.co[1])
                buckets.setdefault((cx,cy), []).append((tr, fi, vx, vy))
            # Zellweise Mittelwert & Deletion
            for _, items in buckets.items():
                vxa = sum(vx for _,_,vx,_ in items)/len(items)
                vya = sum(vy for _,_,_,vy in items)/len(items)
                va = 0.5*(vxa+vya)
                for tr, f, vx, vy in items:
                    vm = 0.5*(vx+vy)
                    if abs(vm - va) >= ee:
                        for ff in (f-1, f, f+1):
                            if tr.markers.find_frame(ff):
                                tr.markers.delete_frame(ff)
                                deleted += 1
        region.tag_redraw()
    return deleted

# ...innerhalb multiscale_temporal_grid_clean(...) nach Phasen A/B:
ee_base = max((getattr(context.scene, "error_track", 1.0) + 0.1)/100.0, 1e-6)
deleted_micro = _micro_outlier_pass(area, region, space, tracks, frame_range, width, height, ee_base, grid)
return deleted_coarse + deleted_micro  # summiert
