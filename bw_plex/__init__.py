import os
import logging
from logging.handlers import RotatingFileHandler

from plexapi.compat import makedirs
from .config import read_or_make

VERSION = '0.0.1'
DEFAULT_FOLDER = os.path.expanduser('~/.config/bw_plex')
THEMES = os.path.join(DEFAULT_FOLDER, 'themes')
TEMP_THEMES = os.path.join(DEFAULT_FOLDER, 'temp_themes')
FP_HASHES = os.path.join(DEFAULT_FOLDER, 'hashes.pklz')
LOG_FILE = os.path.join(DEFAULT_FOLDER, 'log.txt')
log = logging.getLogger('bw_plex')


makedirs(DEFAULT_FOLDER, exist_ok=True)
makedirs(THEMES, exist_ok=True)
makedirs(TEMP_THEMES, exist_ok=True)

CONFIG = read_or_make(os.path.join(DEFAULT_FOLDER, 'config.ini'))

if CONFIG.get('level') in ['', 'info']:  # Should we just use a int?
    lvl = logging.INFO
else:
    lvl = logging.DEBUG

print('ass')

handle = logging.NullHandler()

frmt = logging.Formatter(CONFIG.get('logformat', '%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s'))
handle.setFormatter(frmt)
log.addHandler(handle)


# CONSOLE
stream_handle = logging.StreamHandler()
stream_handle.setFormatter(frmt)
log.addHandler(stream_handle)

frmt = logging.Formatter(CONFIG.get('logformat', '%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s'))
handle.setFormatter(frmt)
log.addHandler(handle)


# FILE
rfh = RotatingFileHandler(LOG_FILE, 'a', 512000, 3)
rfh.setFormatter(frmt)
log.addHandler(rfh)

log.setLevel(lvl)
