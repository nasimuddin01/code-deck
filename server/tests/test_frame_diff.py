import numpy as np
from PIL import Image

from code_deck.render import frame_diff


def img(w=320, h=480, fill=0):
    return Image.fromarray(np.full((h, w, 3), fill, dtype=np.uint8))


def test_identical_frames_have_no_bbox():
    assert frame_diff.bbox(img(), img()) is None


def test_single_pixel_change():
    a, b = img(), img()
    b.putpixel((17, 300), (255, 0, 0))
    assert frame_diff.bbox(a, b) == (17, 300, 18, 301)


def test_region_change_and_area():
    a, b = img(), img()
    for x in range(100, 150):
        for y in range(200, 210):
            b.putpixel((x, y), (1, 2, 3))
    box = frame_diff.bbox(a, b)
    assert box == (100, 200, 150, 210)
    assert frame_diff.area(box) == 50 * 10


def test_size_mismatch_is_full():
    assert frame_diff.bbox(img(320, 480), img(320, 481)) == (0, 0, 320, 481)
