import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from multiprocessing.pool import ThreadPool as Pool

from joblib import Memory

THEMES = None
TEMP_THEMES = None
FP_HASHES = None
LOG_FILE = None
LOG = logging.getLogger('bw_plex')
INI_FILE = None
DB_PATH = None
CONFIG = None
PMS = None
POOL = None



DEFAULT_FOLDER = os.environ.get('bw_plex_default_folder') or os.path.expanduser('~/.config/bw_plex')
MEMORY = Memory(location=DEFAULT_FOLDER, verbose=0)

if os.path.isdir(DEFAULT_FOLDER) and not os.access(DEFAULT_FOLDER, os.W_OK):
    print('You default folder is not writeable')
    sys.exit()




subcommands = ['watch', 'add_theme_to_hashtable', 'check_db', 'export_db',
               'ffmpeg_process', 'manually_correct_theme', 'process', 'match', 'add_hash_frame',
               'set_manual_theme_time', 'test_a_movie', 'create_edl_from_db', 'add_ref_frame']


def trim_argv(args=None):  # pragma: no cover
    """Remove any sub commands and arguments for subcommands."""
    args = args or sys.argv[:]
    for cmd in subcommands:
        try:
            idx = args.index(cmd)
            return args[:idx]
        except ValueError:
            pass

    return []


class RedactFilter(logging.Filter):
    """ Logging filter to hide secrets.

        Borrow from https://relaxdiego.com/2014/07/logging-in-python.html
        with some minor adjustments

    """

    def __init__(self, secrets=None):
        self.secrets = secrets or set()

    def add_secret(self, secret):
        if secret is not None and secret:
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
        msg = isinstance(msg, str) and msg or str(msg)
        for pattern in self.secrets:
            msg = msg.replace(pattern, "<hidden>")
        return msg


FILTER = RedactFilter()


def arg_extract(keys=None):
    """ghetto parser for cli arguments."""
    possible_kw = {'token': ('-t', '--token'),
                   'username': ('-u', '--username'),
                   'password': ('-p', '--password'),
                   'servername': ('-s', '--servername'),
                   'config': ('-c', '--config'),
                   'verify_ssl': ('-vs', '--verify_ssl'),
                   'default_folder': ('-df', '--default_folder'),
                   'url': ('-u', '--username'),
                   'debug': ('-d', '--debug'),
                   'nice': ('-n', '--nice')
                   }

    d = {}
    trimmed_args = trim_argv()
    for i, arg in enumerate(trimmed_args):
        for k, v in possible_kw.items():
            if arg in v:
                # Just set the flags.
                if k == 'debug':
                    d[k] = True
                else:
                    d[k] = trimmed_args[i + 1]

    if 'debug' not in d:
        d['debug'] = None

    if keys:
        return dict((key, value) for key, value in d.items() if key in keys)

    return d


def init(folder=None, debug=False, config=None):
    global DEFAULT_FOLDER, THEMES, TEMP_THEMES, LOG_FILE, INI_FILE, INI_FILE, DB_PATH, CONFIG, FP_HASHES, POOL, MEMORY

    DEFAULT_FOLDER = folder or DEFAULT_FOLDER

    if os.path.isdir(DEFAULT_FOLDER) and not os.access(DEFAULT_FOLDER, os.W_OK):
        print('You default folder is not writeable')
        sys.exit()

    THEMES = os.path.join(DEFAULT_FOLDER, 'themes')
    TEMP_THEMES = os.path.join(DEFAULT_FOLDER, 'temp_themes')
    FP_HASHES = os.path.join(DEFAULT_FOLDER, 'hashes.pklz')
    LOG_FILE = os.path.join(DEFAULT_FOLDER, 'log.txt')
    INI_FILE = config or os.path.join(DEFAULT_FOLDER, 'config.ini')
    DB_PATH = os.path.join(DEFAULT_FOLDER, 'media.db')

    os.makedirs(DEFAULT_FOLDER, exist_ok=True)
    os.makedirs(THEMES, exist_ok=True)
    os.makedirs(TEMP_THEMES, exist_ok=True)

    # leave this, intented to overwrite incase someone want to use a another
    # location while still running intro as a script.
    MEMORY = Memory(location=DEFAULT_FOLDER, verbose=0)

    from bw_plex.config import read_or_make
    CONFIG = read_or_make(INI_FILE)
    POOL = Pool(int(CONFIG.get('thread_pool_number', 10)))

    from bw_plex.db import db_init
    db_init()

    handle = logging.NullHandler()
    frmt = logging.Formatter(CONFIG.get('logformat', '%(asctime)s :: %(name)s :: %(levelname)s :: %(filename)s:%(lineno)d :: %(message)s'))
    handle.setFormatter(frmt)
    LOG.addHandler(handle)

    stream_handle = logging.StreamHandler()
    stream_handle.setFormatter(frmt)
    LOG.addHandler(stream_handle)

    handle.setFormatter(frmt)
    LOG.addHandler(handle)

    # FILE
    rfh = RotatingFileHandler(LOG_FILE, 'a', 512000, 3)
    rfh.setFormatter(frmt)
    LOG.addHandler(rfh)

    log_to_lvl = {'debug': logging.DEBUG,
                  'info': logging.INFO,
                  'warning': logging.WARNING}

    if debug is True:
        LOG.setLevel(logging.DEBUG)
    else:
        try:
            lvl = log_to_lvl[CONFIG['general']['loglevel']]
            LOG.setLevel(lvl)
        except KeyError:
            LOG.error('Invalid option for loglevel in fonfig file, defualting to level to debug')
            LOG.setLevel(logging.DEBUG)

    # This import is slow
    import pkg_resources

    LOG.info('Using bw_plex version %s', pkg_resources.get_distribution("bw_plex").version)
    LOG.info('default folder set to %s', DEFAULT_FOLDER)

    FILTER.add_secret(CONFIG['server']['token'])
    FILTER.add_secret(CONFIG['server']['password'])
    secret_args = arg_extract(keys=['username', 'token', 'password']).values()
    for arg in secret_args:
        FILTER.add_secret(arg)

    if debug is None:
        if CONFIG['general']['debug'] is False:
            LOG.addFilter(FILTER)
    elif debug is False:
        LOG.addFilter(FILTER)
    else:
        LOG.info('Log is not sanitized!')

        packages = ['plexapi', 'requests', 'urllib3']
        for pack in packages:
            _pack = logging.getLogger(pack)
            _pack.setLevel(logging.DEBUG)
            _pack.addHandler(rfh)
            _pack.addHandler(stream_handle)
