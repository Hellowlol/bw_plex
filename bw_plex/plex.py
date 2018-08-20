#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import tempfile
import struct
import time
import webbrowser

from functools import wraps

import click
import requests
from sqlalchemy.orm.exc import NoResultFound

from bw_plex import FP_HASHES, CONFIG, THEMES, LOG, INI_FILE, PMS, POOL, Pool
from bw_plex.config import read_or_make
from bw_plex.credits import find_credits
from bw_plex.db import session_scope, Processed
from bw_plex.misc import (analyzer, convert_and_trim, choose, find_next, find_offset_ffmpeg, get_offset_end,
                          get_pms, get_hashtable, has_recap, to_sec, to_time, download_theme, ignore_ratingkey)


IN_PROG = []
JUMP_LIST = []
SHOWS = {}
HT = None

is_64bit = struct.calcsize('P') * 8
if not is_64bit:  # pragma: no cover
    LOG.info('You not using a python 64 bit version.')


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

    # Disable for now.
    # if media.TYPE == 'movie':
    #    return

    # This will download the theme and add it to
    # the hashtable if its missing
    if media.TYPE == 'episode' and theme is None:
        if HT.has_theme(media, add_if_missing=False) is False:
            LOG.debug('downloading theme from process_to_db')
            theme = download_theme(media, HT)

    name = media._prettyfilename()
    LOG.debug('Started to process %s', name)

    if vid is None and media.TYPE == 'episode':
        vid = convert_and_trim(check_file_access(media), fs=11025,
                               trim=CONFIG['tv'].get('check_for_theme_sec', 600))

    # Find the start and the end of the theme in the episode file.
    if end is None and media.TYPE == 'episode':
        start, end = get_offset_end(vid, HT)

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
                              has_recap=recap)

            elif media.TYPE == 'movie':
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
                              updatedAt=media.updatedAt)

            se.add(p)
            LOG.debug('Added %s to media.db', name)


@click.group(help='CLI tool that monitors pms and jumps the client to after the theme.')
@click.option('--debug', '-d', default=False, is_flag=True, help='Add debug logging.')
@click.option('--username', '-u', default=None, help='Your plex username')
@click.option('--password', '-p', default=None, help='Your plex password')
@click.option('--servername', '-s', default=None, help='The server you want to monitor.')
@click.option('--url', default=None, help='url to the server you want to monitor')
@click.option('--token', '-t', default=None, help='plex-x-token')
@click.option('--config', '-c', default=None, help='Path to config file.')
@click.option('--verify_ssl', '-vs', default=None, help='Enable this to allow insecure connections to PMS')
@click.option('--default_folder', '-df', default=None, help='Override for the default folder, typically used by dockers.')
def cli(debug, username, password, servername, url, token, config, verify_ssl, default_folder):
    """ Entry point for the CLI."""
    global PMS
    global CONFIG

    # Remember to update the subcommands in __init__ if sub commands are added.
    # Default folder is handled in fake_main as we need to modify
    # the variables before import plex.py, its just listed here for the help
    # message etc.

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

            if item.theme_end != -1:

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
@click.option('-fp', default=None, help='where to create the config file.')
def create_config(fp=None):
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

    LOG.debug('Creating hashtable, this might take a while..')

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


def check_file_access(m):
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
            LOG.debug('Found %s', file.file)
            return file.file
        else:
            LOG.warning('Downloading from pms..')
            try:
                # for plexapi 3.0.6 and above.
                return PMS.url('%s?download=1' % file.key, includeToken=True)
            except TypeError:
                return PMS.url('%s?download=1' % file.key)


@log_exception
def client_action(offset=None, sessionkey=None, action='jump'):  # pragma: no cover
    """Seek the client to the offset.

       Args:
            offset(int): Default None
            sessionkey(int): So we made sure we control the correct client.

       Returns:
            None
    """
    global JUMP_LIST
    LOG.info('Called client_action with %s %s %s %s', offset, to_time(offset), sessionkey, action)

    def proxy_on_fail(func):
        import plexapi

        @wraps(func)
        def inner():
            try:
                func()
            except plexapi.exceptions.BadRequest:
                try:
                    LOG.info('Failed to reach the client directly, trying via server.')
                    correct_client.proxyThroughServer()
                    func()
                except:  # pragma: no cover
                    correct_client.proxyThroughServer(value=False)
                    raise

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

            # To stop processing. from func task if we have used to much time..
            # This will not work if/when credits etc are added. Need a better way.
            # if offset <= media.viewOffset / 1000:
            #    LOG.debug('Didnt jump because of offset')
            #    return

            for c in clients:
                LOG.info('%s %s' % (c.machineIdentifier, client.machineIdentifier))
                # So we got the correct client..
                if c.machineIdentifier == client.machineIdentifier:
                    # Plex web sometimes add loopback..
                    if '127.0.0.1' in c._baseurl:
                        c._baseurl = c._baseurl.replace('127.0.0.1', client.address)
                    correct_client = c
                    break

            if correct_client:
                try:
                    LOG.info('Connectiong to %s', correct_client.title)
                    correct_client.connect()
                except requests.exceptions.ConnectionError:
                    LOG.exception('Cant connect to %s', client.title)
                    return

                if action != 'stop':
                    if ignore_ratingkey(media, CONFIG['general'].get('ignore_intro_ratingkeys')):
                        LOG.info('Didnt send seek command this show, season or episode is ignored')
                        return

                    # PMP seems to be really picky about timeline calls, if we dont
                    # it returns 406 errors after 90 sec.
                    if correct_client.product == 'Plex Media Player':
                        correct_client.sendCommand('timeline/poll', wait=0)

                    proxy_on_fail(correct_client.seekTo(int(offset * 1000)))
                    LOG.info('Jumped %s %s to %s %s', user, client.title, offset, media._prettyfilename())
                else:
                    if not ignore_ratingkey(media, CONFIG['general'].get('ignore_intro_ratingkeys')):
                        proxy_on_fail(correct_client.stop())
                        # We might need to login on pms as the user..
                        # urs_pms = users_pms(PMS, user)
                        # new_media = urs_pms.fetchItem(int(media.ratingkey))
                        # new_media.markWatched()
                        # LOG.debug('Stopped playback on %s and marked %s as watched.', client.title, media._prettyfilename())

                        # Check if we just start the next ep instantly.
                        if CONFIG['tv'].get('check_credits_start_next_ep') is True:
                            nxt = find_next(media) # This is always false for movies.
                            if nxt:
                                LOG.info('Start playback on %s with %s', user, nxt._prettyfilename())
                                proxy_on_fail(correct_client.playMedia(nxt))
            else:
                LOG.info('Didnt find the correct client.')

            # Some clients needs some time..
            # time.sleep(0.2)
            # client.play()
            # JUMP_LIST.remove(sessionkey)
            # time.sleep(1)

            return


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


def check(data):
    global JUMP_LIST

    if data.get('type') == 'playing' and data.get(
            'PlaySessionStateNotification'):

        sess = data.get('PlaySessionStateNotification')[0]

        if sess.get('state') != 'playing':
            return

        ratingkey = int(sess.get('ratingKey'))
        sessionkey = int(sess.get('sessionKey'))
        progress = sess.get('viewOffset', 0) / 1000  # converted to sec.
        mode = CONFIG['general'].get('mode', 'skip_only_theme')

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

            if action:
                POOL.apply_async(client_action, args=(sec, sessionkey, action))
                return

            if sessionkey not in JUMP_LIST:
                LOG.debug('Called jump with %s %s %s %s', item.prettyname, sessionkey, sec, action)
                JUMP_LIST.append(sessionkey)
                POOL.apply_async(client_action, args=(sec, sessionkey, action))

        with session_scope() as se:
            try:
                item = se.query(Processed).filter_by(ratingKey=ratingkey).one()

                if item:
                    bt = best_time(item)
                    LOG.debug('Found %s theme start %s, theme end %s, ffmpeg_end %s progress %s '
                              'best_time %s credits_start %s credits_end %s', item.prettyname,
                              item.theme_start_str, item.theme_end_str, item.ffmpeg_end_str,
                              to_time(progress), to_time(bt), item.credits_start_str, item.credits_end_str)

                    if (item.type == 'episode' and CONFIG['tv'].get('check_credits') is True and
                        CONFIG['tv'].get('check_credits_action') == 'stop' or
                        item.type == 'movie' and CONFIG['movie'].get('check_credits') is True and
                        CONFIG['movie'].get('check_credits_action') == 'stop'):

                        # todo check for correct credits too
                        if item.credits_start and item.credits_start != -1 and progress >= item.credits_start:
                            LOG.debug('We found the start of the credits.')
                            return jump(item, sessionkey, item.credits_start, action='stop')

                    # If recap is detected just instantly skip to intro end.
                    # Now this can failed is there is: recap, new episode stuff, intro, new episode stuff
                    # So thats why skip_only_theme is default as its the safest option.
                    if (mode == 'skip_if_recap' and item.type == 'episode' and item.has_recap is True and bt != -1):
                        return jump(item, sessionkey, bt)

                    # This mode will allow playback until the theme starts so it should be faster then skip_if_recap.
                    if mode == 'skip_only_theme':
                        if item.type == 'episode' and item.correct_theme_end and item.correct_theme_start:
                            if progress > item.correct_theme_start and progress < item.correct_theme_end:
                                LOG.debug('%s is in the correct time range correct_theme_end', item.prettyname)
                                return jump(item, sessionkey, item.correct_theme_end)

                        elif item.type == 'episode' and item.theme_end and item.theme_start:
                            if progress > item.theme_start and progress < item.theme_end:
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
            metadata_state == 'created' and
            identifier == 'com.plexapp.plugins.library'):

            LOG.debug('%s was added to %s', title, PMS.friendlyName)
            # Youtubedl can fail if we batch add loads of eps at the same time if there is no
            # theme.
            if (metadata_type == 1 and not CONFIG['movie'].get('process_recently_added') or
                metadata_state == 4 and not CONFIG['tv'].get('process_recently_added')):
                LOG.debug("Didnt start to process %s is process_recently_added is disabled")
                return

            if ratingkey not in IN_PROG:
                IN_PROG.append(ratingkey)
                ep = PMS.fetchItem(int(ratingkey))
                ret = POOL.apply_async(process_to_db, args=(ep,))
                return ret

        elif (metadata_type in (1, 4) and state == 9 and
              metadata_state == 'deleted'):

            if (metadata_type == 1 and not CONFIG['movie'].get('process_deleted') or
                metadata_state == 4 and not CONFIG['tv'].get('process_deleted')):
                LOG.debug("Didnt start to process %s is process_deleted is disabled for")
                return

            with session_scope() as se:
                try:
                    item = se.query(Processed).filter_by(ratingKey=ratingkey).one()
                    item.delete()
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
    x = get_offset_end(f, HT)
    click.echo(x)


@cli.command()
def watch(): # # pragma: no cover
    """Start watching the server for stuff to do."""
    global HT
    HT = get_hashtable()
    click.echo('Watching for media on %s' % PMS.friendlyName)
    ffs = PMS.startAlertListener(check)

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        click.echo('Aborting')
        ffs.stop()
        POOL.terminate()


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

                LOG.debug('Set correct_time %s for %s to start %s end %s', type, ep._prettyfilename(), start, end)


def real_main():
    try:
        cli()
    except:
        raise
    finally:
        # Make sure we save if we need it.
        if HT and HT.dirty:
            HT.save()


if __name__ == '__main__':
    print('You need to use bw_plex or cli.py')
