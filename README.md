# bw_plex
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/4c2a18e04d3d45648224b4be4c45e20b)](https://app.codacy.com/app/Hellowlol/bw_plex?utm_source=github.com&utm_medium=referral&utm_content=Hellowlol/bw_plex&utm_campaign=Badge_Grade_Dashboard)
[![Travis Status](https://travis-ci.org/Hellowlol/bw_plex.svg?branch=master)](https://travis-ci.org/Hellowlol/bw_plex)
[![Cov](https://codecov.io/gh/hellowlol/bw_plex/branch/master/graph/badge.svg)](https://codecov.io/gh/hellowlol/bw_plex/branch/master)
[![GitHub Releases](https://img.shields.io/github/tag/hellowlol/bw_plex.svg?label=github+release)](https://github.com/hellowlol/bw_plex/releases)
[![PyPI version](https://badge.fury.io/py/bw-plex.svg)](https://badge.fury.io/py/bw-plex)
![GitHub last commit](https://img.shields.io/github/last-commit/hellowlol/bw_plex.svg)
![docker build](https://img.shields.io/docker/build/hellowlol/bw_plex.svg)


A tool for skipping intro and outro for plex.

## Features
- identify outro start and end scanning the video for credits text.
- identify intro start and end using themes song or blackframes and audio silence.
- identify if the video has a recap using subtitles and audio.
- download theme songs.
- process on playback start.
- process on recently added.
- control the client to skip intro/outro.
- start next episode when the credits start.
- create chapter for intro and outro

## Install
You should install this from github as this project isnt stable.
```pip install -e git+https://github.com/Hellowlol/bw_plex.git#egg=bw_plex```
or using a docker ```docker pull hellowlol/bw_plex```. You may also need to `pip install Pillow`.


## Usage
**Note:** This tool only works on your local network and use a 64 bit python install.

```
Usage: bw_plex

[OPTIONS] COMMAND [ARGS]...

  CLI tool that monitors pms and jumps the client to after the theme.

Options:
  -d, --debug             Add debug logging.
  -u, --username TEXT     Your plex username
  -p, --password TEXT     Your plex password
  -s, --servername TEXT   The server you want to monitor.
  --url TEXT              url to the server you want to monitor
  -t, --token TEXT        plex-x-token
  -c, --config TEXT       Not in use atm.
  -vs, --verify_ssl TEXT  Enable this to allow insecure connections to PMS
  --help                  Show this message and exit.

Commands:
  add_theme_to_hashtable  Create a hashtable from the themes.
  check_db                Do a manual check of the db.
  create_config           Create a config file.
  export_db               Export the db to some other format.
  ffmpeg_process          Simple manual test for ffmpeg_process with...
  manually_correct_theme  Set the correct fingerprint of the show in...
  match                   Manual match for a file.
  process                 Manual process some/all eps.
  set_manual_theme_time   Set a manual start and end time for a theme.
  watch                   Start watching the server for stuff to do.
```

You can read the help for the subcommands using --help:
```bw_plex export_db --help```

The most common command is:
```bw_plex watch --url "http://....." -t "aaabb" ``` you can skip the url and token flags if you edit the config.ini

## Resources

The memory usage and especially the CPU can get very high. If you running bw_plex in a docker on a shared server consider adding resource constraints. For simple cpu constraints you can set the niceness with the nice flag `bw_plex --nice nicenesslevel command` 

## Configuration File

bw_plex automatically generates a default configuration file located at ```~/.config/bw_plex/config.ini```. Most of the entries have notes accompanying them explaining what each one does, and what the options are.

## How it works:

Bw_plex listens for playing events using websocket. We download the first 10 minutes of that episode and/or the theme music from YouTube/tvtunes/Plex.

We then create a audio print from the theme song that we match against the audio of the 10 minutes of the episode. (There’s a backup method that uses audio silence in combination with black frames too).

We then check if this episode has a recap using subtitles and audio where we look for clues like last season, previously on (add you own words in the config), then we download last part of the episode an and indentify the start and end of the outro.

Depending on your settings we will then allow playback until the theme start or just jump straight to intro end if we also should skip recaps.

Since this is a rather slow process we also start processing the next episode so next time you watch the same show we instantly seek the client to the end of the theme.
