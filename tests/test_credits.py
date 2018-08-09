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
    # print('start', start)
    # print('end', end)


def test_find_credits(outro_file):
    start, end = credits.find_credits(outro_file, frame_range=True, check=9999)
    assert math.floor(start) == 4.0
    assert math.floor(end) == 58


def test_find_hash(outro_file):
    hashes = []
    for h, _ in credits.hash_file(outro_file):
        hashes.append(h)

    needels, files = credits.hash_image_folder(TEST_DATA)

    for i, hash_ in credits.find_hashes(needels, hashes):
        assert files[i] == os.path.join(TEST_DATA, 'text_greenbg_4.jpg')

