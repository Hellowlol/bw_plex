import os
import logging
import configobj
from validate import Validator


vtor = Validator()
LOG = logging.getLogger(__name__)


spec = """
url = string(default='')
token = string(default='')
servername = string(default='')
debug = boolean(default=False)
username = string(default='')
password = string(default='')
# This is a list of ratingKeys!
ignore_show = list(default=[])

""".splitlines()

# 
def read_or_make(fp):
    make_conf = False
    if not os.path.isfile(fp):
        LOG.debug('%s does not exist creating default spec on that location' % fp)
        make_conf = True

    config = configobj.ConfigObj(fp, configspec=spec, write_empty_values=True)
    config.validate(vtor, copy=True)
    if make_conf is False:
        return config

    config.filename = fp
    config.write()
    return config