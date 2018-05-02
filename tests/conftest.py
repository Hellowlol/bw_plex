import os
import shutil
import sys
import tempfile

import pytest

fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bw_plex')

# I dont like it..
sys.path.insert(1, fp)

# This is reimported by the tests.
# Do not delete.

import bw_plex
# Change default folder so we dont mess up the users normal things..
# This needs to deleted after all the tests are done.
bw_plex.DEFAULT_FOLDER = os.path.join(tempfile.gettempdir(), 'bw_plex_test_root')

# Delete any old stuff in the test dir..
if os.path.exists(bw_plex.DEFAULT_FOLDER):
    shutil.rmtree(bw_plex.DEFAULT_FOLDER)

if not os.path.exists(bw_plex.DEFAULT_FOLDER):
    os.makedirs(bw_plex.DEFAULT_FOLDER)

bw_plex.THEMES = os.path.join(bw_plex.DEFAULT_FOLDER, 'themes')
bw_plex.TEMP_THEMES = os.path.join(bw_plex.DEFAULT_FOLDER, 'temp_themes')
bw_plex.FP_HASHES = os.path.join(bw_plex.DEFAULT_FOLDER, 'hashes.pklz')
bw_plex.LOG_FILE = os.path.join(bw_plex.DEFAULT_FOLDER, 'log.txt')
bw_plex.INI_FILE = os.path.join(bw_plex.DEFAULT_FOLDER, 'config.ini')

from plexapi.video import Episode, Show
import bw_plex.plex as plex
import bw_plex.misc as misc
import bw_plex.credits as credits


TEST_DATA = os.path.join(os.path.dirname(__file__), 'test_data')


@pytest.fixture()
def outro_file():
    fp = os.path.join(TEST_DATA, 'out.mkv')
    return fp


@pytest.fixture()
def intro_file():
    fp = os.path.join(TEST_DATA, 'dexter_s03e01_intro.mkv')
    return fp


@pytest.fixture(scope='session')
def HT():
    return misc.get_hashtable()


@pytest.fixture()
def media(mocker):
    media = mocker.Mock(spec=Show)
    media.TYPE = 'show'
    media.name = 'dexter'
    media.ratingKey = 1337
    media.theme = ''
    media._server = ''
    media.title = 'dexter'

    return media


@pytest.fixture()
def episode(mocker):

    ep = mocker.Mock(spec=Episode)
    ep.TYPE = 'episode'
    ep.name = ''
    ep.title = ''
    ep.grandparentTitle = 'Dexter'
    ep.ratingKey = 1337
    ep._server = ''
    ep.title = 'Dexter'
    ep.index = 1
    ep.parentIndex = 1

    return ep
