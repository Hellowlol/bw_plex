import os
import logging
import sys
from logging.handlers import RotatingFileHandler

from plexapi.compat import makedirs
from .config import read_or_make


#VERSION = '0.0.1'
DEFAULT_FOLDER = os.path.expanduser('~/.config/bw_plex')
THEMES = os.path.join(DEFAULT_FOLDER, 'themes')
TEMP_THEMES = os.path.join(DEFAULT_FOLDER, 'temp_themes')
FP_HASHES = os.path.join(DEFAULT_FOLDER, 'hashes.pklz')
LOG_FILE = os.path.join(DEFAULT_FOLDER, 'log.txt')
LOG = logging.getLogger('bw_plex')
INI_FILE = os.path.join(DEFAULT_FOLDER, 'config.ini')


makedirs(DEFAULT_FOLDER, exist_ok=True)
makedirs(THEMES, exist_ok=True)
makedirs(TEMP_THEMES, exist_ok=True)

CONFIG = read_or_make(INI_FILE)

if CONFIG.get('level') in ['', 'info']:  # Should we just use a int?
    lvl = logging.INFO
else:
    lvl = logging.DEBUG

handle = logging.NullHandler()

frmt = logging.Formatter(CONFIG.get('logformat', '%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s'))
handle.setFormatter(frmt)
LOG.addHandler(handle)

# CONSOLE
stream_handle = logging.StreamHandler()
stream_handle.setFormatter(frmt)
LOG.addHandler(stream_handle)

handle.setFormatter(frmt)
LOG.addHandler(handle)

# FILE
rfh = RotatingFileHandler(LOG_FILE, 'a', 512000, 3)
rfh.setFormatter(frmt)
LOG.addHandler(rfh)

LOG.setLevel(lvl)

# Disable some logging..
logging.getLogger("plexapi").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
