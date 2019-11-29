import math
import os
import glob

from conftest import credits, TEST_DATA

image_type = ('.png', '.jpeg', '.jpg')


def test_locate_text():
    files = glob.glob('%s/*.*' % TEST_DATA)

    for f in sorted(files):
        if f.endswith(image_type):
            if 'fail' in f:
                assert not len(credits.locate_text(f))
                if f.endswith('blackbg_greentxt_1_fail.png'):
                    assert len(credits.locate_text_east(f))
                else:
                    assert not len(credits.locate_text_east(f))
            else:
                assert len(credits.locate_text(f))
                assert len(credits.locate_text_east(f))


def test_extract_text():
    fp = os.path.join(TEST_DATA, 'blacktext_whitebg_2.png')
    assert credits.extract_text(fp) == b'A\n\nJOHN GOLDWYN\n\nPRODUCTION'


def test_find_credits_frame_range_false(outro_file):
    start, end = credits.find_credits(outro_file, offset=3, frame_range=False, check=7)
    assert round(start) == 4
    assert math.floor(end) == 4


def test_find_credits_east(outro_file):
    start, end = credits.find_credits(outro_file, frame_range=True, check=9999)
    assert math.floor(start) == 4.0
    assert math.floor(end) >= 58


def test_find_credits(outro_file):
    start, end = credits.find_credits(outro_file, frame_range=True, check=9999, method='normal')
    assert math.floor(start) == 4.0
    assert math.floor(end) >= 58
