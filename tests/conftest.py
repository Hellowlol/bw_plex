import os
import sys

import pytest

fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bw_plex')

# I dont like it..
sys.path.insert(1, fp)

import bw_plex.plex as plex
import bw_plex.misc as misc


