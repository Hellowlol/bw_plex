#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import multiprocessing
import os
import re
import time
from collections import defaultdict

try:
    from multiprocessing.pool import ThreadPool as Pool
except ImportError:
    from multiprocessing.dummy import ThreadPool as Pool

import click
from plexapi.compat import makedirs
from plexapi.exceptions import NotFound
from plexapi.server import PlexServer
from plexapi.utils import download
from profilehooks import timecall
from sqlalchemy.orm.exc import NoResultFound

from audfprint.hash_table import HashTable
from misc import analyzer, get_offset_end, convert_and_trim, to_time, search_for_theme_youtube
from db import session_scope, Preprocessed


POOL = Pool(10)

url = ''
token = ''
frmt = '%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s'
logging.basicConfig(format=frmt, level=logging.DEBUG) # <-- default for now.

LOG = logging.getLogger(__name__)

IN_PROG = []
JUMP_LIST = []
SHOWS = defaultdict(list)  # Fix this, should be all caps.
ROOT = os.path.abspath('.')
THEMES = os.path.join(ROOT, 'themes')
TEMP_THEMES = os.path.join(ROOT, 'temp_themes')
FP_HASHES = os.path.join(ROOT, 'hashes.pklz')

# Create default dirs.
makedirs(THEMES, exist_ok=True)
makedirs(TEMP_THEMES, exist_ok=True)

if os.path.exists(FP_HASHES):
    LOG.info('Loading existing files in db')
    HT = HashTable(FP_HASHES)
    for n in HT.names:
        LOG.debug('%s', n)

else:
    LOG.info('Creating new hashtable db')
    HT = HashTable()
    HT.save(FP_HASHES)
    HT.load(FP_HASHES)

# Disable some logging..
#logging.getLogger("plexapi").setLevel(logging.WARNING)
#logging.getLogger("requests").setLevel(logging.WARNING)
#logging.getLogger("urllib3").setLevel(logging.WARNING)


def load_themes():
    LOG.debug('Loading themes')
    items = os.listdir(THEMES)

    for i in items:
        if i:
            try:
                show_rating = i.split('__')[1].split('.')[0]
                SHOWS[show_rating] = i
            except IndexError:
                pass


def find_all_shows(func=None):
    """ Helper of get all the shows on a server.
        Very usefull if your pass a func so it run in a threadpool

        Args:
            func (callable)

        Returns: List

    """
    all_shows = []

    for section in PMS.library.sections():
        if section.TYPE == 'show':
            all_shows += section.all()

    if func:
        return POOL.map(func, all_shows)

    return all_shows


def find_next(media):
    """ Find the next media item or None."""
    try:
        nxt_ep = media.show().episode(
            season=media.seasonNumber, episode=media.index + 1)
        LOG.debug('Found %s', nxt_ep._prettyfilename())
        return nxt_ep

    except NotFound:
        LOG.debug(
            'Failed to find the next media item of %s'.media.grandparentTitle)


#@timecall(immediate=True)
def download_theme(media, force=False):
    """Download a theme using PMS. And add it to shows cache.

       force (bool): Download even if the theme exists.

       Return:
            The filepath of the theme.

    """
    if media.TYPE == 'show':
        name = media.title
        rk = media.ratingKey
        theme = media.theme
    else:
        name = media.grandparentTitle
        rk = media.grandparentRatingKey
        theme = media.grandparentTheme
        if theme is None:
            theme = media.show().theme

    name = '%s__%s' % (re.sub('[\'\"\\\/;,-]+', '', name), rk) # make a proper cleaning in misc.
    f_name = '%s.mp3' % name
    f_path = os.path.join(THEMES, f_name)

    if not os.path.exists(f_path) or force and theme:
        LOG.debug('Downloading %s', f_path)
        dlt = download(PMS.url(theme), savepath=THEMES, filename=f_name)

        if dlt:
            SHOWS[rk] = f_path
            return f_path
    else:
        LOG.debug('Skipping %s as it already exists', f_name)

    return f_path


def process_to_db(media, theme=None, vid=None, end=None, start=None):
    """Process a plex media item to the db

       Args:
            media (Episode obj):
            theme: path to the theme.
            vid: path to the stripped wav of the media item.
            offset: where in the video file did the theme end.

    """
    LOG.debug('Started to process %s', media._prettyfilename())
    if theme is None:
        theme = download_theme(media)

    if vid is None:
        vid = convert_and_trim(check_file_access(media), fs=11025, trim=600)

    # Lets skip the start time for now. This need to be added later to support shows
    # that have show, theme song show.
    if end is None:
        global HT
        start, end = get_offset_end(vid, HT)

    if end is not None:
        with session_scope() as se:
            p = Preprocessed(
                show_name=media.grandparentTitle,
                ep_title=media.title,
                theme_end=end,
                theme_start=start,
                theme_start_str=to_time(start),
                theme_end_str=to_time(end),
                duration=media.duration,
                ratingKey=media.ratingKey,
                grandparentRatingKey=media.grandparentRatingKey,
                prettyname=media._prettyfilename(),
                updatedAt=media.updatedAt)
            se.add(p)
            LOG.debug('Added %s to db', media._prettyfilename())


@click.group(help='CLI tool that monitors and jumps the client to after the theme.')
@click.option('--debug', '-d', default=False, is_flag=True, help='Add debug logging.')
@click.option('--username', '-u', default=None, help='Your plex username')
@click.option('--password', '-p', default=None, help='Your plex password')
@click.option('--servername', '-s', default=None, help='The server you want to monitor.')
@click.option('--url', default=None, help='url to the server you want to monitor')
@click.option('--token', '-t', default=None, help='plex-x-token')
@click.option('--config', '-c', default=None, help='Not in use atm.')
def cli(debug, username, password, servername, url, token, config):
    """ Entry point for the CLI."""
    global PMS

    # click.echo('debug %s' % debug)
    # click.echo('username %s' % username)
    # click.echo('password %s' % password)
    # click.echo('servername %s' % servername)
    # click.echo('url %s' % url)
    # click.echo('token %s' % token)
    # click.echo('config %s' % config)
    
    if debug:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)

    if username and password and servername:
        from plexapi.myplex import MyPlexAccount

        acc = MyPlexAccount(username, password)
        PMS = acc.resource(servername).connect()

    elif url and token:
        PMS = PlexServer(url, token)
    else:
        PMS = PlexServer('', '') # plexapi will pull config file..


    # CONFIG is unused atm.
    click.echo('Watching for media on %s' % PMS.friendlyName)
    

@cli.command()
def test_dexter():
    """Test manual process_to_db."""
    results = PMS.search('Dexter')[0]
    eps = results.episodes()

    for ep in eps:
        process_to_db(ep)


@cli.command()
@click.option('--fp', default=None, help='where to create the config file.')
def create_config(fp=None):
    if fp is None:
        fp = os.path.join(ROOT, 'config.ini')

    from config import read_or_make
    read_or_make(fp)


@cli.command()
@click.option('--force', default=False, is_flag=True)
def find_theme_youtube(force):
    shows = find_all_shows()
    LOG.debug('Downloading all themes from youtube. This might take a while..')
    for show in shows:
        search_for_theme_youtube(show.title, rk=show.ratingKey, save_path=TEMP_THEMES)


@cli.command()
@click.option('--force', default=False, is_flag=True)
@timecall(immediate=True)
def update_all_themes(force=False):
    """Find and download all themes"""
    LOG.debug('Updating all themes')

    # Lets read from the disk before we do any http calls
    load_themes()
    k = SHOWS.keys()

    def lol(media):
        if media.theme and media.ratingKey not in k:
            f = download_theme(media, force=force)
            # Sometime 0 bytes files get downloaded
            if os.path.getsize(f) == 0:
                LOG.debug('Deleted %s since the size was invalid' % f)
                os.remove(f)
            return f

    items = find_all_shows(func=lol)
    LOG.debug('Downloaded %s themes', len(items))


@cli.command()
@click.option('-n', help='threads', type=int, default=1)
def create_hash_table_from_themes(n):
    """ Create a hashtable from the themes."""
    from audfprint.audfprint import multiproc_add

    a = analyzer()
    all_files = []

    for root, dir, files in os.walk(THEMES):
        for f in files:
            fp = os.path.join(root, f)
            # We need to check this since when themes are downloaded
            # They sometimes get a 0b files.
            if os.path.exists(fp) and os.path.getsize(fp):
                all_files.append(fp)

    def report(s):  # this shitty reporter they want sucks balls..
        print(s)

    LOG.debug('Creating hashtable, this might take a while..')

    multiproc_add(a, HT, iter(all_files), report, n)
    if HT and HT.dirty:
        HT.save(FP_HASHES)


#@timecall(immediate=True)
def check_file_access(m):
    """Check if we can reach the file directly
       or if we have to download it via PMS.

       Args:
            m (plexapi.video.Episode)

       Return:
            filepath or http to the file.

    """
    LOG.debug('Checking file access')

    files = list(m.iterParts())
    for file in files:
        if os.path.exists(file.file):
            LOG.debug('Found %s', file.file)
            return file.file
        else:
            LOG.warning('Downloading from pms..')
            return PMS.url('%s?download=1' % file.key)


#@timecall(immediate=True)
def client_jump_to(offset=None, sessionkey=None):
    """Seek the client to the offset."""

    # Just check so we dont jump more then
    # once the first 60 sec
    now = time.time()
    for item in JUMP_LIST:
        sk, t = item
        if now - t < 60:
            return
        else:
            JUMP_LIST.remove(item)

    LOG.debug('Called client_jump_to with %s', offset)
    LOG.debug('Called with %s', sessionkey)
    for media in PMS.sessions():
        # Find the client.. This client does not have the correct address
        # or 'protocolCapabilities' so we have to get the correct one.
        # or we can proxy thru the server..
        if sessionkey and int(sessionkey) == media.sessionKey:
            JUMP_LIST.append((sessionkey, now))
            client = media.players[0]  #<---


            # This does not work on plex web since the fucker returns
            # the local url..
            client = PMS.client(client.title).connect()
            client.seekTo(int(offset * 1000))

            # Some clients needs some time..
            # time.sleep(0.2)
            # client.play()

            return


def task(item, sessionkey):
    global HT
    media = PMS.fetchItem(int(item))
    LOG.debug('Found %s', media._prettyfilename())
    if media.TYPE not in ('episode', 'show'):
        return

    # Lets try to download the theme.
    n = download_theme(media)
    if n:
        SHOWS[media.grandparentRatingKey] = n
    else:
        # lets skip if we don't have a theme.
        return

    LOG.debug('Convert %s to .wav', os.path.basename(n))
    theme = convert_and_trim(SHOWS[media.grandparentRatingKey], fs=11025)

    LOG.debug('Download the first 10 minutes of %s as .wav',
              media._prettyfilename())
    vid = convert_and_trim(check_file_access(media), fs=11025, trim=600)

    # Check if this shows theme exist in the hash table.
    # We should prop just check if x in HT.names
    try:
        HT.name_to_id(theme)
    except ValueError:
        LOG.debug('Theme %s does not exists in the %s' % (os.path.basename(theme), FP_HASHES))
        analyzer().ingest(HT, theme)
        HT = HT.save_then_reload(FP_HASHES)

    start, end = get_offset_end(vid, HT)
    if end is not None:
        # End is -1 if not found. Or a positiv int.
        if end:
            client_jump_to(end, sessionkey)
        process_to_db(media, theme=theme, vid=vid, offset=end)

   	try:
   		os.remove(vid)
   	except IOError:
   		LOG.excetion('Failed to delete %s', vid)

    # Should we start processing the next ep?
    LOG.debug('Check if we can find the next media item.')
    nxt = find_next(media)
    process_to_db(nxt)

    IN_PROG.remove(item)


def check(data):
    
    if data.get('type') == 'playing' and data.get(
            'PlaySessionStateNotification'):
        print('data')
        sess = data.get('PlaySessionStateNotification')[0]
        offset = 60000  # just check the first 60 sec
        if offset > sess.get('viewOffset', 0):
            ratingkey = sess.get('ratingKey')
            sessionkey = sess.get('sessionKey')
            with session_scope() as se:
                try:
                    item = se.query(Preprocessed).filter_by(
                        ratingKey=ratingkey).one()

                    

                    if item and item.theme_end:
                        LOG.debug('Found %s in the db with theme_end %s' % (
                              item.prettyname, item.theme_end))
                        POOL.apply_async(
                            client_jump_to, args=(item.theme_end, sessionkey))
                    return
                except NoResultFound:
                    pass

            if ratingkey not in IN_PROG:
                IN_PROG.append(ratingkey)
                POOL.apply_async(task, args=(ratingkey, sessionkey))


@cli.command()
@click.argument('-f')
def match(f):
    """Manual match for a file. This is usefull for testing the a finds the correct end time"""
    # assert f in H.names
    x = get_offset_end(f, HT)
    print(x)


@cli.command()
def watch():
    """Start watching the server for stuff to do."""
    ffs = PMS.startAlertListener(check)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        click.echo('Aborting')
        ffs.stop()
        POOL.terminate()


if __name__ == '__main__':
    cli()
