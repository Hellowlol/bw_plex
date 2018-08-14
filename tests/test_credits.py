import math
import os
import glob

from conftest import credits, TEST_DATA

image_type = ('.png', '.jpeg', '.jpg')


def test_locate_text():
    files = glob.glob('%s\*.*' % TEST_DATA)

    for f in sorted(files):
        if f.endswith(image_type):
            if 'fail' in f:
                assert not credits.locate_text(f)
            else:
                assert credits.locate_text(f)


def test_extract_text():
    fp = os.path.join(TEST_DATA, 'blacktext_whitebg_2.png')
    assert credits.extract_text(fp) == b'A\n\nJOHN GOLDWYN\n\nPRODUCTION'


def test_find_credits_frame_range_false(outro_file):
    start, end = credits.find_credits(outro_file, offset=3, frame_range=False, check=7)
    assert math.floor(start) == 3
    assert math.floor(end) == 3


def test_find_credits(outro_file):
    start, end = credits.find_credits(outro_file, frame_range=True, check=9999)
    assert math.floor(start) == 4.0
    assert math.floor(end) == 58


def test_find_hash(outro_file):
    hashes = list(credits.hash_file(outro_file))
    img_file = os.path.join(TEST_DATA, 'out8.jpg')
    img_hash, _ = next(credits.hash_file(img_file))

    needels, files = credits.hash_image_folder(TEST_DATA)

    for kek, pos, i, n in credits.find_hashes(needels, hashes):
        assert kek == img_hash and files[n] == img_file


def test_find_where_a_img_is_in_video(outro_file):
    img_file = os.path.join(TEST_DATA, 'out8.jpg')

    h, t = next(credits.hash_file(img_file))

    v_hashes = list(credits.hash_file(outro_file))

    for vh, i in v_hashes:
        if vh == h:
            # Check that the image if between 47 sec and 49 sec.
            assert i > 47464 and i < 49425
