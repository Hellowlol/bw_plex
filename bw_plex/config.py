import os
import configobj
from validate import Validator

vtor = Validator()


spec = """
[general]
thread_pool_number = integer(default=10, min=10, max=50)
debug = boolean(default=False)
logformat = ''
level = option('debug', 'info', default='debug')
mode = option('skip_only_theme', 'skip_if_recap', default='skip_only_theme')
ignore_intro_ratingkeys = list(default=list())
ignore_outro_ratingkeys = list(default=list())

# Clients and users are a whitelist! empty allows all.
clients = list(default=list())
users = list(default=list())

[server]
url = string(default='')
token = string(default='')
verify_ssl = boolean(default=False)
name = string(default='')
username = string(default='')
password = string(default='')

[tv]
# This could be season, show or ep.
#ignore_intro_ratingkeys = list(default=list())
#ignore_outro_ratingkeys = list(default=list())
check_credits = boolean(default=False
check_credits_action = string(default='')
check_credits_start_next_ep = boolean(default=True)
check_credits_sec = integer(default=120)
check_for_theme_sec = integer(default=600, min=300, max=600)
check_intro_ffmpeg_sec = integer(default=600)
process_recently_added = boolean(default=False)
process_deleted = boolean(default=False)
theme_source = option('all', 'tvtunes', 'plex', 'youtube', default='all')
words = list(default=list('previously on', 'last season', 'last episode'))

# This will be ignored for now.
[movie]
check_credits = boolean(default=False)
check_credits_action = string(default='')
check_credits_sec = integer(default=600)
check_intro_ffmpeg_sec = integer(default=600)
process_recently_added = boolean(default=False)
process_deleted = boolean(default=False)
#ignore_intro_ratingkeys = list(default=list())
#ignore_outro_ratingkeys = list(default=list())

""".splitlines()


def migrate(conf):
    return conf


def read_or_make(fp):
    default = configobj.ConfigObj(None, configspec=spec,
                                  write_empty_values=True,
                                  create_empty=True,
                                  list_values=True)

    # Overwrite defaults options with what the user has given.
    if os.path.isfile(fp):
        config = configobj.ConfigObj(fp,
                                     write_empty_values=True,
                                     create_empty=True,
                                     list_values=True)
        default.merge(config)

    default.validate(vtor, copy=True)

    default = migrate(default)

    default.filename = fp
    default.write()
    return default
