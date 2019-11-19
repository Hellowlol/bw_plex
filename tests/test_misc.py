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


def test_download_theme_and_find_theme_start_end(media, HT, intro_file):
    files = misc.download_theme(media, HT, theme_source='youtube', url='https://www.youtube.com/watch?v=BIqBQWB7IUM')
    assert len(files)
    assert HT.has_theme(media)

    new_files = misc.download_theme(media, HT, theme_source='tvtunes')
    assert len(new_files)

    start, end = misc.find_theme_start_end(intro_file, HT)
    assert math.floor(start) in (115, 116, 117)
    assert math.floor(end) in (208, 209)


def test_has_recap_subtitle(episode, monkeypatch, mocker):
    def download_subtitle2(*args, **kwargs):
        l = []
        for i in ['Hello you old', 'dog']:
            m = mocker.Mock()
            m.text = i
            l.append(m)

        return [l]

    monkeypatch.setattr(misc, 'download_subtitle', download_subtitle2)
    assert misc.has_recap_subtitle(episode, ['dog'])


def test_search_tunes():
    d = misc.search_tunes('dexter', 1337, url=None)
    assert d


def test_choose(monkeypatch, mocker):
    l = []
    for r in range(10):
        m = mocker.Mock()
        m.title = r
        l.append(m)

    mocker.patch('click.prompt', side_effect=['0'])
    x = misc.choose('select', l, 'title')
    assert x[0].title == 0

    assert not len(misc.choose('select', [], 'title'))

    mocker.patch('click.prompt', side_effect=['-1'])
    last = misc.choose('select', l, 'title')
    assert last[0].title == 9

    mocker.patch('click.prompt', side_effect=['1,7'])
    some = misc.choose('select', l, 'title')
    assert some[0].title == 1
    assert some[1].title == 7

    mocker.patch('click.prompt', side_effect=['1000', '-1:'])
    some = misc.choose('select', l, 'title')
    assert some[0].title == 9


def test_to_time():
    assert misc.to_time(-1) == '00:00'
