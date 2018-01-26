
from conftest import misc


def test_to_sec():

    assert misc.to_sec(1) == 1
    assert misc.to_sec('00:01') == 1

    assert misc.to_sec('10:59') == 659


def test_get_valid_filename():
    assert misc.get_valid_filename('M*A*S*H') == 'MASH'

def test_search_tunes():
    x = misc.search_tunes('Dexter', 1)
    assert len(x) == 1 and 'Dexter__1' in list(x.keys())


