#!/usr/bin/env python
#!python2
# -*- coding: utf-8 -*-

import logging
import os
import time

try:
    from multiprocessing.pool import ThreadPool as Pool
except ImportError:
    from multiprocessing.dummy import ThreadPool as Pool

import click
from sqlalchemy.orm.exc import NoResultFound

from bw_plex import FP_HASHES, CONFIG, THEMES, TEMP_THEMES, LOG, INI_FILE

from bw_plex.config import read_or_make
from bw_plex.db import session_scope, Preprocessed
from bw_plex.misc import (analyzer, convert_and_trim, choose, find_next, find_offset_ffmpeg, get_offset_end,
                   get_pms, get_hashtable, has_recap, to_sec, to_time, search_for_theme_youtube)


POOL = Pool(20)
PMS = None
IN_PROG = []
JUMP_LIST = []
SHOWS = {}
HT = None


def load_themes():
    LOG.debug('Loading themes')
    items = os.listdir(THEMES)

    for i in items:
        fp = os.path.join(THEMES, i)
        LOG.debug(fp)
        if fp:
            try:
                show_rating = i.split('__')[1].split('.')[0]
                SHOWS[int(show_rating)] = fp
            except IndexError:
                pass


def find_all_shows(func=None):
    """ Helper of get all the shows on a server.


        Args:
            func (callable): Run this function in a threadpool.

        Returns: List

    """
    all_shows = []

    for section in PMS.library.sections():
        if section.TYPE == 'show':
            all_shows += section.all()

    if func:
        return POOL.map(func, all_shows)

    return all_shows


def process_to_db(media, theme=None, vid=None, start=None, end=None, ffmpeg_end=None):
    """Process a plex media item to the db

       Args:
            media (Episode obj):
            theme: path to the theme.
            vid: path to the stripped wav of the media item.
            start: of theme.
            end (int): of theme.

    """
    global HT

    ff = -1
    name = media._prettyfilename()
    LOG.debug('Started to process %s', name)
    if theme is None:
        theme = convert_and_trim(get_theme(media), fs=11025, theme=True)

    if vid is None:
        vid = convert_and_trim(check_file_access(media), fs=11025, trim=600)

    # Lets skip the start time for now. This need to be added later to support shows
    # that have show, theme song show.
    if end is None:
        start, end = get_offset_end(vid, HT)

    if ffmpeg_end is None:
        ffmpeg_end = find_offset_ffmpeg(check_file_access(media))

    if end is not None:
        with session_scope() as se:
            try:
                se.query(Preprocessed).filter_by(ratingKey=media.ratingKey).one()
            except NoResultFound:
                p = Preprocessed(show_name=media.grandparentTitle,
                                 ep_title=media.title,
                                 theme_end=end,
                                 theme_start=start,
                                 theme_start_str=to_time(start),
                                 theme_end_str=to_time(end),
                                 ffmpeg_end=ffmpeg_end,
                                 ffmpeg_end_str=to_time(ff),
                                 duration=media.duration,
                                 ratingKey=media.ratingKey,
                                 grandparentRatingKey=media.grandparentRatingKey,
                                 prettyname=media._prettyfilename(),
                                 updatedAt=media.updatedAt,
                                 has_recap=has_recap(media, CONFIG.get('words')))
                se.add(p)
                LOG.debug('Added %s to media.db', name)


@click.group(help='CLI tool that monitors pms and jumps the client to after the theme.')
@click.option('--debug', '-d', default=True, is_flag=True, help='Add debug logging.')
@click.option('--username', '-u', default=None, help='Your plex username')
@click.option('--password', '-p', default=None, help='Your plex password')
@click.option('--servername', '-s', default=None, help='The server you want to monitor.')
@click.option('--url', default=None, help='url to the server you want to monitor')
@click.option('--token', '-t', default=None, help='plex-x-token')
@click.option('--config', '-c', default=None, help='Not in use atm.')
def cli(debug, username, password, servername, url, token, config):
    """ Entry point for the CLI."""
    global PMS
    global CONFIG

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

    if config and os.path.isfile(config):
        CONFIG = read_or_make(config)

    url = url or CONFIG.get('url')
    token = token or CONFIG.get('token')

    if url and token or username and password:

        PMS = get_pms(url=url, token=token,
                      username=username,
                      password=password,
                      servername=servername)


def get_theme(media):
    """Get the current location of the theme or download
       the damn thing and convert it so it's ready for matching."""
    LOG.debug('theme media type %s', media.TYPE)

    if media.TYPE == 'show':
        name = media.title
        rk = media.ratingKey
    else:
        name = media.grandparentTitle
        rk = media.grandparentRatingKey

    theme = SHOWS.get(rk)

    if theme is None:
        theme = search_for_theme_youtube(name,
                                         rk=rk,
                                         save_path=THEMES)

        theme = convert_and_trim(theme, fs=11025, theme=True)
        SHOWS[rk] = theme
    return theme


@cli.command()
@click.option('-client_name', default=None)
@click.option('-skip_done', default=False, is_flag=True)
def manual_check_db(client_name, skip_done):
    """Do a manual check of the db. This will start playback on a client and seek the video file where we have found
       theme start/end and ffmpeg_end. You will be asked if its a correct match, press y or set the correct time in
       mm:ss format.
    """
    if client_name is None:
        client = choose('Select what client to use', PMS.clients(), 'title')[0]
    else:
        client = PMS.client(client_name).connect()

    with session_scope() as se:
        items = se.query(Preprocessed).all()
        click.echo('')

        for item in sorted(items, key=lambda k: k.ratingKey):

            click.echo('%s %s' % (click.style('Checking', fg='white'),
                                  click.style(item.prettyname, bold=True, fg='green')))
            click.echo('theme_start %s theme_end %s ffmpeg_end %s' % (item.theme_start,
                                                                      item.theme_end_str,
                                                                      item.ffmpeg_end))
            click.echo('*%s*' % ('-' * 80))
            click.echo('')

            if item.theme_start == -1 or item.theme_end == -1:
                click.echo('Exists in the db but the start of the theme was not found.'
                           ' Check the audio file and run it again.')

            if item.theme_end != -1:

                if (not skip_done and item.correct_theme_start) or not item.correct_theme_start:

                    click.echo('Found theme_start at %s %s theme_end %s %s' % (item.theme_start, item.theme_start_str,
                        item.theme_end, item.theme_end_str))

                    client.playMedia(PMS.fetchItem(item.ratingKey))
                    time.sleep(1)

                    client.seekTo(item.theme_start * 1000)
                    start_match = click.prompt('Was theme_start at %s correct?' % item.theme_start_str)
                    if start_match:
                        if start_match == 'y':
                            item.correct_theme_start = item.theme_start
                        else:
                            item.correct_theme_start = to_sec(start_match)

                if (not skip_done and item.correct_theme_end) or not item.correct_theme_end:

                    client.seekTo(item.theme_end * 1000)
                    end_match = click.prompt('Was theme_end at %s correct?' % item.theme_end_str)
                    if end_match:
                        if end_match == 'y':
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

                    client.playMedia(PMS.fetchItem(item.ratingKey))
                    time.sleep(1)
                    client.seekTo(j * 1000)

                    match = click.prompt('Was ffmpeg_end at %s correct?' % item.ffmpeg_end_str)

                    if match:
                        if match == 'y':
                            item.correct_ffmpeg = item.ffmpeg_end
                        else:
                            item.correct_ffmpeg = to_sec(match)

            click.clear()

            # Commit thit shit after each loop.
            if se.dirty:
                se.commit()

        click.echo('Done')




@cli.command()
@click.option('-name', help='Search for a show.', default=None)
@click.option('-sample', default=0, help='Process N episodes of all shows.', type=int)
@click.option('-threads', help='Threads to uses', default=1, type=int)
@click.option('-skip_done', help='Skip media items that exist in the db', is_flag=True)
def process(name, sample, threads, skip_done):
    """Manual process some/all eps.
       You will asked for what you want to process

    """
    global HT

    load_themes()

    all_eps = []
    shows = find_all_shows()
    if name:
        shows = [s for s in shows if s.title.lower().startswith(name.lower())]
        shows = choose('Select what show to process', shows, 'title')

        for show in shows:
            eps = show.episodes()
            eps = choose('Select episodes', eps, lambda x: '%s %s' % (x._prettyfilename(), x.title))
            all_eps += eps

    if sample:
        for show in shows:
            all_eps += show.episodes()[:sample]

    if skip_done:
        # Now there must be a betty way..
        with session_scope() as se:
            items = se.query(Preprocessed).all()
            for item in items:
                for ep in all_eps:
                    if ep.ratingKey == item.ratingKey:
                        click.secho('Removing as %s already is processed' % item.prettyname, fg='red')
                        all_eps.remove(ep)

    HT = get_hashtable()
    if all_eps:
        p = Pool(threads)
        p.map(process_to_db, all_eps, 1)



@cli.command()
@click.argument('name')
def ffmpeg_process(name):
    click.echo(find_offset_ffmpeg(name))


@click.command()
@click.option('--fp', default=None, help='where to create the config file.')
def create_config(fp=None):
    """Create a config.

       Args:
            fp(str): Where to create the config. If omitted it will be written to the root.

       Returns:
            None

    """
    if fp is None:
        fp = INI_FILE

    read_or_make(fp)


@cli.command()
@click.argument('name')
@click.argument('url')
@click.option('-rk', help='Add rating key', default='auto')
def fix_shitty_theme(name, url, rk=None):
    """Set the correct fingerprint of the show in the hashes.db and
       process the eps of that show in the db against the new theme fingerprint.

       Args:
            name(str): name of the show
            url(str): the youtube url to the correct theme.
            rk(None, str): ratingkey of that show. Pass auto if your lazy.

       Returns:
            None
    """
    global HT
    HT = get_hashtable()
    fp = search_for_theme_youtube(name, url=url, save_path=THEMES)

    # Assist for the lazy bastards..
    if rk == 'auto':
        item = PMS.search(name)
        item = choose('Select correct show', item, lambda x: '%s %s' % (x.title, x.TYPE))
        if item:
            #if name.lower() == item[0].title.lower():
            rk = item[0].ratingKey

    for fp in HT.names:
        if os.path.basename(fp).lower() == name.lower():
            LOG.debug('Removing %s from the hashtable', fp)
            HT.remove(fp)

    analyzer().ingest(HT, fp)
    HT.save(FP_HASHES)
    to_pp = []

    if rk:  # TODO a
        with session_scope() as se:
            item = se.query(Preprocessed).filter_by(grandparentRatingKey=rk)

            for i in item:
                to_pp.append(PMS.fetchItem(i.ratingKey))
                # Prob should have edit, but we do this so we can use process_to_db.
                se.delete(i)

        for media in to_pp:
            process_to_db(media)


@cli.command()
@click.option('-show', default=None)
@click.option('--force', default=False, is_flag=True)
def find_theme_youtube(show, force):
    """Iterate over all your shows and downloads the first match for
       showname theme song on youtube.

       Since this is best effort (at best.. )they are stored in the temp_theme dir
       Copy them over to the theme folder and run create_hash_table_from_themes and fix any mismatch with
       fix_shitty_theme.

        Args:
            show(str): name of the show
            force(bool): does nothing

        Returns:
            None
    """

    if show is not None:
        search_for_theme_youtube(show, rk=1, save_path=TEMP_THEMES)
        return

    shows = find_all_shows()
    LOG.debug('Downloading all themes from youtube. This might take a while..')

    #if n: # untested
    #    POOL.map(search_for_theme_youtube,
    #             [(s.title, s.ratingKey, TEMP_THEMES) for s in shows], 1)

    for show in shows:
        search_for_theme_youtube(show.title, rk=show.ratingKey,
                                 save_path=TEMP_THEMES)


@cli.command()
@click.option('-n', help='threads', type=int, default=1)
@click.option('-directory', default=None)
def create_hash_table_from_themes(n, directory):
    """ Create a hashtable from the themes."""
    from audfprint.audfprint import multiproc_add
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
        pass  #print(s)

    LOG.debug('Creating hashtable, this might take a while..')

    multiproc_add(a, HT, iter(all_files), report, n)
    if HT and HT.dirty:
        HT.save(FP_HASHES)


@click.command()
def test_basic():
    """Test command for myself."""
    pass


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
    for file in files:
        if os.path.exists(file.file):
            LOG.debug('Found %s', file.file)
            return file.file
        else:
            LOG.warning('Downloading from pms..')
            return PMS.url('%s?download=1' % file.key)


def client_jump_to(offset=None, sessionkey=None):
    """Seek the client to the offset.

       Args:
            offset(int): Default None
            sessionkey(int): So we made sure we control the correct client.

       Returns:
            None
    """
    global JUMP_LIST
    LOG.debug('Called jump with %s %s %s', offset, to_time(offset), sessionkey)
    if offset == -1:
        return

    for media in PMS.sessions():
        # Find the client.. This client does not have the correct address
        # or 'protocolCapabilities' so we have to get the correct one.
        # or we can proxy thru the server..
        if sessionkey and int(sessionkey) == media.sessionKey:
            client = media.players[0]
            user = media.usernames[0]
            LOG.debug('client %s %s' % (client.title, (media.viewOffset / 1000)))

            # To stop processing. from func task if we have used to much time..
            # This will not work if/when credits etc are added. Need a better way.
            # if offset <= media.viewOffset / 1000:
            #    LOG.debug('Didnt jump because of offset')
            #    return

            # This does not work on plex web since the fucker returns
            # the local url..
            client = PMS.client(client.title).connect()
            client.seekTo(int(offset * 1000))
            LOG.debug('Jumped %s %s to %s %s', user, client.title, offset, media._prettyfilename())

            # Some clients needs some time..
            # time.sleep(0.2)
            # client.play()
            JUMP_LIST.remove(sessionkey)
            time.sleep(1)

            return


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
    # LOG.debug('Found %s', media._prettyfilename())
    if media.TYPE not in ('episode', 'show'):
        return

    theme = get_theme(media)
    LOG.debug('task theme %s', theme)

    LOG.debug('Download the first 10 minutes of %s as .wav', media._prettyfilename())
    vid = convert_and_trim(check_file_access(media), fs=11025, trim=600)

    # Check if this shows theme exist in the hash table.
    # We should prop just check if x in HT.names
    try:
        HT.name_to_id(theme)
    except ValueError:
        LOG.debug('No fingerprint for theme %s does exists in the %s',
                  os.path.basename(theme), FP_HASHES)

        analyzer().ingest(HT, theme)
        HT = HT.save_then_reload(FP_HASHES)

    start, end = get_offset_end(vid, HT)
    ffmpeg_end = find_offset_ffmpeg(check_file_access(media))
    if end != -1:
        # End is -1 if not found. Or a positiv int.
        process_to_db(media, theme=theme, vid=vid, start=start, end=end, ffmpeg_end=ffmpeg_end)

    try:
        os.remove(vid)
        LOG.debug('Deleted %s', vid)
    except IOError:
        LOG.excetion('Failed to delete %s', vid)

    # Should we start processing the next ep?

    nxt = find_next(media)
    if nxt:
        process_to_db(nxt)

    try:
        IN_PROG.remove(item)
    except ValueError:
        LOG.debug('Failed to remove %s from IN_PROG', item)


def check(data):
    global JUMP_LIST

    if data.get('type') == 'playing' and data.get(
            'PlaySessionStateNotification'):

        sess = data.get('PlaySessionStateNotification')[0]

        if sess.get('state') != 'playing':
            return

        ratingkey = sess.get('ratingKey')
        sessionkey = int(sess.get('sessionKey'))
        progress = sess.get('viewOffset', 0) / 1000  # converted to sec.
        mode = CONFIG.get('mode', 'skip_only_theme')

        with session_scope() as se:
            try:
                item = se.query(Preprocessed).filter_by(ratingKey=ratingkey).one()

                if item:
                    LOG.debug('Found %s theme start %s, theme end %s, progress %s', item.prettyname,
                              item.theme_start_str, item.theme_end_str, to_time(progress))

                    if mode == 'skip_only_theme' and item.theme_end and item.theme_start:
                        if progress > item.theme_start and progress < item.theme_end:
                            LOG.debug('%s is in the correct time range', item.prettyname)
                            if sessionkey not in JUMP_LIST:
                                JUMP_LIST.append(sessionkey)
                                POOL.apply_async(client_jump_to, args=(item.theme_end, sessionkey))

                        else:
                            if item.theme_start - progress < 0:
                                n = item.theme_start - progress
                                if n > 0:
                                    part = 'jumping in %s' % to_time(n)
                                else:
                                    part = 'should have jumped %s ago' % to_time(n)
                                LOG.debug('Skipping %s as it not in the correct time range jumping in %s',
                                          item.prettyname, part)

                    if mode == 'check_recap':
                        pass  # TODO

            except NoResultFound:
                if ratingkey not in IN_PROG:
                    IN_PROG.append(ratingkey)
                    LOG.debug('Failed to find %s in the db', ratingkey)
                    POOL.apply_async(task, args=(ratingkey, sessionkey))


@cli.command()
@click.argument('-f')
def match(f):
    """Manual match for a file. This is usefull for testing the a finds the correct end time."""
    # assert f in H.names
    global HT
    HT = get_hashtable()
    x = get_offset_end(f, HT)
    print(x)


@cli.command()
def watch():
    """Start watching the server for stuff to do."""
    load_themes()
    global HT
    HT = get_hashtable()
    click.echo('Watching for media on %s' % PMS.friendlyName)
    ffs = PMS.startAlertListener(check)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        click.echo('Aborting')
        ffs.stop()
        POOL.terminate()
        # if HT and HT.dirty:
        #    HT.save()


@cli.command()
@click.argument('showname')
@click.argument('season', type=int)
@click.argument('episode', type=int)
@click.argument('type', default='theme')
@click.argument('start')
@click.argument('end')
def set_manual_theme_time(showname, season, episode, type, start, end):
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
                item = se.query(Preprocessed).filter_by(ratingKey=ep.ratingKey).one()
                start = to_sec(start)
                end = to_sec(end)

                if start:
                    item.correct_time_start = start

                if end:
                    item.correct_time_end = end

                LOG.debug('Set correct_time %s for %s to start %s end %s', type, ep._prettyfilename(), start, end)


if __name__ == '__main__':
    cli()
