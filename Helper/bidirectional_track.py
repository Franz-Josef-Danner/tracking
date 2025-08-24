import bpy
from mathutils import Vector

class BIDIR_OT_bidirectional_track(bpy.types.Operator):
    """Bi-direktionales Marker-Tracking im Movie Clip Editor:
    Gruppiert je drei Marker, trackt vorwärts, korrigiert Positionen und wiederholt."""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track Markers"
    bl_options = {'REGISTER'}
    
    _timer = None
    groups = []
    
    def invoke(self, context, event):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Movie Clip aktiviert")
            return {'CANCELLED'}
        # Alle selektierten Tracks sammeln
        tracks = [t for t in clip.tracking.tracks if t.select]
        if not tracks:
            self.report({'WARNING'}, "Keine Marker ausgewählt")
            return {'CANCELLED'}
        if len(tracks) % 3 != 0:
            self.report({'WARNING'}, "Markeranzahl ist kein Vielfaches von 3")
            return {'CANCELLED'}
        frame = context.space_data.clip_user.frame_current
        
        # Gruppiere zu Dreiern (greedy nach minimaler Distanz)
        pts = []
        for t in tracks:
            m = t.markers.find_frame(frame)
            if m and not m.mute:
                pts.append((t, Vector(m.co)))
        groups = []
        while pts:
            best = None; best_sum = None
            n = len(pts)
            # Kombination aller Dreier durchgehen
            for i in range(n):
                for j in range(i+1, n):
                    for k in range(j+1, n):
                        (t1, p1) = pts[i]; (t2, p2) = pts[j]; (t3, p3) = pts[k]
                        d12 = (p1 - p2).length
                        d13 = (p1 - p3).length
                        d23 = (p2 - p3).length
                        s = d12 + d13 + d23
                        if best_sum is None or s < best_sum:
                            best_sum = s
                            best = (i, j, k)
            if not best:
                break
            i, j, k = best
            groups.append((pts[i][0], pts[j][0], pts[k][0]))
            for idx in sorted([i,j,k], reverse=True):
                pts.pop(idx)
        self.groups = groups
        
        # Modal-Timer starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        # ESC: Abbruch
        if event.type == 'ESC':
            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            scene = context.scene
            clip = context.space_data.clip
            if not clip:
                context.window_manager.event_timer_remove(self._timer)
                return {'CANCELLED'}
            current = context.space_data.clip_user.frame_current
            # Ende prüfen
            if current >= scene.frame_end:
                scene['_BIDI_RESULT_KEY'] = 'OK'
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            
            # Kontext-Override für Clip-Editor setzen
            override = context.copy()
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    override['area'] = area
                    for reg in area.regions:
                        if reg.type == 'WINDOW':
                            override['region'] = reg
                            break
                    for sp in area.spaces:
                        if sp.type == 'CLIP_EDITOR':
                            override['space_data'] = sp
                            break
                    break
            override['window'] = context.window
            override['screen'] = context.screen
            
            # Tracke Marker 1 Frame vorwärts
            bpy.ops.clip.track_markers(override, backwards=False, sequence=False)
            
            next_frame = current + 1
            # Korrigiere Marker jeder Gruppe
            for (t1, t2, t3) in self.groups:
                m1 = t1.markers.find_frame(next_frame)
                m2 = t2.markers.find_frame(next_frame)
                m3 = t3.markers.find_frame(next_frame)
                if not m1 or not m2 or not m3:
                    continue
                p1 = Vector(m1.co); p2 = Vector(m2.co); p3 = Vector(m3.co)
                d12 = (p1 - p2).length; d13 = (p1 - p3).length; d23 = (p2 - p3).length
                if d12 <= d13 and d12 <= d23:
                    mid = (p1 + p2) / 2.0
                    m3.co = mid
                elif d13 <= d12 and d13 <= d23:
                    mid = (p1 + p3) / 2.0
                    m2.co = mid
                else:
                    mid = (p2 + p3) / 2.0
                    m1.co = mid
            # Gruppe wieder selektieren
            for (t1, t2, t3) in self.groups:
                for t in (t1, t2, t3):
                    t.select = True
                    t.select_anchor = True
                    t.select_pattern = True
            # Vorwärts im Clip-Editor springen
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.spaces.active.clip_user.frame_current = next_frame
                    break
        
        return {'RUNNING_MODAL'}

def register():
    bpy.utils.register_class(BIDIR_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(BIDIR_OT_bidirectional_track)
