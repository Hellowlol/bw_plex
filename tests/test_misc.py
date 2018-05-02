import math
import pytest
from conftest import misc


def test_to_sec():

    assert misc.to_sec(1) == 1
    assert misc.to_sec('00:01') == 1

    assert misc.to_sec('10:59') == 659


def test_get_valid_filename():
    assert misc.get_valid_filename('M*A*S*H') == 'MASH'


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
    assert len(HT.get_theme(media)) == 1
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


def test_has_recap_audio(intro_file):
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


def test_to_time():
    assert misc.to_time(-1) == '00:00'
