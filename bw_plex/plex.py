#!/usr/bin/env python
# -*- coding: utf-8 -*-

import itertools
import logging
import os
import signal
import struct
import tempfile
import threading
import time
import webbrowser
from collections import defaultdict
from functools import wraps

import bw_plex.edl as edl
import click
import plexapi
import requests
from bw_plex import CONFIG, FP_HASHES, INI_FILE, LOG, PMS, POOL, THEMES, Pool
from bw_plex.audio import convert_and_trim
from bw_plex.chromecast import get_chromecast_player
from bw_plex.config import read_or_make
from bw_plex.credits import find_credits
from bw_plex.db import Images, Processed, Reference_Frame, session_scope
from bw_plex.hashing import create_imghash, hash_file
from bw_plex.misc import (analyzer, choose, download_theme, find_next,
                          find_offset_ffmpeg, find_theme_start_end,
                          get_hashtable, get_pms, has_recap, ignore_ratingkey,
                          to_ms, to_sec, to_time)
from lomond import WebSocket
from lomond.persist import persist
from sqlalchemy.orm.exc import NoResultFound

# Serves as simple locks so we dont start processing stuff
# over and over again on each websocket tick and the user can seek
# manually if bw_plex misses on the theme or credits.
IN_PROG = []
JUMP_LIST = []
CREDITS_LIST = []
SHOWS = {}
HT = None
# Just we can kill the watch
# gracefully on the docker.
EVENT = threading.Event()

is_64bit = struct.calcsize('P') * 8
if not is_64bit:  # pragma: no cover
    LOG.info('You not using a python 64 bit version.')


def shutdown_handler(sig, stack):  # pragma: no cover
    LOG.info('Got a signal %s doing some '
             'cleanup before shutting down', sig)

    # The events sets method shutsdown
    # the ws connection.
    EVENT.set()
    LOG.info('Shutting down ws connection')

    # Make sure we save the hashtable.
    global HT
    if HT and HT.dirty:
        LOG.info('Saving the hashtable')
        HT.save()

    # We just terminate the damn pool as
    # some of the stuff we are doing can take a really long time,
    # might be ffmpeg that is hugging it or something. dunno, idk.
    POOL.terminate()
    LOG.info('Shutting down the POOL')
    raise SystemExit('Goodbye')


def log_exception(func):
    @wraps(func)
    def inner(*args, **kwargs):
        try:
            if kwargs:
                return func(*args, **kwargs)
            else:
                return func(*args)

        except:  # pragma: no cover
            err = "There was an exception in "
            err += func.__name__
            LOG.exception(err)
            raise

    return inner


def find_all_movies_shows(func=None):  # pragma: no cover
    """ Helper of get all the shows on a server.

        Args:
            func (callable): Run this function in a threadpool.

        Returns: List

    """
    all_shows = []

    for section in PMS.library.sections():
        if section.TYPE in ('movie', 'show'):
            all_shows += section.all()

    if func:
        return POOL.map(func, all_shows)

    return all_shows


@log_exception
def process_to_db(media, theme=None, vid=None, start=None, end=None, ffmpeg_end=None,
                  recap=None, credits_start=None, credits_end=None):
    """Process a plex media item to the db

       Args:
            media (Episode obj):
            theme: path to the theme.
            vid: path to the stripped wav of the media item.
            start (None, int): of theme.
            end (None, int): of theme.
            ffmpeg_end (None, int): What does ffmpeg think is the start of the ep.
            recap(None, bool): If this how has a recap or not
            credits_start(None, int): The offset (in sec) the credits text starts
            credits_end(None, int): The offset (in sec) the credits text ends

       Returns:
            None

    """
    global HT
    add_images = False
    edl_file = None

    # This will download the theme and add it to
    # the hashtable if its missing
    if media.TYPE == 'episode' and theme is None:
        if HT.has_theme(media, add_if_missing=False) is False:
            LOG.debug('downloading theme from process_to_db')
            theme = download_theme(media, HT)

    name = media._prettyfilename()
    LOG.debug('Started to process %s', name)

    # vid is aud ffs.
    if vid is None and media.TYPE == 'episode':
        vid = convert_and_trim(check_file_access(media), fs=11025,
                               trim=CONFIG['tv'].get('check_for_theme_sec', 600))

    # Find the start and the end of the theme in the episode file.
    if end is None and media.TYPE == 'episode':
        start, end = find_theme_start_end(vid, HT)

    # Guess when the intro ended using blackframes and audio silence.
    if ffmpeg_end is None:
        if media.TYPE == 'episode':
            trim = CONFIG['tv'].get('check_intro_ffmpeg_sec')
        else:
            trim = CONFIG['movie'].get('check_intro_ffmpeg_sec')
        ffmpeg_end = find_offset_ffmpeg(check_file_access(media), trim=trim)

    # Check for recap.
    if recap is None:
        recap = has_recap(media, CONFIG['tv'].get('words', []), audio=vid)

    if (media.TYPE == 'episode' and CONFIG['tv'].get('check_credits') is True and
        credits_start is None and credits_end is None):

        dur = media.duration / 1000 - CONFIG['tv'].get('check_credits_sec', 120)
        credits_start, credits_end = find_credits(check_file_access(media),
                                                  offset=dur,
                                                  check=-1)

    elif (media.TYPE == 'movie' and CONFIG['movie'].get('check_credits') is True
          and credits_start is None and credits_end is None):

        dur = media.duration / 1000 - CONFIG['movie'].get('check_credits_sec', 600)
        credits_start, credits_end = find_credits(check_file_access(media),
                                                  offset=dur,
                                                  check=-1)
    else:
        # We dont want to find the credits.
        credits_start = -1
        credits_end = -1

    # We assume this is kinda right, # double check this # TODO
    location = list(i.file for i in media.iterParts() if i)[0]

    with session_scope() as se:
        try:
            se.query(Processed).filter_by(ratingKey=media.ratingKey).one()
        except NoResultFound:
            if media.TYPE == 'episode':
                p = Processed(show_name=media.grandparentTitle,
                              title=media.title,
                              type=media.TYPE,
                              theme_end=end,
                              theme_start=start,
                              theme_start_str=to_time(start),
                              theme_end_str=to_time(end),
                              ffmpeg_end=ffmpeg_end,
                              ffmpeg_end_str=to_time(ffmpeg_end),
                              credits_start=credits_start,
                              credits_start_str=to_time(credits_start),
                              credits_end=credits_end,
                              credits_end_str=to_time(credits_end),
                              duration=media.duration,
                              ratingKey=media.ratingKey,
                              grandparentRatingKey=media.grandparentRatingKey,
                              prettyname=media._prettyfilename(),
                              updatedAt=media.updatedAt,
                              has_recap=recap,
                              location=location
                              )
                se.add(p)
                LOG.debug('Added %s to media.db', name)

            elif media.TYPE == 'movie' and CONFIG.get('movie', {}).get('create_chapters', False) is True:
                p = Processed(title=media.title,
                              type=media.TYPE,
                              ffmpeg_end=ffmpeg_end,
                              ffmpeg_end_str=to_time(ffmpeg_end),
                              credits_start=credits_start,
                              credits_start_str=to_time(credits_start),
                              credits_end=credits_end,
                              credits_end_str=to_time(credits_end),
                              duration=media.duration,
                              ratingKey=media.ratingKey,
                              prettyname=media._prettyfilename(),
                              updatedAt=media.updatedAt,
                              location=location
                              )
                se.add(p)
                LOG.debug('Added %s to media.db', name)

            if CONFIG['movie']['create_chapters'] and media.TYPE == 'movie':
                edl.write_chapters_to_file(check_file_access(media), edl.db_to_edl(p))
            elif CONFIG['tv']['create_chapters'] and media.TYPE == 'episode':
                edl.write_chapters_to_file(check_file_access(media), edl.db_to_edl(p))

        #if media.TYPE == 'episode':
        #    try:
                # since it will check every ep if will download hashes from every ep. We might get
                # away with just checking 2-4 eps. Should this be a config option?
                # we could checkfor grandparentkey and see if we have the required amount
        #        se.query(Images).filter_by(ratingKey=media.ratingKey).one()
        #    except NoResultFound:
        #        add_images = True

    # if media.TYPE == 'episode' and CONFIG.get('hashing').get('check_frames') is True and add_images:
    #    img_hashes = []
        # Check this later TODO
        # for imghash, _, pos in hash_file(check_file_access(media)):  # Add config option of get frames ever n.
        #    img = Images(ratingKey=media.ratingKey,
        #                 hex=str(imghash),
        #                 hash=imghash.hash.tostring(),
        #                 grandparentRatingKey=media.grandparentRatingKey,
        #                 offset=pos,
        #                 time=to_time(pos / 1000))
        #    img_hashes.append(img)

        #with session_scope() as ssee:
        #    ssee.add_all(img_hashes)



@click.group(help='CLI tool that monitors pms and jumps the client to after the theme.')
@click.option('--debug', '-d', default=False, is_flag=True, help='Add debug logging.')
@click.option('--username', '-u', default=None, help='Your plex username')
@click.option('--password', '-p', default=None, help='Your plex password')
@click.option('--servername', '-s', default=None, help='The server you want to monitor.')
@click.option('--url', default=None, help='url to the server you want to monitor')
@click.option('--token', '-t', default=None, help='plex-x-token')
@click.option('--config', '-c', default=None, help='Path to config file.')
@click.option('--verify_ssl', '-vs', default=False, is_flag=True, help='Enable this to allow insecure connections to PMS')
@click.option('--default_folder', '-df', default=None, help='Override for the default folder, typically used by dockers.')
@click.option('--nice', '-n', default=None, type=int, help='Set niceness of the process.')
def cli(debug, username, password, servername, url, token, config, verify_ssl, default_folder, nice):  # pragma: no cover
    """ Entry point for the CLI."""
    global PMS
    global CONFIG

    # Remember to update the subcommands in __init__ if sub commands are added.
    # Default folder is handled in fake_main as we need to modify
    # the variables before import plex.py, its just listed here for the help
    # message etc.

    if nice:
        try:
            os.nice(nice)
        except AttributeError:
            try:
                import psutil
                # Lets keep this for now as this shit keeps
                # hogging my gaming rig.
                p = psutil.Process(os.getpid())
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            except ImportError:
                LOG.debug('psutil is required to set nice on windows')
        except OSError:
            pass

    if config and os.path.isfile(config):
        CONFIG = read_or_make(config)

    url = url or CONFIG['server'].get('url')
    token = token or CONFIG['server'].get('token')
    verify_ssl = verify_ssl or CONFIG['server'].get('verify_ssl')

    if url and token or username and password:

        PMS = get_pms(url=url, token=token,
                      username=username,
                      password=password,
                      servername=servername,
                      verify_ssl=verify_ssl)


@cli.command()
@click.option('-cn', '--client_name', default=None)
@click.option('-sd', '--skip_done', default=False, is_flag=True)
def check_db(client_name, skip_done):  # pragma: no cover
    """Do a manual check of the db. This will start playback on a client and seek the video file where we have found
       theme start/end and ffmpeg_end. You will be asked if its a correct match, press y or set the correct time in
       mm:ss format.

       Args:
            client_name (None, str): Name of the client you want to use (watch)
            skip_done (bool): Skip episodes that already exist in the db.

       Returns:
            None
    """
    if client_name is None:
        client = choose('Select what client to use', PMS.clients(), 'title')
        if len(client):
            client = client[0]
        else:
            click.echo('No client to check with.. Aborting')
            return
    else:
        client = PMS.client(client_name).connect()

    client.proxyThroughServer()

    with session_scope() as se:
        items = se.query(Processed).all()
        click.echo('')

        for item in sorted(items, key=lambda k: k.ratingKey):

            click.echo('%s %s' % (click.style('Checking', fg='white'),
                                  click.style(item.prettyname, bold=True, fg='green')))
            click.echo('theme_start %s theme_end %s ffmpeg_end %s' % (item.theme_start,
                                                                      item.theme_end_str,
                                                                      item.ffmpeg_end))
            click.echo('*%s*' % ('-' * 80))
            click.echo('')

            media = PMS.fetchItem(item.ratingKey)

            if item.theme_start == -1 or item.theme_end == -1:
                click.echo('Exists in the db but the start of the theme was not found.'
                           ' Check the audio file and run it again. Use cmd manually_correct_theme')

            if item.theme_end != -1 and item.type == "episode":

                if (not skip_done and item.correct_theme_start) or not item.correct_theme_start:

                    click.echo('Found theme_start at %s %s theme_end %s %s' % (item.theme_start,
                               item.theme_start_str, item.theme_end, item.theme_end_str))

                    client.playMedia(media, offset=item.theme_start * 1000)
                    time.sleep(1)

                    start_match = click.prompt('Was theme_start at %s correct? [y or MM:SS]' % item.theme_start_str)
                    if start_match:
                        if start_match in ['y', 'yes']:
                            item.correct_theme_start = item.theme_start
                        else:
                            item.correct_theme_start = to_sec(start_match)

                if (not skip_done and item.correct_theme_end) or not item.correct_theme_end:

                    client.playMedia(media, offset=item.theme_end * 1000)
                    end_match = click.prompt('Was theme_end at %s correct? [y or MM:SS]' % item.theme_end_str)
                    if end_match:
                        if end_match in ['y', 'yes']:
                            item.correct_theme_end = item.theme_end
                        else:
                            item.correct_theme_end = to_sec(end_match)

            if item.ffmpeg_end:
                if (not skip_done and item.correct_ffmpeg) or not item.correct_ffmpeg:
                    click.echo('Found ffmpeg_end at sec %s time %s' % (item.ffmpeg_end, item.ffmpeg_end_str))
                    if item.ffmpeg_end > 30:
                        j = item.ffmpeg_end - 20
                    else:
                        j = item.ffmpeg_end

                    client.playMedia(media, offset=j * 1000)
                    time.sleep(1)

                    match = click.prompt('Was ffmpeg_end at %s correct? [y or MM:SS]' % item.ffmpeg_end_str)

                    if match:
                        if match.lower() in ['y', 'yes']:
                            item.correct_ffmpeg = item.ffmpeg_end
                        else:
                            item.correct_ffmpeg = to_sec(match)

            # This needs to be tested manually.
            if item.credits_start and item.credits_start != 1:
                if (not skip_done and item.correct_credits_start) or not item.correct_credits_start:
                    click.echo('Found credits start as sec %s time %s' % (item.credits_start, item.credits_start_str))
                    client.playMedia(media, offset=item.credits_start - 10)
                    time.sleep(1)

                    match = click.prompt('Did the credits start at %s correct? [y or MM:SS]' % item.credits_start_str)

                    if match:
                        if match.lower() in ['y', 'yes']:
                            item.correct_credits_start = item.credits_start
                        else:
                            item.correct_credits_start = to_sec(match)

            click.clear()

            # Commit this shit after each loop.
            if se.dirty:
                se.commit()

        click.echo('Done')


@cli.command()
@click.option('-n', '--name', help='Search for a show.', default=None)
@click.option('-s', '--sample', default=0, help='Process N episodes of all shows.', type=int)
@click.option('-t', '--threads', help='Threads to uses', default=1, type=int)
@click.option('-sd', '--skip_done', help='Skip media items that exist in the db', default=True, is_flag=True)
def process(name, sample, threads, skip_done):
    """Manual process some/all eps.
       You will asked for what you want to process

       Args:
            name (None): Pass a name of a show you want to process
            sample (int): process x eps for all shows.
            threads (int): How many thread to use
            skip_done(bool): Should we skip stuff that is processed.

       Return:
            None

    """
    global HT
    all_items = []

    if name:
        medias = find_all_movies_shows()
        medias = [s for s in medias if s.title.lower().startswith(name.lower())]
        medias = choose('Select what item to process', medias, 'title')

        for media in medias:
            if media.TYPE == 'show':
                eps = media.episodes()
                eps = choose('Select episodes', eps, lambda x: '%s %s' % (x._prettyfilename(), x.title))
                all_items += eps
            else:
                all_items.append(media)

    if sample:
        def lol(i):
            if i.TYPE == 'show':
                x = i.episodes()[:sample]
                return all_items.extend(x)
            else:
                return all_items.append(i)

        find_all_movies_shows(lol)

    if skip_done:
        # Now there must be a better way..
        with session_scope() as se:
            items = se.query(Processed).all()
            for item in items:
                for ep in all_items:
                    if ep.ratingKey == item.ratingKey:
                        click.secho("Removing %s at it's already is processed" % item.prettyname, fg='red')
                        all_items.remove(ep)

    HT = get_hashtable()

    def prot(item):
        try:
            process_to_db(item)
        except Exception as e:
            logging.error(e, exc_info=True)

    if all_items:
        p = Pool(threads)

        # Download all the themes first, skip the ones that we already have..
        gr = set([i.grandparentRatingKey for i in all_items if i.TYPE == 'episode']) - set(HT.get_themes().keys())
        LOG.debug('Downloading theme for %s shows this might take a while..', len(gr))
        if len(gr):
            sh = p.map(PMS.fetchItem, gr)
            try:
                p.map(HT.has_theme, sh)
            except KeyboardInterrupt:
                pass

        try:
            p.map(prot, all_items)
        except KeyboardInterrupt:
            p.terminate()


@cli.command()
@click.argument('name', type=click.Path(exists=True))
@click.option('-trim', default=600, help='Only get the first x seconds', type=int)
@click.option('-dev', default=7, help='Accepted deviation between audio and video', type=int)
@click.option('-da', default=0.5, type=float)
@click.option('-dv', default=0.5, type=float)
@click.option('-pix_th', default=0.10, type=float)
@click.option('-au_db', default=50, type=int)
def ffmpeg_process(name, trim, dev, da, dv, pix_th, au_db):  # pragma: no cover
    """Simple manual test for ffmpeg_process with knobs to turn."""

    n = find_offset_ffmpeg(name, trim=trim, dev=dev, duration_audio=da,
                           duration_video=dv, pix_th=pix_th, au_db=au_db)
    click.echo(n)
    return n


@cli.command()
@click.option('-t', default='scene marker', type=click.Choice(['cut', 'scene marker', 'mute', 'commercial break']),
              help='What type of edl is this')
@click.option('-sp', '--save_path', default=None)
def create_edl_from_db(t, save_path):  # pragma: no cover
    with session_scope() as se:
        db_items = se.query(Processed).all()
        for item in db_items:
            # Maybe remove this later?
            if save_path:
                loc = edl.create_edl_path(os.path.join(save_path, os.path.basename(item.location)))
            else:
                loc = item.location  # handle remapping?

            try:
                t = edl.write_edl(loc, edl.db_to_edl(item, edl.TYPES[t]))
                click.echo('Wrote %s' % t)
            except:
                LOG.exception('Failed to write edl.')


@cli.command()
@click.option('--name', default=None)
@click.option('--dur', default=600)
@click.option('--sample', default=None, type=int)
def add_hash_frame(name, dur, sample):  # pragma: no cover
    """This will hash the episodes. We can later use this info to extract intro etc."""
    all_items = []
    p = Pool(4)
    result = []

    @log_exception
    def to_db(media):
        """ Just we can do the processing in a thread pool"""
        imgz = []
        for imghash, _, pos in hash_file(check_file_access(media), frame_range=False, end=dur):
            img = Images(ratingKey=media.ratingKey,
                         hex=str(imghash),
                         hash=imghash.hash.tostring(),
                         grandparentRatingKey=media.grandparentRatingKey,
                         parentRatingKey=media.parentRatingKey,
                         offset=pos,
                         time=to_time(pos / 1000))
            imgz.append(img)
        return imgz

    medias = find_all_movies_shows()
    if sample is None:
        if name:
            medias = [s for s in medias if s.title.lower().startswith(name.lower())]
        else:
            medias = [s for s in medias if s.TYPE == 'show']

        medias = choose('Select what item to process', medias, 'title')

        for media in medias:
            if media.TYPE == 'show':
                eps = media.episodes()
                eps = choose('Select episodes', eps, lambda x: '%s %s' % (x._prettyfilename(), x.title))
                all_items += eps
    else:
        for show in [s for s in medias if s.TYPE == 'show']:
            for season in show.seasons():
                try:
                    all_items.extend(season.episodes()[:sample])
                except:  # pragma: no cover
                    pass
    try:
        # This might take a while so lets make it easy to interupt.
        LOG.debug('Started to process %s items to the images table', len(all_items))
        result = p.map(to_db, all_items, 1)
    except KeyboardInterrupt:
        pass

    # Flatten the list.
    result = list(itertools.chain(*result))

    with session_scope() as ssee:
        ssee.add_all(result)


@cli.command()
@click.option('--name', default=None)
@click.option('--conf', default=0.7, type=float)
def test_hashing_visual(name, conf):  # pragma: no cover
    from bw_plex.tools import visulize_intro_from_hashes

    medias = find_all_movies_shows()
    all_items = []
    if name:
        medias = [s for s in medias if s.title.lower().startswith(name.lower())]
    else:
        medias = [s for s in medias if s.TYPE == 'show']

    medias = choose('Select what item to process', medias, 'title')

    for media in medias:
        if media.TYPE == 'show':
            eps = media.episodes()
            eps = choose('Select episodes', eps, lambda x: '%s %s' % (x._prettyfilename(), x.title))
            all_items += eps

    assert len(all_items) == 1, 'visulize_intro_from_hashes only works on one file at the time'

    def find_intro_from_hexes_in_db(item):
        d = defaultdict(set)
        new_hex = []
        stuff = []
        with session_scope() as se:
            eps = se.execute('select count(distinct ratingKey) from images where grandparentRatingKey = %s and parentRatingKey = %s' % (item.grandparentRatingKey, item.parentRatingKey))
            eps = list(eps)[0][0]
            LOG.debug('%s season %s has %s episodes', item.grandparentTitle, item.parentIndex, eps)
            stuff = se.execute('select * from images where grandparentRatingKey = %s and parentRatingKey = %s' % (item.grandparentRatingKey, item.parentRatingKey))
            stuff = list(stuff)

        for s in stuff:
            d[s.hex].add(s.ratingKey)

        for k, v in d.items():
            if len(v) >= float(eps * float(conf)):
                new_hex.append(k)

        LOG.debug('Found %s hashes that are in %s percent of the episodes (%s) in this season', len(new_hex), eps, 100 * conf)
        return new_hex

    hexes = find_intro_from_hexes_in_db(all_items[0])

    visulize_intro_from_hashes(check_file_access(all_items[0]), hexes)


@cli.command()
@click.argument('fp')
@click.option('-t', type=click.Choice(['start', 'end']))
@click.option('--tvdbid')
@click.option('--timestamp', default=None)
@click.option('--gui', default=True)
def add_ref_frame(fp, t, tvdbid, timestamp, gui):  # pragma: no cover
    import cv2

    if gui:
        from bw_plex.tools import play
        play(fp, key=tvdbid)
        return

    if fp.endswith(('.mp4', '.mkv', '.avi')) and timestamp:

        cap = cv2.VideoCapture(fp)
        ms = to_ms(timestamp)
        cap.set(cv2.CAP_PROP_POS_MSEC, ms)
        _, frame = cap.read()
    else:
        # So its a image...
        frame = fp

    frames_hash = create_imghash(frame)
    # DUnno if this still is correct. using frames would be better.
    frames_hex = ''.join(hex(i) for i in frames_hash.flatten()) # fixme?

    with session_scope() as se:
        try:
            se.query(Reference_Frame).filter_by(hex=frames_hex).one()
            click.echo('This frame already exist in the db')
        except NoResultFound:

            frm = Reference_Frame(hex=frames_hex,
                                  type=t,
                                  tvdbid=tvdbid)
            se.add(frm)
            LOG.debug('Added %s to Reference_Frame table hex %s tvdbid %s', fp, frames_hex, tvdbid)


@cli.command()
@click.option('-fp', default=None, help='where to create the config file.')
def create_config(fp=None):  # pragma: no cover
    """Create a config file.

       Args:
            fp(str): Where to create the config file. If omitted it will be written
                     to the default location


       Returns:
            filepath to config.ini
    """
    if fp is None:
        fp = INI_FILE

    conf_file = read_or_make(fp).filename
    click.echo('Wrote configfile to %s' % conf_file)
    return conf_file


@cli.command()
@click.argument('name')
@click.argument('url')
@click.option('-t', '--type', default=None, type=click.Choice(['manual', 'tvtunes', 'plex', 'youtube', 'all']))
@click.option('-rk', help='Add rating key', default='auto')
@click.option('-jt', '--just_theme', default=False, is_flag=True)
@click.option('-rot', '--remove_old_theme', default=False, is_flag=True)
def manually_correct_theme(name, url, type, rk, just_theme, remove_old_theme):  # pragma: no cover
    """Set the correct fingerprint of the show in the hashes.db and
       process the eps of that show in the db against the new theme fingerprint.

       Args:
            name (str): name of the show
            url (str): the youtube/tvtunes url or filepath to the correct theme.
            type (str): What source to use for themes.
            rk (str): ratingkey of that show. Pass auto if your lazy.
            just_theme (bool): just add the theme song not reprocess stuff.
            remove_old_theme (bool): Removes all the old themes of this show

       Returns:
            None
    """
    global HT
    HT = get_hashtable()

    # Assist for the lazy bastards..
    if rk == 'auto':
        items = PMS.search(name)
        items = [i for i in items if i and i.TYPE == 'show']
        items = choose('Select correct show', items, lambda x: '%s %s' % (x.title, x.TYPE))
        if items:
            rk = items[0].ratingKey

    if remove_old_theme:
        themes = HT.get_theme(items[0])
        for th in themes:
            LOG.debug('Removing %s from the hashtable', th)
            HT.remove(th)

    # Download the themes depending on the manual option or config file.
    download_theme(items[0], HT, theme_source=type, url=url)
    to_pp = []

    if just_theme:
        return

    if rk:
        with session_scope() as se:
            # Find all episodes of this show.
            item = se.query(Processed).filter_by(grandparentRatingKey=rk)

            for i in item:
                to_pp.append(PMS.fetchItem(i.ratingKey))
                # Prob should have used edit, but we do this so we can use process_to_db.
                se.delete(i)

        for media in to_pp:
            process_to_db(media)


@cli.command()
@click.option('-t', '--threads', help='How many thread to use', type=int, default=1)
@click.option('-d', '--directory', help='What directory you want to scan for themes.', default=None)
def add_theme_to_hashtable(threads, directory):
    """ Create a hashtable from the themes.

        Args:
            theads (int): How many threads to use.
            directory (None, str): If you don't pass a directory will select the default one

        Returns:
            None

    """
    from bw_plex.audfprint.audfprint import multiproc_add
    global HT
    HT = get_hashtable()

    a = analyzer()
    all_files = []

    for root, _, files in os.walk(directory or THEMES):
        for f in files:
            fp = os.path.join(root, f)
            # We need to check this since when themes are downloaded
            # They sometimes get a 0b files.
            if os.path.exists(fp) and os.path.getsize(fp):
                all_files.append(fp)

    def report(s):  # this shitty reporter they want sucks balls..
        pass  # print(s)

    LOG.debug('Creating hashtable, this might take a while.. adding %s files', len(all_files))
    multiproc_add(a, HT, iter(all_files), report, threads)
    if HT and HT.dirty:
        HT.save(FP_HASHES)


@cli.command()
@click.option('-f', '--format', type=click.Choice(['txt', 'html', 'json', 'yaml', 'dbf', 'csv']), default='txt')
@click.option('-fp', '--save_path', default=os.getcwd())
@click.option('-wf', '--write_file', default=False, is_flag=True)
@click.option('-sh', '--show_html', default=True, is_flag=True)
def export_db(format, save_path, write_file, show_html):
    """Export the db to some other format."""
    import tablib

    keys = [k for k in Processed.__dict__.keys() if not k.startswith('_')]
    data = []

    with session_scope() as se:
        db_items = se.query(Processed).all()

        for item in db_items:
            data.append(item._to_tuple(keys=keys))

    td = tablib.Dataset(*data, headers=keys)
    if format != 'txt':
        t = td.export(format)
    else:
        t = td

    if write_file:
        fullpath = os.path.join(save_path, '%s.%s' % (Processed.__name__, format))
        with open(fullpath, 'wb') as f:
            f.write(t.encode('utf-8'))
        click.echo('Wrote file to %s' % fullpath)

    else:
        if format == 'html' and show_html:
            tf = tempfile.NamedTemporaryFile(suffix='.%s' % format)
            with tf as f:
                f.write(t.encode('utf-8'))
                webbrowser.open(tf.name)
                try:
                    while True:
                        time.sleep(10)
                except KeyboardInterrupt:
                    pass
        else:
            click.echo(t)


def check_file_access(m):  # pragma: no cover
    """Check if we can reach the file directly
       or if we have to download it via PMS.

       Args:
            m (plexapi.video.Episode)

       Return:
            filepath or http to the file.

    """
    LOG.debug('Checking if we can reach %s directly', m._prettyfilename())

    files = list(m.iterParts())
    # Now we could get the "wrong" file here.
    # If the user has duplications we might return the wrong file
    # CBA with fixing this as it requires to much work :P
    # And the use case is rather slim, you should never have dupes.
    # If the user has they can remove them using plex-cli.
    for file in files:
        if os.path.exists(file.file):
            LOG.debug('Found %s directly', file.file)
            return file.file
        elif CONFIG.get('remaps', []):
            for key, value in CONFIG.get('remaps').items():
                fp = file.file.replace(key, value)
                if os.path.exists(fp):
                    LOG.debug('Found %s using path remaps', fp)
                    return fp
    else:
        LOG.warning('Downloading from pms..')
        try:
            # for plexapi 3.0.6 and above.
            return PMS.url('%s?download=1' % files[0].key, includeToken=True)
        except TypeError:
            return PMS.url('%s?download=1' % files[0].key)

    LOG.debug('this should not be in log')


@log_exception
def client_action(offset=None, sessionkey=None, action='jump'):  # pragma: no cover
    """Seek the client to the offset.

       Args:
            offset(int): Default None
            sessionkey(int): So we made sure we control the correct client.

       Returns:
            None
    """
    global JUMP_LIST, CREDITS_LIST
    # Some of this stuff take so time.
    # so we use this to try fix the offset
    # as this is given to client_action as a parameter.
    called = time.time()
    LOG.info('Called client_action with %s %s %s %s', offset, to_time(offset), sessionkey, action)

    @log_exception
    def proxy_on_fail(func):

        @wraps(func)
        def inner(*args, **kwargs):
            try:
                if args:
                    return func(*args)
                return func()
            except (plexapi.exceptions.BadRequest, requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout, requests.exceptions.TooManyRedirects,
                    requests.exceptions.HTTPError):
                try:
                    LOG.info('Failed to reach the client directly, trying via server.')
                    correct_client.proxyThroughServer()
                    return func()
                except:  # pragma: no cover
                    correct_client.proxyThroughServer(value=False)
                    raise

        return inner

    if offset == -1:
        return

    conf_clients = CONFIG.get('general', {}).get('clients', [])
    conf_users = CONFIG.get('general', {}).get('users', [])
    correct_client = None

    clients = PMS.clients()
    for media in PMS.sessions():
        # Find the client.. This client does not have the correct address
        # or 'protocolCapabilities' so we have to get the correct one.
        # or we can proxy thru the server..
        LOG.info('sessionkey %s media_sessionkey %s', sessionkey, media.sessionKey)
        if sessionkey and int(sessionkey) == media.sessionKey:
            client = media.players[0]
            user = media.usernames[0]
            LOG.info('client %s %s', client.title, (media.viewOffset / 1000))

            # Check that this client is allowed.
            if conf_clients and client.title not in conf_clients:
                LOG.info('Client %s is not whitelisted', client.title)
                return

            # Check that this user is allowed.
            if conf_users and user not in conf_users:
                LOG.info('User %s is not whitelisted', user)
                return

            if client.platform == 'Chromecast' and client.local:
                LOG.debug('The client is a chromecast and on the local network.')
                correct_client = client
                # getting the player can take some time, in my shallow tests
                # it takes like 5 sec.
                pc, cast = log_exception(get_chromecast_player)(client.address, 'Chromecast')
                if pc and cast:
                    # Block until the cromecast is ready.
                    cast.wait()
                    correct_client.pc = pc
                else:
                    LOG.debug('The client was a chromecast but we couldnt get a plex controller '
                              'and/or the chromecast.')
                    return
            else:
                LOG.info('Checking if we cant find the correct client')
                for c in clients:
                    LOG.info('%s %s', c.machineIdentifier, client.machineIdentifier)
                    # So we got the correct client..
                    if c.machineIdentifier == client.machineIdentifier:
                        # Plex web sometimes add loopback..
                        if '127.0.0.1' in c._baseurl:
                            c._baseurl = c._baseurl.replace('127.0.0.1', client.address)
                        correct_client = c
                        break
                else:
                    LOG.debug('We couldnt match the client. Trying a hail marry.')
                    correct_client = client

            if correct_client and correct_client.platform != 'Chromecast':
                try:
                    # Browsers seems to fail to connect so many times
                    # lets just stop trying and proxy the commands via the server.
                    if correct_client._baseurl and correct_client.product != "Plex Web":
                        LOG.info('Connectiong to %s', correct_client.title)
                        correct_client.connect()
                    else:
                        # Some clients might not have a _baseurl like the lg
                        # lets try, to proxy this but i dont have a lg to test with.
                        LOG.debug('Client hasnt a _baseurl or is a browser, enabling proxyThroughServer')
                        correct_client.proxyThroughServer()
                except (requests.exceptions.ConnectionError, requests.exceptions.InvalidURL):
                    # Lets just skip this for now and some "clients"
                    # might be controllable but not support the /resources endpoint
                    # https://github.com/Hellowlol/bw_plex/issues/74
                    # return
                    LOG.exception('Cant connect to %s', client.title)

            if action != 'stop':
                if ignore_ratingkey(media, CONFIG['general'].get('ignore_intro_ratingkeys')):
                    LOG.info('Didnt send seek command this show, season or episode is ignored')
                    return

                # PMP seems to be really picky about timeline calls, if we dont
                # it returns 406 errors after 90 sec.
                if correct_client.product == 'Plex Media Player':
                    correct_client.sendCommand('timeline/poll', wait=0)

                now = time.time()
                calculated_offset = int(now - called + offset)
                LOG.debug('calculated_offset %s %s' % (calculated_offset, calculated_offset / 1000))

                if correct_client.platform != 'Chromecast':
                    proxy_on_fail(correct_client.seekTo)(calculated_offset * 1000)
                else:
                    correct_client.pc.seek(calculated_offset)

                LOG.info('Seeked %s %s to %s %s %s', user, client.title,
                         calculated_offset, to_time(calculated_offset), media._prettyfilename())

                # We are done, disconnect
                if correct_client.platform == 'Chromecast':
                    correct_client.pc.disconnect(timeout=10)

            else:
                if not ignore_ratingkey(media, CONFIG['general'].get('ignore_outro_ratingkeys')):
                    if client.product != 'Chromecast':
                        proxy_on_fail(correct_client.stop)()
                    else:
                        correct_client.pc.stop()

                    LOG.debug('Stopped playback on %s and marked %s as watched.', client.title, media._prettyfilename())

                    # Check if we just start the next ep instantly.
                    if CONFIG['tv'].get('check_credits_start_next_ep') is True:
                        nxt = find_next(media)  # This is always false for movies.
                        if nxt:
                            if correct_client.platform != 'Chromecast':
                                LOG.info('Start playback on %s with %s', user, nxt._prettyfilename())
                                proxy_on_fail(correct_client.playMedia)(nxt)
                            else:
                                correct_client.pc.play_media(nxt)
                                # this does not work the playback does not start, need to figure
                                # out that shit.
                                # so the shit is figured out, needs a new chromecast controller.
                                # See the chromecast branch.

                    # We are done, disconnect
                    if correct_client.platform == 'Chromecast':
                        correct_client.pc.disconnect(timeout=10)


@log_exception
def task(item, sessionkey):
    """Main func for processing a episode.

       Args:
            item(str): a episode's ratingkey
            sessionkey(str): streams sessionkey

       Returns:
            None
    """
    global HT
    media = PMS.fetchItem(int(item))
    LOG.debug('Found %s', media._prettyfilename())
    if media.TYPE not in ('episode', 'show', 'movie'):  # pragma: no cover
        return

    if media.TYPE == 'episode':
        LOG.debug('Download the first 10 minutes of %s as .wav', media._prettyfilename())
        vid = convert_and_trim(check_file_access(media), fs=11025,
                               trim=CONFIG['tv'].get('check_for_theme_sec', 600))

        process_to_db(media, vid=vid)

        try:
            os.remove(vid)
            LOG.debug('Deleted %s', vid)
        except IOError:  # pragma: no cover
            LOG.exception('Failed to delete %s', vid)

    elif media.TYPE == 'movie':
        process_to_db(media)

    try:
        IN_PROG.remove(item)
    except ValueError:  # pragma: no cover
        LOG.debug('Failed to remove %s from IN_PROG', item)

    nxt = find_next(media)
    if nxt:
        process_to_db(nxt)


def best_time(item):
    """Find the best time in the db."""
    if item.type == 'episode' and item.correct_theme_end and item.correct_theme_end != 1:
        sec = item.correct_theme_end

    elif item.correct_ffmpeg and item.correct_ffmpeg != 1:
        sec = item.correct_ffmpeg

    elif item.type == 'episode' and item.theme_end and item.theme_end != -1:
        sec = item.theme_end

    elif item.ffmpeg_end and item.ffmpeg_end != -1:
        sec = item.ffmpeg_end

    else:
        sec = -1

    return sec


def jump(item, sessionkey, sec=None, action=None):  # pragma: no cover

    if sec is None:
        sec = best_time(item)

    if action and sessionkey not in CREDITS_LIST:
        CREDITS_LIST.append(sessionkey)
        POOL.apply_async(client_action, args=(sec, sessionkey, action))
        return

    if action is None and sessionkey not in JUMP_LIST:
        LOG.debug('Called jump with %s %s %s %s', item.prettyname,
                  sessionkey, sec, action)
        JUMP_LIST.append(sessionkey)
        POOL.apply_async(client_action, args=(sec, sessionkey, action))


def check(data):
    if data.get('type') == 'playing' and data.get(
            'PlaySessionStateNotification'):

        sess = data.get('PlaySessionStateNotification')[0]

        if sess.get('state') != 'playing':
            return

        ratingkey = int(sess.get('ratingKey'))
        sessionkey = int(sess.get('sessionKey'))
        progress = sess.get('viewOffset', 0) / 1000  # converted to sec.
        mode = CONFIG['general'].get('mode', 'skip_only_theme')
        no_wait_tick = CONFIG['general'].get('no_wait_tick', 5)
        # Let's try to not wait for the next tick.
        fake_progress = progress + no_wait_tick

        with session_scope() as se:
            try:
                item = se.query(Processed).filter_by(ratingKey=ratingkey).one()

                if item:
                    bt = best_time(item)
                    LOG.debug('Found %s theme start %s, theme end %s, ffmpeg_end %s progress %s fake_progress %s'
                              ' best_time %s credits_start %s credits_end %s', item.prettyname,
                              item.theme_start_str, item.theme_end_str, item.ffmpeg_end_str,
                              to_time(progress), to_time(fake_progress), to_time(bt), item.credits_start_str, item.credits_end_str)

                    if (item.type == 'episode' and CONFIG['tv'].get('check_credits') is True and
                        CONFIG['tv'].get('check_credits_action') in ('stop', 'seek') or
                        item.type == 'movie' and CONFIG['movie'].get('check_credits') is True and
                        CONFIG['movie'].get('check_credits_action') == 'stop'):

                        # todo check for correct credits too
                        if item.credits_start and item.credits_start != -1 and fake_progress >= item.credits_start:
                            LOG.debug('We found the start of the credits.')

                            if item.type == 'episode':
                                act = CONFIG['tv'].get('check_credits_action')
                                if act == 'seek':
                                    # Seek until the end so the playback for next time start
                                    # This is only to get the countdown in the client
                                    act_to_time = item.duration / 1000
                                else:
                                    act_to_time = item.credits_start + CONFIG['tv'].get('credits_delay', 0)
                            else:
                                act = CONFIG['movie'].get('check_credits_action')
                                act_to_time = item.credits_start + CONFIG['movie'].get('credits_delay', 0)

                            return jump(item, sessionkey, act_to_time, action=act)

                    # If recap is detected just instantly skip to intro end.
                    # Now this can failed is there is: recap, new episode stuff, intro, new episode stuff
                    # So thats why skip_only_theme is default as its the safest option.
                    if (mode == 'skip_if_recap' and item.type == 'episode' and item.has_recap is True and bt != -1):
                        return jump(item, sessionkey, bt)

                    # This mode will allow playback until the theme starts so it should be faster then skip_if_recap.
                    if mode == 'skip_only_theme':
                        # For manual corrected themes..
                        if item.type == 'episode' and item.correct_theme_end and item.correct_theme_start:
                            if fake_progress > item.correct_theme_start and fake_progress < item.correct_theme_end:
                                LOG.debug('%s is in the correct time range correct_theme_end', item.prettyname)
                                return jump(item, sessionkey, item.correct_theme_end)

                        elif item.type == 'episode' and item.theme_end and item.theme_start:
                            if fake_progress > item.theme_start and fake_progress < item.theme_end:
                                LOG.debug('%s is in the correct time range theme_end', item.prettyname)
                                return jump(item, sessionkey, item.theme_end)

            except NoResultFound:
                if ratingkey not in IN_PROG:
                    IN_PROG.append(ratingkey)
                    LOG.debug('Failed to find ratingkey %s in the db', ratingkey)
                    ret = POOL.apply_async(task, args=(ratingkey, sessionkey))
                    return ret

    elif data.get('type') == 'timeline':
        timeline = data.get('TimelineEntry')[0]
        state = timeline.get('state')
        ratingkey = timeline.get('itemID')
        title = timeline.get('title')
        metadata_type = timeline.get('type')
        identifier = timeline.get('identifier')
        metadata_state = timeline.get('metadataState')

        if (metadata_type in (1, 4) and state == 0 and
            metadata_state == 'created' and identifier == 'com.plexapp.plugins.library'):
            LOG.debug('%s was added to %s', title, PMS.friendlyName)

            # Youtubedl can fail if we batch add loads of eps at the same time if there is no
            # theme.
            if (metadata_type == 1 and not CONFIG['movie'].get('process_recently_added') or
                metadata_type == 4 and not CONFIG['tv'].get('process_recently_added')):
                LOG.debug("Didn't start to process %s is process_recently_added is disabled", title)
                return

            if ratingkey not in IN_PROG:
                IN_PROG.append(ratingkey)
                try:
                    ep = PMS.fetchItem(int(ratingkey))
                except plexapi.exceptions.BadRequest:
                    # See https://github.com/Hellowlol/bw_plex/issues/114
                    LOG.exception("Didn't start to process %s", ratingkey)
                    return
                ret = POOL.apply_async(process_to_db, args=(ep,))
                return ret

        elif (metadata_type in (1, 4) and state == 9 and
              metadata_state == 'deleted'):

            if (metadata_type == 1 and not CONFIG['movie'].get('process_deleted') or
                metadata_type == 4 and not CONFIG['tv'].get('process_deleted')):
                LOG.debug("Didn't start to process %s is process_deleted is disabled for", title)
                return

            with session_scope() as se:
                try:
                    item = se.query(Processed).filter_by(ratingKey=ratingkey).one()
                    se.delete(item)
                    LOG.debug('%s was deleted from %s and from media.db', title, PMS.friendlyName)
                except NoResultFound:
                    LOG.debug('%s was deleted from %s', title, PMS.friendlyName)


@cli.command()
@click.argument('-f', type=click.Path(exists=True))
def match(f):  # pragma: no cover
    """Manual match for a file. This is useful for testing we finds the correct start and
       end time."""
    global HT
    HT = get_hashtable()
    x = find_theme_start_end(f, HT)
    click.echo(x)


@cli.command()
def watch():  # pragma: no cover
    """Start watching the server for stuff to do."""
    global HT
    HT = get_hashtable()
    click.echo('Watching for media on %s' % PMS.friendlyName)

    ws_url = PMS.url('/:/websockets/notifications', includeToken=True).replace('http', 'ws').replace('https', 'wss')
    ws = WebSocket(ws_url)
    for event in persist(ws, ping_rate=0, exit_event=EVENT):
        try:
            if event.name == 'text':
                data = event.json
                if 'NotificationContainer' in data:
                    check(data['NotificationContainer'])

            elif event.name not in ('text', 'binary', 'poll', 'ping', 'pong', 'connecting', 'connected'):
                LOG.debug('ws event %s', event)

        except KeyboardInterrupt:
            click.echo('Aborting')


@cli.command()
@click.argument('name')
def test_a_movie(name):  # pragma: no cover
    result = PMS.search(name)

    if result:
        process_to_db(result[0])


@cli.command()
@click.argument('showname')
@click.argument('season', type=int)
@click.argument('episode', type=int)
@click.argument('type', default='theme')
@click.argument('start')
@click.argument('end')
def set_manual_theme_time(showname, season, episode, type, start, end):  # pragma: no cover
    """Set a manual start and end time for a theme.

       Args:
           showname(str): name of the show you want to find
           season(int): season number fx 1
           episode(int): episode number 1
           type(str): theme, credit # Still TODO Stuff for credits
           start(int, str): This can be in seconds or MM:SS format
           start(int, str): This can be in seconds or MM:SS format

       Returns:
            None
    """
    LOG.debug('Trying to set manual time')
    result = PMS.search(showname)

    if result:

        items = choose('Select show', result, 'title')
        show = items[0]
        ep = show.episode(season=season, episode=episode)

        if ep:
            with session_scope() as se:
                item = se.query(Processed).filter_by(ratingKey=ep.ratingKey).one()
                start = to_sec(start)
                end = to_sec(end)

                if type == 'ffmpeg':
                    item.correct_ffmpeg = end

                elif type == 'theme':
                    if start:
                        item.correct_time_start = start

                    if end:
                        item.correct_time_end = end
                elif type == 'credits':
                    if start:
                        item.correct_credits_start = start

                    if end:
                        item.correct_credits_end = end

                LOG.debug('Set correct_time %s for %s to start %s end %s',
                          type, ep._prettyfilename(), start, end)


if os.name != 'nt':
    LOG.info('Added signal handler.')
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGHUP, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

else:  # pragma: no cover
    signal.signal(signal.SIGINT, shutdown_handler)


def real_main():
    try:
        cli()
    except:  # pragma: no cover
        raise


if __name__ == '__main__':
    print('You need to use bw_plex or cli.py')
