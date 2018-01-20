import os

from plexapi.compat import makedirs
from .config import read_or_make

VERSION = '0.0.1'
DEFAULT_FOLDER = os.path.expanduser('~/.config/bw_plex')
THEMES = os.path.join(DEFAULT_FOLDER, 'themes')
TEMP_THEMES = os.path.join(DEFAULT_FOLDER, 'temp_themes')
FP_HASHES = os.path.join(DEFAULT_FOLDER, 'hashes.pklz')

makedirs(THEMES, exist_ok=True)
makedirs(TEMP_THEMES, exist_ok=True)

CONFIG = read_or_make(os.path.join(DEFAULT_FOLDER, 'config.ini'))
