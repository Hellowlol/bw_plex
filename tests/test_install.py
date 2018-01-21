import pytest
import subprocess


def test_that_bwplex_is_installed():
    subprocess.check_call(['bwplex', '--help'])
