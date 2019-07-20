#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division

import os
import re
import subprocess
import time
import itertools
import unicodedata

from collections import defaultdict

import click
import requests
from bs4 import BeautifulSoup

from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

import pysubs2
from pysubs2.ssafile import SSAFile
from pysubs2.formats import FILE_EXTENSION_TO_FORMAT_IDENTIFIER

from bw_plex import THEMES, CONFIG, LOG, FP_HASHES
from bw_plex.audio import convert_and_trim, has_recap_audio


def ignore_ratingkey(item, key):
    """Helper to check if this is in a ignorelist"""
    if item.TYPE == 'movie':
        return item.ratingKey in key
    if item.TYPE == 'episode':
        return any(i for i in [item.ratingKey, item.grandparentRatingKey, item.parentRatingKey] if i in key)

    return False


def get_pms(url=None, token=None, username=None,
            password=None, servername=None, verify_ssl=None):  # pragma: no cover

    url = url or CONFIG['server'].get('url')
    token = token or CONFIG['server'].get('token')
    verify_ssl = verify_ssl or CONFIG['server'].get('verify_ssl', False)
    servername = servername or CONFIG['server'].get('name')

    if url and token:
        url = url.rstrip('/')
        sess = requests.Session()
        if not verify_ssl:
            # Disable the urllib3 warning as the user
            # has choosen to not verify the http request.
            # why the fuck isnt this default?
            requests.packages.urllib3.disable_warnings()
            sess.verify = False
        PMS = PlexServer(url, token, sess)

    elif username and password and servername:
        acc = MyPlexAccount(username, password)
        PMS = acc.resource(servername).connect()

    assert PMS is not None, 'You need to add a url and token or username password and servername'

    LOG.debug('Getting server %s', PMS.friendlyName)

    return PMS


def users_pms(pms, user):  # pragma: no cover
    """Login on your server using the users access credentials."""
    from plexapi.exceptions import NotFound
    LOG.debug('Logging in on PMS as %s', user)
    acc = pms._server.myPlexAccount()
    try:
        usr = acc.user(user)
    except NotFound:
        # We fail to find the correct user if the passed user is the owner..
        # We we simply return the owner pms as we already have that.
        # TODO this might be a issue, see if we cant handle this another way using plexapi.
        LOG.debug('returning org pms')
        return pms
    token = usr.get_token(pms.machineIdentifier)
    users_pms = PlexServer(pms._baseurl, token)
    return users_pms


def find_next(media):
    """Find what ever you have that is next ep."""
    LOG.debug('Check if we can find the next media item.')
    if media.TYPE == 'movie':
        return

    eps = media.show().episodes()

    for ep in eps:
        if ep.seasonNumber >= media.seasonNumber and ep.index > media.index:
            LOG.debug('Found %s', ep._prettyfilename())
            return ep

    LOG.debug('Failed to find the next media item of %s', media.grandparentTitle)


def to_time(sec):
    if sec == -1:
        return '00:00'

    m, s = divmod(sec, 60)
    return '%02d:%02d' % (m, s)


def sec_to_hh_mm_ss(sec):
    return time.strftime('%H:%M:%S', time.gmtime(sec))


def to_ms(ip_str): # FIX ME
    """Convert a HH:MM:SS:MILL to milliseconds"""
    try:
        #ip = ip_str.split(':')
        hh, mm, ss = ip_str.split(':')
        hh = int(hh) * 60 * 60
        mm = int(mm) * 60
        ss = int(ss)
    except ValueError:
        hh = 0
        try:
            mm, ss = ip_str.split(':')
            mm = int(mm) * 60
            ss = int(ss)
        except ValueError:
            raise

    sec = hh + mm + ss
    return sec * 1000


def analyzer():
    from bw_plex.audfprint.audfprint_analyze import Analyzer

    a = Analyzer()
    a.n_fft = 512
    a.n_hop = a.n_fft // 2
    a.shifts = 4
    a.fail_on_error = False
    a.density = 50
    return a


def matcher():
    from bw_plex.audfprint.audfprint_match import Matcher
    m = Matcher()
    m.find_time_range = True
    m.search_depth = 2000
    m.verbose = True
    m.exact_count = True
    m.max_returns = 100
    # Remember https://github.com/dpwe/audfprint/issues/8
    m.time_quantile = 0.02
    # This need to be high as we might get to many hashes before
    # we have found the end.
    m.max_alignments_per_id = 10000
    #m.sort_by_time = True # remove this?
    return m


def find_theme_start_end(wav, hashtable, check_if_missing=False):
    an = analyzer()
    match = matcher()
    start_time = -1
    end_time = -1

    t_hop = an.n_hop / float(an.target_sr)
    rslts, dur, nhash = match.match_file(an, hashtable, wav, 1)  # The number does not matter...

    for (tophitid, nhashaligned, aligntime,
         nhashraw, rank, min_time, max_time) in rslts:
            end_time = max_time * t_hop
            start_time = min_time * t_hop
            confidence = nhashaligned / nhashraw
            LOG.debug('Match %s rank %s aligntime %s theme song %s started at %s (%s) in ended at %s (%s) match length %s in the video. Video was found in theme %s ended at %s confidence %s' % (tophitid, rank,
                       aligntime, hashtable.names[tophitid], start_time, to_time(start_time), end_time, to_time(end_time), (max_time - min_time) * t_hop, (min_time + aligntime) * t_hop, (max_time + aligntime) * t_hop, confidence))

    if len(rslts):
        best = rslts[0]
        end_time = best[6] * t_hop
        start_time = best[5] * t_hop
        LOG.debug('Best match was %s', hashtable.names[best[0]])
        return start_time, end_time

    LOG.debug('NO match in the hashes.pklz just returning -1 -1')

    return start_time, end_time


def calc_offset(final_video, final_audio, dev=7, cutoff=15):
    """Helper to find matching time ranges between audio silence and blackframes.
       It simply returns the first matching blackframes with silence.

       Args:
            final_video(list): [[start, end, duration], ...]
            final_audio(list): [[start, end, duration], ...]
            dev (int): The deviation we should accept.

       Returns:
            int


    """
    match_window = []

    def to_time_range(items):
        # just to convert a seconds time range to MM:SS format
        # so its easyer to match,
        t = []
        for i in items:
            t.append([to_time(ii) for ii in i])
        return t

    LOG.debug('final_video %s', to_time_range(final_video))
    LOG.debug('final_audio %s', to_time_range(final_audio))

    LOG.debug('fin v %s', final_video)
    LOG.debug('fin a %s', final_audio)

    # So i could really use some help regarding this. Its shit but it kinda works.
    # Need to get some kinda score system as we need lower db to 30 and dur to 0.2 to catch more stuff.

    for video in reversed(final_video):
        for aud in final_audio:
            # Sometime times there are black shit the first 15 sec. lets skip that to remove false positives
            if video[1] >= cutoff:  # end time of black shit..
                # if silence is within black shit its ok. Allow dev sec deviance.
                if aud and video and abs(aud[0] - video[0]) <= dev and abs(aud[1] - video[0]) <= dev:
                    # todo remove dupes from here...
                    match_window.append(video)

    if not match_window and not final_audio and final_video:
        LOG.debug('There are no audio silence at all, taking a stab in the dark.')
        try:
            return list(sorted([i for i in final_video if i[0] >= 30 and i[1] >= 396], key=lambda k: k[2]))[0][0]
        except IndexError:
            return -1

    if match_window:
        # remove dupes
        match_window = set(tuple(i) for i in match_window)

        try:
           # Sort on end time and duration.
            m = list(sorted(match_window, key=lambda k: (k[1], k[2])))
            LOG.debug('Matching windows are %s', to_time_range(m))
            # So this might be wrong on some shows as as they fade to black and have audio silence
            # before the theme song and or recap.
            return m[0][0]
        except IndexError:
            return -1

    return -1


def find_offset_ffmpeg(afile, trim=600, dev=7, duration_audio=0.3, duration_video=0.5, pix_th=0.10, au_db=50):
    """Find a list of time range for black detect and silence detect.duration_video

       Args:
            afile(str): the file we should checj
            trim(int): Trim the file n secs
            dev(int): The accepted deviation
            duration_audio(float): Duration of the silence
            duration_video(float): Duration of the blackdetect
            pix_th(float): param of blackdetect
            au_db(int): param audio silence.


       Returns:
            int

    """
    v = 'blackdetect=d=%s:pix_th=%s' % (duration_video, pix_th)
    a = 'silencedetect=n=-%sdB:d=%s' % (au_db, duration_audio)

    cmd = ['ffmpeg', '-i', afile, '-t', str(trim), '-vf',
           v, '-af', a, '-f', 'null', '-']

    LOG.debug('Calling find_offset_ffmpeg with command %s', ' '.join(cmd))

    proc = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    temp_silence = []
    final_audio = []
    final_video = []

    audio_reg = re.compile('silence_\w+:\s+?(-?\d+\.\d+|\d)')
    black_reg = re.compile('black_\w+:(\d+\.\d+|\d)')

    while True:
        line = proc.stderr.readline()
        line = line.decode('utf-8').strip()
        # Try to help out with context switch
        # Allow context switch
        time.sleep(0.0001)

        if line:
            audio_res = re.findall(audio_reg, line)

            # Audio shit is sometime on several lines...
            if audio_res:
                temp_silence.extend(audio_res)

            if len(temp_silence) == 3:
                k = temp_silence[:]
                kk = [float(i) for i in k]
                final_audio.append(kk)
                temp_silence[:] = []

            video_res = re.findall(black_reg, line)

            if video_res:
                f = [float(i) for i in video_res]
                final_video.append(f)

        else:
            break

    return calc_offset(final_video, final_audio)


def get_valid_filename(s):

    def remove_accents(input_str):
        try:
            input_str = unicodedata.normalize('NFKD', input_str.decode('utf-8'))
        except (UnicodeError, UnicodeDecodeError, AttributeError):
            try:
                input_str = unicodedata.normalize('NFKD', input_str)
            except:  # pragma: no cover
                pass

        return u''.join([c for c in input_str if not unicodedata.combining(c)])

    head = os.path.dirname(s)
    tail = os.path.basename(s)

    clean_tail = re.sub(r'(?u)[^-_\w.() ]', '', tail)
    clean_tail = remove_accents(clean_tail)
    # remove double space
    clean_tail = ' '.join(clean_tail.strip().split())

    if head:
        return os.path.join(head, u'%s' % clean_tail)
    else:
        return clean_tail


def search_tunes(name, rk, url=None):
    """Search televisontunes for a show theme song.

       Args:
            name (str): eg dexter
            rk (str): ratingkey, this used to find the correct tunes for the shows later.
            url (None, str): Default None, for manual override.

       Returns:
            dict

    """
    # Pretty much everything is stolen from
    # https://github.com/robwebset/script.tvtunes/blob/master/resources/lib/themeFetcher.py
    # Thanks!
    LOG.debug('Searching search_tunes for %s using rk %s', name, rk)

    titles = ['theme', 'opening', 'main title']
    baseurl = 'http://www.televisiontunes.com'

    def real_url(url):
        res = requests.get(url)
        sub_soup = BeautifulSoup(res.text, 'html5lib')
        link = sub_soup.find('a', id='download_song')
        return baseurl + link['href']

    result = defaultdict(list)

    if url is None:
        res = requests.get('http://www.televisiontunes.com/search.php', params={'q': name})
        LOG.debug(res.url)
        if res:
            soup = BeautifulSoup(res.text, 'html5lib')

            search_results = soup.select('div.jp-title > ul > li > a')
            if search_results:
                for sr in search_results:
                    txt = sr.text.strip().split(' - ')
                    if len(txt) == 2:
                        sname = txt[0].strip()
                        title = txt[1].strip()
                    else:
                        sname = txt[0].strip()
                        title = ''

                    # Many of the themes is just listed with the theme names, atm we are rather strict by checking
                    # if a valid word is in the title, this is omitted many times,
                    # but we could check the read url and see if it was listed in
                    # the id #ffx in baseurl + sr['href']
                    if sname.lower() == name.lower() and title and any([i for i in titles if i and i.lower() in title.lower()]):
                        result['%s__%s__%s' % (name, rk, int(time.time()))].append(real_url(baseurl + sr['href']))

    if url and 'televisiontunes' in url:
        result['%s__%s__%s' % (name, rk, int(time.time()))].append(real_url(url))

    if result:
        for k, v in result.items():
            LOG.debug('search tunes found %s %s %s', k, len(v), ', '.join(v))

    return result


def search_for_theme_youtube(name, rk=1337, save_path=None, url=None):
    import youtube_dl

    LOG.debug('Searching youtube for name %s rk %s save_path %s url %s ' % (name, rk, save_path, url))

    if isinstance(name, tuple):
        name, rk, save_path = name

    if save_path is None:
        save_path = os.getcwd()

    if url and 'youtube' not in url:
        return []

    fp = os.path.join(save_path, '%s__%s__%s' % (name, rk, int(time.time())))
    fp = get_valid_filename(fp)
    # Youtuble dl requires the template to be unicode.
    t = u'%s' % fp

    ydl_opts = {
        'quiet': True,
        'continuedl': True,
        'external_downloader': 'ffmpeg',
        #'verbose': True,
        'outtmpl': t + u'.%(ext)s',
        'default_search': 'ytsearch',
        # So we select "best" here since this does not get throttled by
        # youtube. Should it be a config option for ppl with data caps?
        # Possible format could be bestaudio for those poor fuckers..
        'format': 'best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'logger': LOG,
    }
    # https://github.com/rg3/youtube-dl/issues/6923
    # ydl_opts['external_downloader'] = 'aria2c'
    # ydl_opts['external_downloader_args'] = []#['-x', '8', '-s', '8', '-k', '256k']

    ydl = youtube_dl.YoutubeDL(ydl_opts)

    def nothing(*args, **kwargs):
        pass

    ydl.to_screen = nothing

    name = name.replace(':', '')

    with ydl:
        try:
            if url:
                ydl.download([url])
            else:
                ydl.download([name + ' theme song'])
            return t + '.wav'

        except:  # pragma: no cover
            LOG.exception('Failed to download theme song %s' % name)
            return

    LOG.debug('Done downloading theme for %s', name)

    return t + '.wav'


def download_theme(media, ht, theme_source=None, url=None):
    if media.TYPE == 'show':
        name = media.title
        rk = media.ratingKey
        _theme = media.theme
    else:
        name = media.grandparentTitle
        rk = media.grandparentRatingKey
        _theme = media.grandparentTheme
        if _theme is None:
            _theme = media.show().theme

    pms = media._server
    theme = []

    if url and os.path.isfile(url):
        theme_source = 'manual'

    if theme_source is None:
        theme_source = CONFIG['tv'].get('theme_source', 'all')

    if theme_source == 'manual':
        theme.append(url)

    elif theme_source == 'youtube':
        theme = search_for_theme_youtube(name, rk, THEMES, url=url)

    elif theme_source == 'tvtunes':
        theme = search_tunes(name, rk, url=url)
        theme = list(itertools.chain.from_iterable(theme.values()))

    elif theme_source == 'plex' and _theme is not None:
        theme = pms.url(_theme, includeToken=True)
        LOG.debug('Downloading theme via plex %s', theme)

    elif theme_source == 'all':
        st = search_tunes(name, rk, url=url)
        st_res = list(itertools.chain.from_iterable(st.values()))
        theme.extend(st_res)

        if _theme is not None:
            theme.append(pms.url(_theme, includeToken=True))

        yt_theme = search_for_theme_youtube(name, rk, THEMES, url=url)
        if yt_theme:
            theme.append(yt_theme)

    if not isinstance(theme, list) and theme is not None:
        theme = [theme]

    final = []
    for th in theme:
        LOG.debug('Download theme using source %s', th)
        # Filename is just added so we can pass a url to convert_and_trim
        th = convert_and_trim(th, fs=11025, theme=True, filename='%s__%s__%s' % (name, rk, int(time.time())))
        analyzer().ingest(ht, th)
        final.append(th)

    return final


def get_hashtable():
    LOG.debug('Getting hashtable')
    from bw_plex.audfprint.hash_table import HashTable

    # Patch HashTable.
    try:
        import cPickle as pickle
    except ImportError:
        import pickle
    import gzip

    def load(self, name=None):
        if name is None:
            self.__filename = name

        self.load_pkl(name)
        LOG.debug('Files in the hashtable')
        for n in self.names:
            LOG.debug(n)

        return self

    def save(self, name=None, params=None, file_object=None):
        LOG.debug('Saving HashTable')
        # Merge in any provided params
        if params:
            for key in params:
                self.params[key] = params[key]

        if file_object:
            f = file_object
            self.__filename = f.name
        else:

            if name is None:
                f = self.__filename
            else:
                self.__filename = f = name

            f = gzip.open(f, 'wb')

        pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)
        self.dirty = False
        return self

    def has_theme(self, media, add_if_missing=True):
        """Cheaper way to lookup stuff."""
        th = bool(self.get_theme(media))

        if th is False and add_if_missing is True:
            th = download_theme(media, self)

        if th:
            return True

        return False

    def get_theme(self, media):
        if media.TYPE == 'show':
            name = media.title
            rk = media.ratingKey
        else:
            rk = media.grandparentRatingKey
            name = media.grandparentTitle

        d = self.get_themes().get(rk, [])
        LOG.debug('%s has %s themes', name, len(d))

        return d

    def get_themes(self):
        d = defaultdict(list)
        for n in self.names:
            try:
                rk = os.path.basename(n).split('__')[1]
                d[int(rk)].append(n)
            except (IndexError, TypeError):
                LOG.exception('Some crap happend with %s', n)
        return d

    HashTable.save = save
    HashTable.load = load
    HashTable.has_theme = has_theme
    HashTable.get_themes = get_themes
    HashTable.get_theme = get_theme

    if os.path.exists(FP_HASHES):
        LOG.info('Loading existing files in db')
        HT = HashTable(FP_HASHES)
        HT.__filename = FP_HASHES

    else:
        LOG.info('Creating new hashtable db')
        HT = HashTable()
        HT.__filename = FP_HASHES
        HT.save(FP_HASHES)
        HT.load(FP_HASHES)

    return HT


def download_subtitle(episode):

    episode.reload()
    LOG.debug('Downloading subtitle from PMS')
    pms = episode._server
    to_dl = []
    all_subs = []

    for part in episode.iterParts():
        if part.subtitleStreams():
            for sub in part.subtitleStreams():
                if sub.key and sub.codec in FILE_EXTENSION_TO_FORMAT_IDENTIFIER.values():
                    to_dl.append(pms.url('%s?download=1' % sub.key, includeToken=True))

    for dl_url in to_dl:
        r = episode._server._session.get(dl_url)
        r.raise_for_status()
        if r:
            try:
                subt = [sub for sub in SSAFile.from_string(r.text, encoding=r.encoding)]
                all_subs.append(subt)
            except (IOError, pysubs2.exceptions.UnknownFPSError,
                    pysubs2.exceptions.UnknownFormatIdentifierError,
                    pysubs2.exceptions.FormatAutodetectionError):
                LOG.exception('Failed to parse subtitle')

    return all_subs


def to_sec(t):
    try:
        m, s = t.split(':')
        return int(m) * 60 + int(s)
    except:
        return int(t)


def has_recap_subtitle(episode, phrase):
    if not phrase:
        LOG.debug('There are no phrase, add a phrase in your config to check for recaps.')
        return False

    LOG.debug('Checking if %s has a recap with phrase %s using subtitles',
              episode._prettyfilename(), ', '.join(phrase))

    subs = download_subtitle(episode)
    pattern = re.compile(u'|'.join([re.escape(p) for p in phrase]), re.IGNORECASE)

    for sub in subs:
        for line in sub:
            if re.search(pattern, line.text):
                LOG.debug('%s matched %s in subtitles', ', '.join(phrase), line.text)
                return True

    return False


def has_recap(episode, phrase, audio=None):
    subs = has_recap_subtitle(episode, phrase)

    if subs:
        return True

    if audio:
        audio_recap = has_recap_audio(audio)
        if audio_recap:
            return True

    return False


def choose(msg, items, attr):
    result = []

    if not len(items):
        return result

    click.echo('')
    for i, item in reversed(list(enumerate(items))):
        name = attr(item) if callable(attr) else getattr(item, attr)
        click.echo('%s %s' % (i, name))

    click.echo('')

    while True:
        try:
            inp = click.prompt('%s' % msg)
            if any(s in inp for s in (':', '::')):
                idx = slice(*map(lambda x: int(x.strip()) if x.strip() else None, inp.split(':')))
                result = items[idx]
                break
            elif ',' in inp:
                ips = [int(i.strip()) for i in inp.split(',')]
                result = [items[z] for z in ips]
                break

            else:
                result = items[int(inp)]
                break

        except(ValueError, IndexError):
            pass

    if not isinstance(result, list):
        result = [result]

    return result


def check_real_file_access(path):
    if os.path.exists(path):
        return path

    for key, value in CONFIG.get('remaps', {}).items():
            fp = path.replace(key, value)
            if os.path.exists(fp):
                return fp



if __name__ == '__main__':
    # print(search_tunes('Dexter', 1))
    print(find_offset_ffmpeg(r'X:\Breaking bad\Season 05\breaking.bad.s05e02.720p.hdtv.x264-orenji.mkv'))
