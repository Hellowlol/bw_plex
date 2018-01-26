# bw_plex
[![Travis Status](https://travis-ci.org/Hellowlol/bw_plex.svg?branch=master)](https://travis-ci.org/Hellowlol/bw_plex)
[![Cov](https://codecov.io/gh/hellowlol/nrk_api/branch/master/graph/badge.svg)](https://codecov.io/gh/hellowlol/bw_plex/branch/master)
[![GitHub Releases](https://img.shields.io/github/tag/hellowlol/bw_plex.svg?label=github+release)](https://github.com/hellowlol/bw_plex/releases)
[![PyPI version](https://badge.fury.io/py/bw_plex.svg)](https://pypi.python.org/pypi/bw_plex)
[![Code Health](https://landscape.io/github/Hellowlol/bw_plex/master/landscape.svg?style=flat)](https://landscape.io/github/Hellowlol/bw_plex/master)
[![Github commits (since latest release)](https://img.shields.io/github/commits-since/Hellowlol/subtitleedit/latest.svg)](https://github.com/Hellowlol/bw_plex/compare)


binge watching for plex

## Install
pip install bw_plex or pip install -e .


## Usage
bw_plex only works on python 2. :(

```
Usage: bw_plex [OPTIONS] COMMAND [ARGS]...

  CLI tool that monitors pms and jumps the client to after the theme.

Options:
  -d, --debug            Add debug logging.
  -u, --username TEXT    Your plex username
  -p, --password TEXT    Your plex password
  -s, --servername TEXT  The server you want to monitor.
  --url TEXT             url to the server you want to monitor
  -t, --token TEXT       plex-x-token
  -c, --config TEXT      Not in use atm.
  --help                 Show this message and exit.

Commands:
  create_hash_table_from_themes  Create a hashtable from the themes.
  find_theme_youtube             Iterate over all your shows and downloads
                                 the...
  fix_shitty_theme               Set the correct fingerprint of the show
                                 in...
  match                          Manual match for a file.
  process                        Manual process some/all eps.
  test_task
  watch                          Start watching the server for stuff to do.
```

The most common will be:
```bw_plex watch```

## How it works:

bw_plex will connect to PMS using websocket and listen for any playing events.
It will then download the theme and the first 10 minutes of the episode and try to figure out when the theme starts and ends. The result is stored in a sqlite db.
This process is rather slow so the first episode might get skipped. The next episode will be queued up so its ready when you start to watch it.
bw_plex will then seek the client to where the theme ended in that episode.



