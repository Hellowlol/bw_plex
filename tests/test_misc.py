import os
import math
import pytest
from conftest import misc


def test_to_sec():

    assert misc.to_sec(1) == 1
    assert misc.to_sec('00:01') == 1

    assert misc.to_sec('10:59') == 659


def test_get_valid_filename():
    assert misc.get_valid_filename('M*A*S*H') == 'MASH'


def test_ignoreratingkey(film, episode):
    assert misc.ignore_ratingkey(episode, [1337])
    assert misc.ignore_ratingkey(film, [7331])
    assert not misc.ignore_ratingkey(episode, [113])


def test_sec_to_hh_mm_ss():
    x = misc.sec_to_hh_mm_ss(60)
    assert x == '00:01:00'


def test_findnxt(film, episode):
    assert not misc.find_next(film)
    # this should fail was there is no more
    # episodes.
    assert not misc.find_next(episode)


@pytest.mark.xfail
def test_find_offset_ffmpeg(intro_file):
    x = misc.find_offset_ffmpeg(intro_file)
    assert x == 214
    # This failed it isnt really the intro file.
    #assert x == -1
    # failes as find_offset_ffmpeg selects the intro, not the end of the intro..


def test_download_theme_and_get_offset_end(media, HT, intro_file):
    files = misc.download_theme(media, HT, theme_source='youtube', url='https://www.youtube.com/watch?v=BIqBQWB7IUM')
    assert len(files)
    assert HT.has_theme(media)

    new_files = misc.download_theme(media, HT, theme_source='tvtunes')
    assert len(new_files)

    start, end = misc.get_offset_end(intro_file, HT)
    assert math.floor(start) == 116
    assert math.floor(end) == 208


def test_has_recap_subtitle(episode, monkeypatch, mocker):
    def download_subtitle2(*args, **kwargs):
        l = []
        for i in ['Hello you old', 'dog']:
            m = mocker.Mock()
            m.content = i
            l.append(m)

        return [l]

    monkeypatch.setattr(misc, 'download_subtitle', download_subtitle2)
    assert misc.has_recap_subtitle(episode, ['dog'])


# Disabled as this is tested in test_cli.py::test_process_to_db
def _test_has_recap_audio(intro_file):
    audio = misc.convert_and_trim(intro_file)
    assert misc.has_recap_audio(audio, phrase=['previously on'])


def test_search_tunes():
    d = misc.search_tunes('dexter', 1337, url=None)
    assert d


def test_choose(monkeypatch, mocker):
    l = []
    for r in range(10):
        m = mocker.Mock()
        m.title = r
        l.append(m)

    with mocker.patch('click.prompt', side_effect=['0']):
        x = misc.choose('select', l, 'title')
        assert x[0].title == 0

    assert not len(misc.choose('select', [], 'title'))

    with mocker.patch('click.prompt', side_effect=['-1']):
        last = misc.choose('select', l, 'title')
        assert last[0].title == 9

    with mocker.patch('click.prompt', side_effect=['1,7']):
        some = misc.choose('select', l, 'title')
        assert some[0].title == 1
        assert some[1].title == 7

    with mocker.patch('click.prompt', side_effect=['1000', '-1:']):
        some = misc.choose('select', l, 'title')
        assert some[0].title == 9


def test_to_time():
    assert misc.to_time(-1) == '00:00'


def test_edl_line():
    assert '1    2    0' == misc.edl_line(1, 2, 0)


def tests_edl_stuff(tmpdir):
    line = misc.edl_line(1, 2, 0)
    fp = os.path.join(str(tmpdir), 'sn.s13e37.avi')
    f = misc.edl(fp, [line])
    with open(f, 'r') as fh:
        x = fh.read()
        assert x.strip() ==  '1    2    0'
