# bw_plex
binge watching for plex

## Install
pip install bw_plex


## Usage
bw_plex only works on python 2. :(

```
Usage: plex.py [OPTIONS] COMMAND [ARGS]...

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

## How it works:

bw_plex will connect to PMS using websocket and listen for any playing events.
It will then download the theme and the first 10 minutes of the episode and try to figure out when the theme starts and ends. The result is stored in a sqlite db.
This process is rather slow so the first episode might get skipped. The next episode will be queued up so its ready when you start to watch it.
bw_plex will then seek the client to where the theme ended in that episode.



