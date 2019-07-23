import os
from conftest import TEST_DATA

from bw_plex.config import read_or_make


def test_config():
    conf = read_or_make(os.path.join(TEST_DATA, 'test_config.ini'))

    assert 'level' not in conf['general']
    assert conf['general']['loglevel'] == 'info'
