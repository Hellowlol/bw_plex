import os
import logging
import sys
from logging.handlers import RotatingFileHandler

from plexapi.compat import makedirs, string_type
from plexapi.utils import SecretsFilter
from .config import read_or_make

DEFAULT_FOLDER = os.path.expanduser('~/.config/bw_plex')
THEMES = os.path.join(DEFAULT_FOLDER, 'themes')
TEMP_THEMES = os.path.join(DEFAULT_FOLDER, 'temp_themes')
FP_HASHES = os.path.join(DEFAULT_FOLDER, 'hashes.pklz')
LOG_FILE = os.path.join(DEFAULT_FOLDER, 'log.txt')
LOG = logging.getLogger('bw_plex')
INI_FILE = os.path.join(DEFAULT_FOLDER, 'config.ini')
DB_PATH = os.path.join(DEFAULT_FOLDER, 'media.db')


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


class RedactFilter(logging.Filter):
    """ Logging filter to hide secrets. 
        
        Borrow from https://relaxdiego.com/2014/07/logging-in-python.html
        with some minor adjustments

    """

    def __init__(self, secrets=None):
        self.secrets = secrets or set()

    def add_secret(self, secret):
        if secret is not None:
            self.secrets.add(secret)
        return secret

    def filter(self, record):
        record.msg = self.redact(record.msg)
        if isinstance(record.args, dict):
            for k in record.args.keys():
                record.args[k] = self.redact(record.args[k])
        else:
            record.args = tuple(self.redact(arg) for arg in record.args)
        return True

    def redact(self, msg):
        msg = isinstance(msg, string_type) and msg or str(msg)
        for pattern in self.secrets:
            msg = msg.replace(pattern, "<hidden>")
        return msg


if not CONFIG['general']['debug']:
    LOG.addFilter(RedactFilter(secrets=[i for i in [CONFIG['server']['token'],
                                                    CONFIG['server']['password']] if i]
                               )
                  )
else:
    LOG.info('Log is not sanitized!')
    # TODO add http log.
