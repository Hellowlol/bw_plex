import os
import configobj
from validate import Validator

import bw_plex


vtor = Validator()


spec = """
url = string(default='')
token = string(default='')
servername = string(default='')
debug = boolean(default=False)
username = string(default='')
password = string(default='')
logformat = string
words = list(default=list())
ignore_show = list(default=list())
level = string(default='info')

""".splitlines()


def read_or_make(fp):
    make_conf = False
    if not os.path.isfile(fp):
        bw_plex.LOG.debug('%s does not exist creating default spec on that location' % fp)
        make_conf = True

    config = configobj.ConfigObj(fp, configspec=spec,
                                 write_empty_values=True,
                                 create_empty=True, raise_errors=True,
                                 list_values=True,)
    config.validate(vtor, copy=True)
    if make_conf is False:
        return config

    config.filename = fp
    config.write()
    return config
