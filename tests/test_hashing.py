
import os
import math
from conftest import hashing, TEST_DATA, misc


def test_string_hash():
    assert 'c20ad4d76fe97759aa27a0c99bff6710' == hashing.string_hash([[1], [2]])


def test_find_hash(outro_file):
    hashes = list(hashing.hash_file(outro_file))
    img_file = os.path.join(TEST_DATA, 'out8.jpg')
    img_hash, frame, pos = next(hashing.hash_file(img_file))

    needels, files = hashing.hash_image_folder(TEST_DATA)
    for stack_hash, stack_ms, stacknr, needel_ms, needelnr, stacknr in hashing.find_hashes(needels, hashes):
        assert stack_hash == img_hash and files[needelnr]


def test_find_where_a_img_is_in_video(outro_file):
    img_file = os.path.join(TEST_DATA, 'out8.jpg')

    h, f, t = next(hashing.hash_file(img_file))

    v_hashes = list(hashing.hash_file(outro_file))

    for vh, v_frames, i in v_hashes:
        if vh == h:
            # Check that the image if between 47 sec and 49 sec.
            assert i > 47464 and i < 49425


def test_find_partial_video_inside_another(intro_file):
    # This is cut from the one minute mark of intro_file
    # and last for 2 min
    part = os.path.join(TEST_DATA, 'part.mkv')

    # Check the parts file by file.
    part_hashes = list(hashing.hash_file(part, frame_range=False))
    intro_hashes = list(hashing.hash_file(intro_file, frame_range=True))

    for straw, sms, i, pms, _, z in hashing.find_hashes(part_hashes, intro_hashes, no_dupe_frames=True):
        sms_sec = math.floor(sms / 1000)
        pms_sec = math.floor(pms / 1000)

        assert sms_sec >= 60 and sms_sec <= 180
        assert pms_sec >= 0 and pms_sec <= 120
        # print('%r %s %s' % (straw, misc.sec_to_hh_mm_ss(sms_sec), misc.sec_to_hh_mm_ss(pms_sec)))
