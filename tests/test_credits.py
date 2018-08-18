import math
import os
import glob
from collections import defaultdict, Counter
from operator import itemgetter

from conftest import credits, TEST_DATA, misc

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


def test_find_partial_video_inside_another(intro_file):
    # This is cut from the one minute mark of intro_file
    # and last for 2 min
    part = os.path.join(TEST_DATA, 'part.mkv')

    # Check the parts file by file.
    part_hashes = list(credits.hash_file(part, frame_range=False))
    intro_hashes = list(credits.hash_file(intro_file, frame_range=True))

    for straw, sms, i, pms, _ in credits.find_hashes(part_hashes, intro_hashes, no_dupe_frames=True):
        sms_sec = math.floor(sms / 1000)
        pms_sec = math.floor(pms / 1000)

        assert sms_sec >= 60 and sms_sec <= 180
        assert pms_sec >= 0 and pms_sec <= 120
        print('%r %s %s' % (straw, misc.sec_to_hh_mm_ss(sms_sec), misc.sec_to_hh_mm_ss(pms_sec)))

def test_most_common(intro_file):

    intro_hashes = list(credits.hash_file(intro_file))

    def mc():
        #d = {}
        #print(intro_hashes[0][0])
        l = []
        for hash_, t in intro_hashes:
            d = {}
            h = tuple(hash_)
            if h not in d:
                d[h] = 'name'
                d['pos'] = []
                d['pos'].append(t)
                d['size'] = 1
            else:
                d['size'] += 1
                d['pos'].append(t)

            l.append(d)

        return l


    t = mc()
    f = sorted(t, key=itemgetter('size'))
    print(list(f)[0])

