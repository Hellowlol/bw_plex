#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division

import os
import re
import subprocess
import tempfile
import shutil
import time
import itertools
import unicodedata

from collections import defaultdict

from profilehooks import timecall
import requests
from bs4 import BeautifulSoup

from plexapi.utils import download

from bw_plex import THEMES, CONFIG, LOG, FP_HASHES


def get_pms(url=None, token=None, username=None,
            password=None, servername=None, verify_ssl=None):
    from plexapi.myplex import MyPlexAccount
    from plexapi.server import PlexServer

    url = url or CONFIG.get('url')
    token = token or CONFIG.get('token')
    verify_ssl = verify_ssl or CONFIG.get('verify_ssl', False)

    if url and token:
        sess = requests.Session()
        if not verify_ssl:
            sess.verify = False
        PMS = PlexServer(url, token, sess)

    elif username and password and servername:
        acc = MyPlexAccount(username, password)
        PMS = acc.resource(servername).connect()

    LOG.debug('Getting server %s', PMS.friendlyName)

    return PMS


def find_next(media):
    """Find what ever you have that is next ep."""
    LOG.debug('Check if we can find the next media item.')
    eps = media.show().episodes()

    for ep in eps:
        if ep.seasonNumber >= media.seasonNumber and ep.index > media.index:
            LOG.debug('Found %s', ep._prettyfilename())
            return ep

    LOG.debug('Failed to find the next media item of %s'.media.grandparentTitle)


def download_theme_plex(media, force=False):
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

    name = '%s__%s__%s' % (re.sub('[\'\"\\\/;,-]+', '', name), rk, int(time.time()))  # make a proper cleaning in misc.
    f_name = '%s.mp3' % name
    f_path = os.path.join(THEMES, f_name)

    if not os.path.exists(f_path) or force and theme:
        LOG.debug('Downloading %s', f_path)
        dlt = download(PMS.url(theme, includeToken=True), savepath=THEMES, filename=f_name)

        if dlt:
            SHOWS[rk] = f_path
            return f_path
    else:
        LOG.debug('Skipping %s as it already exists', f_name)

    return f_path


def to_time(sec):
    if sec == -1:
        return '00:00'

    m, s = divmod(sec, 60)
    return '%02d:%02d' % (m, s)


def sec_to_hh_mm_ss(sec):
    return time.strftime('%H:%M:%S', time.gmtime(sec))


def analyzer():
    from bw_plex.audfprint.audfprint_analyze import Analyzer

    a = Analyzer()
    a.n_fft = 512
    a.n_hop = a.n_fft // 2
    a.shifts = 4
    a.fail_on_error = False
    a.density = 20
    return a

def matcher():
    from bw_plex.audfprint.audfprint_match import Matcher
    m = Matcher()
    m.find_time_range = True
    m.search_depth = 2000
    m.verbose = True
    m.exact_count = True
    # m.time_quantile = 0.02
    # This need to be high as we might get to many hashes before
    # we have found the end.
    m.max_alignments_per_id = 10000
    # m.sort_by_time = True
    return m


#@timecall(immediate=True)
def get_offset_end(vid, hashtable, check_if_missing=False):
    an = analyzer()
    match = matcher()
    start_time = -1
    end_time = -1

    t_hop = an.n_hop / float(an.target_sr)
    rslts, dur, nhash = match.match_file(an, hashtable, vid, 1) # The number does not matter...

    for (tophitid, nhashaligned, aligntime,
         nhashraw, rank, min_time, max_time) in rslts:
            end_time = max_time * t_hop
            start_time = min_time * t_hop
            LOG.info('Match %s rank %s theme song %s started at %s (%s) in ended at %s (%s)' % (tophitid, rank, hashtable.names[tophitid], start_time, to_time(start_time),
                                                                               end_time, to_time(end_time)))

    if rslts:
        best = rslts[0]
        end_time = best[6] * t_hop
        start_time = best[5] * t_hop
        LOG.debug('Best match was %s', hashtable.names[best[0]])
        return start_time, end_time

    LOG.debug('no result just returning -1')

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
            if video[1] > cutoff:  # end time of black shit..
                # if silence is within black shit its ok. Allow dev sec deviance.
                if aud and video and abs(aud[0] - video[0]) <= dev and abs(aud[1] - video[0]) <= dev:
                    match_window.append(video)

    if not match_window and not final_audio and final_video:
        LOG.debug('There are no audio silence at all, taking a stab in the dark.')
        try:
            return list(sorted([i for i in final_video if i[0] >= 30 and i[1] >= 396], key=lambda k: k[2]))[0][0]
        except IndexError:
            return -1

    if match_window:
        try:
            m = list(sorted(match_window, key=lambda k: (k[1], k[2])))
            LOG.debug('Matching windows are %s', to_time_range(m))
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
            except:
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


def convert_and_trim(afile, fs=8000, trim=None, theme=False, filename=None):
    tmp = tempfile.NamedTemporaryFile(mode='r+b',
                                      prefix='offset_',
                                      suffix='.wav')

    tmp_name = tmp.name
    tmp.close()
    if trim is None:
        cmd = [
            'ffmpeg', '-i', afile, '-ac', '1', '-ar',
            str(fs), '-acodec', 'pcm_s16le', tmp_name
        ]

    else:
        cmd = [
            'ffmpeg', '-i', afile, '-ac', '1', '-ar',
            str(fs), '-ss', '0', '-t', str(trim), '-acodec', 'pcm_s16le',
            tmp_name
        ]

    LOG.debug('calling ffmpeg with %s' % ' '.join(cmd))

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    o, e = psox.communicate()

    if not psox.returncode == 0:
        LOG.exception(e)
        raise Exception("FFMpeg failed")

    # Check if we passed a url.
    if '://' in afile and filename:
        filename = filename + '.wav'
        afile = os.path.join(THEMES, filename)

    if theme:
        shutil.move(tmp_name, afile)
        LOG.debug('Done converted and moved %s to %s' % (afile, THEMES))
        return afile
    else:
        LOG.debug('Done converting %s', tmp_name)
        return tmp_name


def convert_and_trim_to_mp3(afile, fs=8000, trim=None, outfile=None):
    if outfile is None:
        tmp = tempfile.NamedTemporaryFile(mode='r+b', prefix='offset_',
                                          suffix='.mp3')
        tmp_name = tmp.name
        tmp.close()
        outfile = tmp_name

    cmd = ['ffmpeg', '-i', afile, '-ss', '0', '-t',
           str(trim), '-codec:a', 'libmp3lame', '-qscale:a', '6', outfile]

    LOG.debug('calling ffmepg with %s' % ' '.join(cmd))

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)

    o, e = psox.communicate()
    if not psox.returncode == 0:
        print(e)
        raise Exception("FFMpeg failed")

    return outfile

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

        except:
            LOG.exception('Failed to download theme song %s' % name)
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

    if theme_source is None:
        theme_source = CONFIG.get('theme_source', 'plex')

    if theme_source == 'youtube':
        theme = search_for_theme_youtube(name, rk, THEMES, url=url)

    elif theme_source == 'tvtunes':
        theme = search_tunes(name, rk, url=url)
        theme = list(itertools.chain.from_iterable(theme.values()))

    elif theme_source == 'plex':
        theme = pms.url(_theme, includeToken=True)
        LOG.debug('Downloading theme via plex %s' % theme)

    elif theme_source == 'all':
        theme = []
        st = search_tunes(name, rk, url=url)
        st_res = list(itertools.chain.from_iterable(st.values()))
        theme.extend(st_res)
        theme.append(pms.url(_theme, includeToken=True))
        theme.append(search_for_theme_youtube(name, rk, THEMES, url=url))

    if not isinstance(theme, list):
        theme = [theme]

    final = []
    for th in theme:
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
                LOG.exception('Some crap happend with', n)
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
    import srt
    episode.reload()
    pms = episode._server
    to_dl = []
    all_subs = []

    for part in episode.iterParts():
        if part.subtitleStreams():
            for sub in part.subtitleStreams():
                if sub.key and sub.codec == 'srt':
                    to_dl.append(pms.url('%s?download=1' % sub.key, includeToken=True))

    for dl_url in to_dl:
        r = requests.get(dl_url)
        r.raise_for_status()
        if r:
            try:
                a_sub = list(srt.parse(r.text))
                all_subs.append(a_sub)
            except ValueError:
                LOG.exception('Failed to parse subtitle')

    return all_subs


def to_sec(t):
    try:
        m, s = t.split(':')
        return int(m) * 60 + int(s)
    except:
        return int(t)


def has_recap_audio(audio, phrase=None, thresh=1, duration=30):
    """ audio is wave in 16k sample rate."""
    import speech_recognition as sr

    if phrase is None:
        phrase = CONFIG.get('words')

    try:
        r = sr.Recognizer()
        with sr.AudioFile(audio) as source:
            r.adjust_for_ambient_noise(source)
            audio = r.record(source, duration=duration)
            result = r.recognize_sphinx(audio, keyword_entries=[(i, thresh) for i in phrase])
            LOG.debug('Found %s in audio', result)
            return result.strip()

    except sr.UnknownValueError:
        pass

    return False


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
            if re.search(pattern, line.content):
                LOG.debug('%s matched %s in subtitles', ', '.join(phrase), line.content)
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
    import click
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
            if any(s in inp for s in (':', '::', '-')):
                idx = slice(*map(lambda x: int(x.strip()) if x.strip() else None, inp.split(':')))
                result = items[idx]
                break
            elif ',' in inp:
                ips = [int(i.strip()) for i in inp.split()]
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


if __name__ == '__main__':
    #print(search_tunes('Dexter', 1))
    print(find_offset_ffmpeg(r'X:\Breaking bad\Season 05\breaking.bad.s05e02.720p.hdtv.x264-orenji.mkv'))

