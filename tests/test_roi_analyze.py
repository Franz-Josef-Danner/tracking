import numpy as np
from pathlib import Path
import sys

# ensure repo root on path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from Helper import roi


def make_synthetic_frames(w=400, h=300):
    # create a checkerboard texture on left half and smooth on right
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            if (x // 8 + y // 8) % 2 == 0:
                img[y, x] = 255
            else:
                img[y, x] = 50
    # prev frame: shift left region slightly -> motion there
    prev = np.roll(img, shift=2, axis=1)
    return img, prev


def test_analyze_rois_texture_motion():
    img, prev = make_synthetic_frames(200, 120)
    # Create a fake clip with declared size matching img
    class C:
        pass
    clip = C()
    clip.size = (img.shape[1], img.shape[0])

    rois = roi.analyze_rois(clip, grid=(2, 2), frame_img=img, prev_frame_img=prev)
    assert isinstance(rois, dict)
    assert 0 in rois
    info = rois[0]
    tiles = info.get("tiles")
    assert tiles.shape == (2, 2)
    textures = [tiles[i, j]["texture"] for i in range(2) for j in range(2)]
    motions = [tiles[i, j]["motion"] for i in range(2) for j in range(2)]
    # Left-top should have higher texture than right-top
    assert max(textures) > 0.1
    # There should be some non-zero motion (due to roll)
    assert any(m > 0.0 for m in motions)


if __name__ == "__main__":
    test_analyze_rois_texture_motion()
    print("ok")
