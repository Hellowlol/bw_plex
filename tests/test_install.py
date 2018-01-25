import pytest
import subprocess


def test_that_bwplex_is_installed():
    assert subprocess.check_call(['bw_plex', '--help']) == 0
