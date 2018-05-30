import os
import shutil
import sys
import tempfile
from datetime import datetime as DT


from plexapi.video import Episode, Show
# from plexapi.compat import makedirs
from sqlalchemy.orm.exc import NoResultFound
import pytest

fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bw_plex')

# I dont like it..
sys.path.insert(1, fp)

import bw_plex

old_def = bw_plex.DEFAULT_FOLDER
# Change default folder so we dont mess up the users normal things..
# This needs to deleted after all the tests are done.
bw_plex.DEFAULT_FOLDER = os.path.join(tempfile.gettempdir(), 'bw_plex_test_root')

# Delete any old stuff in the test dir..
if os.path.exists(bw_plex.DEFAULT_FOLDER):
    shutil.rmtree(bw_plex.DEFAULT_FOLDER)

# Copy the stuff over to the new folder.
shutil.copytree(old_def, bw_plex.DEFAULT_FOLDER)

#if not os.path.exists(bw_plex.DEFAULT_FOLDER):
#    os.makedirs(bw_plex.DEFAULT_FOLDER)

bw_plex.THEMES = os.path.join(bw_plex.DEFAULT_FOLDER, 'themes')
bw_plex.TEMP_THEMES = os.path.join(bw_plex.DEFAULT_FOLDER, 'temp_themes')
bw_plex.FP_HASHES = os.path.join(bw_plex.DEFAULT_FOLDER, 'hashes.pklz')
bw_plex.LOG_FILE = os.path.join(bw_plex.DEFAULT_FOLDER, 'log.txt')
bw_plex.INI_FILE = os.path.join(bw_plex.DEFAULT_FOLDER, 'config.ini')
bw_plex.DB_PATH = os.path.join(bw_plex.DEFAULT_FOLDER, 'media.db')

# Do not remove these imports..
import bw_plex.plex as plex
import bw_plex.misc as misc
import bw_plex.credits as credits
from bw_plex.db import session_scope, Preprocessed

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
def in_db(ratingkey):
    rk = int(ratingkey)
    with session_scope() as se:
        try:
            item = se.query(Processed).filter_by(ratingKey=rk).one()
            return item
        except NoResultFound:
            return


@pytest.fixture()
def episode(mocker):

    ep = mocker.MagicMock(spec=Episode)
    ep.TYPE = 'episode'
    ep.name = ''
    ep.title = ''
    ep.grandparentTitle = 'Dexter'
    ep.ratingKey = 1337
    ep._server = ''
    ep.title = 'Dexter'
    ep.index = 1
    ep.parentIndex = 1
    ep.grandparentRatingKey = 1337
    ep.grandparentTheme = ''
    ep.duration = 60 * 60 * 1000  # 1h in ms
    ep.updatedAt = DT(1970, 1, 1)

    def _prettyfilename():
        return 'Dexter.s01.e01'

    def iterParts():
        yield os.path.join(TEST_DATA, 'dexter_s03e01_intro.mkv')

    ep._prettyfilename = _prettyfilename

    return ep


@pytest.fixture()
def media(mocker, episode):
    media = mocker.Mock(spec=Show)
    media.TYPE = 'show'
    media.name = 'dexter'
    media.ratingKey = 1337
    media.theme = ''
    media._server = ''
    media.title = 'dexter'

    def _episodes():
        return [episode]

    media.episodes = _episodes

    return media
