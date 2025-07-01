import bpy 
from collections import Counter 

# Mindestanzahl Tracking-Marker pro Frame 
MINIMUM_MARKER_COUNT = 5

def get_tracking_marker_counts(): 
marker_counts = Counter() 
# Gehe durch jeden zugewiesenen Clip 
for clip in bpy.data.movieclips: 
for track in clip.tracking.tracks: 
# Prüfen, ob für diesen Frame ein Marker existiert und ""get_marker"" != None 
for marker in track.markers: 
frame = marker.frame 
if marker: # Implizit immer True, nur als Platzhalter 
marker_counts[frame] += 1 
# Debug-Ausgabe 
print(""Tracking-Marker pro Frame (rohe Zählung):"") 
for frame, count in marker_counts.items(): 
print(f"" Frame {frame}: {count}"") 
return marker_counts 

def find_frame_with_few_tracking_markers(marker_counts, minimum_count): 
start = bpy.context.scene.frame_start 
end = bpy.context.scene.frame_end 

print(""\nSuche Frame mit < %d Tracking-Markern..."" % minimum_count) 
for frame in range(start, end + 1): 
cnt = marker_counts.get(frame, 0) 
print(f"" Frame {frame}: {cnt} Tracker"") 
if cnt < minimum_count: 
print(f""--> Treffer: Frame {frame}"") 
return frame 
print(""Kein Frame gefunden!"") 
return None 

def set_playhead(frame): 
if frame is not None: 
bpy.context.scene.frame_current = frame 
print(f""\nPlayhead auf Frame {frame} gesetzt."") 
else: 
print(""\nKein passender Frame gefunden."") 

# Ablauf 
marker_counts = get_tracking_marker_counts() 
target_frame = find_frame_with_few_tracking_markers(marker_counts, MINIMUM_MARKER_COUNT) 
set_playhead(target_frame)
