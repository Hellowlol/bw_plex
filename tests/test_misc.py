
from conftest import misc


def test_to_sec():

    assert misc.to_sec(1) == 1
    assert misc.to_sec('00:01') == 1

    assert misc.to_sec('10:59') == 659

def test_get_valid_filename():
    assert misc.get_valid_filename('M*A*S*H') == 'MASH'
