import pytest
import subprocess


def test_that_bwplex_is_installed():
    assert subprocess.check_call(['bw_plex', '--help']) == 0


d = {
    "PlaySessionStateNotification": [{
        "guid":
        "",
        "key":
        "/library/metadata/65787",
        "playQueueItemID":
        22631,
        "ratingKey":
        "65787",
        "sessionKey":
        "84",
        "state":
        "paused",
        "transcodeSession":
        "4avh8p7h64n4e9a16xsqvr9e",
        "url":
        "",
        "viewOffset":
        244000
    }],
    "size":
    1,
    "type":
    "playing"
}


def _test_check():
    pass
