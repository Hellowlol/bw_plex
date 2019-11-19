import os
import configobj
from validate import Validator

vtor = Validator()


spec = """
[general]
thread_pool_number = integer(default=10, min=10, max=50)

# Setting debug to True will show your username/password/token in logs!
debug = boolean(default=False)
logformat = ''

# loglevel options: debug or info
loglevel = option('debug', 'info', default='debug')

# mode options: skip_only_theme', 'skip_if_recap'
mode = option('skip_only_theme', 'skip_if_recap', default='skip_only_theme')
ignore_intro_ratingkeys = list(default=list())
ignore_outro_ratingkeys = list(default=list())
# this is used add to the progress we we can start skip faster.
no_wait_tick = integer(default=10, min=0, max=20)

# Clients and users are a whitelist! empty allows all.
clients = list(default=list())
users = list(default=list())

[server]
# The local IP address of your server plus port: http://192.168.0.0:32400
url = string(default='')
# Search online for plex token to find this info.
token = string(default='')
verify_ssl = boolean(default=False)
name = string(default='')
username = string(default='')
password = string(default='')

[tv]
# This lets bw_plex know that its suppose to analyze the video for credits
check_credits = boolean(default=False)
# Setting this to 'stop' will stop playback when credits starts.
# if set to seek it will
check_credits_action = option('', 'seek', 'stop', default='')
# This will start the next available episode
## NOTE: check_credits_action need to be `stop` for this to work.
check_credits_start_next_ep = boolean(default=True)
credits_delay = integer(default=0)
check_credits_sec = integer(default=120)
check_for_theme_sec = integer(default=600, min=300, max=600)
check_intro_ffmpeg_sec = integer(default=600)
process_recently_added = boolean(default=False)
process_deleted = boolean(default=False)
# Options: 'all', 'tvtunes', 'plex', 'youtube'
theme_source = option('all', 'tvtunes', 'plex', 'youtube', default='all')
words = list(default=list('previously on', 'last season', 'last episode'))
create_edl = boolean(default=False)
edl_action_type = integer(default=3)
create_chapters = boolean(default=False)

[movie]
check_credits = boolean(default=False)
check_credits_action = string(default='')
check_credits_sec = integer(default=600)
credits_delay = integer(default=0)
check_intro_ffmpeg_sec = integer(default=600)
process_recently_added = boolean(default=False)
process_deleted = boolean(default=False)
create_edl = boolean(default=False)
edl_action_type = integer(default=3)
create_chapters = boolean(default=False)

[hashing]
check_frames = boolean(default=False)
#every_n = not in use atm.


# remaps can use used to location set a partial location
# this is usefull if bw_plex is running on another computer.
# the key is the path plex user and the value is the computer running
# bw_plex. Ex:
# /tvseries/ = W:\\
[remaps]



""".splitlines()


def migrate(conf):
    """ Used to clean up change config options."""

    if 'level' in conf['general']:
        if conf['general']['level'] != conf['general']['loglevel']:
            conf['general']['loglevel'] = conf['general']['level']

        del conf['general']['level']

    for section in ['movie', 'tv']:
        for old_key in ['create_edl, edl_action_type']:
            if old_key in conf[section]:
                del conf[section][old_key]


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
