#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import re
import subprocess
import tempfile

from collections import defaultdict

import requests
from profilehooks import timecall
from bs4 import BeautifulSoup

from audfprint.audfprint_match import Matcher
from audfprint.audfprint_analyze import Analyzer

LOG = logging.getLogger(__name__)


def to_time(sec):
    m, s = divmod(sec, 60)
    return '%02d:%02d' % (m, s)


def analyzer():

    a = Analyzer()
    a.n_fft = 512
    a.n_hop = a.n_fft / 2
    a.shifts = 4
    a.fail_on_error = False
    a.density = 20
    return a


def matcher():
    m = Matcher()
    m.find_time_range = True
    m.search_depth = 2000
    m.verbose = True
    m.max_matches = 100
    #m.exact_count = True
    #m.time_quantile = 0.02
    # This need to be high as we might get to many hashes before
    # we have found the end.
    m.max_alignments_per_id = 10000
    #m.sort_by_time = True
    return m


#@timecall(immediate=True)
def get_offset_end(vid, hashtable):
    an = analyzer()
    match = matcher()

    start_time = -1
    end_time = -1

    t_hop = an.n_hop / float(an.target_sr)
    rslts, dur, nhash = match.match_file(an, hashtable, vid, 1) # The number does not matter...

    for (tophitid, nhashaligned, aligntime,
         nhashraw, rank, min_time, max_time) in rslts:
            #print(tophitid, nhashaligned, aligntime, nhashraw, rank, min_time, max_time)
            end_time = max_time * t_hop
            start_time = min_time * t_hop
            LOG.debug('Started at %s (%s) in ended at %s (%s)' % (start_time, to_time(start_time),
                                                                  end_time, to_time(end_time)))
    return start_time, end_time

    LOG.debug('no result just returning -1')

    return start_time, end_time


def get_valid_filename(s):

    head = os.path.dirname(s)
    tail = os.path.basename(s)

    clean_tail = str(tail).strip()
    clean_tail = re.sub(r'(?u)[^-_\w.() ]', '', clean_tail)

    if head:
        return os.path.join(head, u'%s' % clean_tail)
    else:
        return clean_tail


#@timecall(immediate=True)
def convert_and_trim(afile, fs=8000, trim=None):
    tmp = tempfile.NamedTemporaryFile(
        mode='r+b', prefix='offset_', suffix='.wav')
    tmp_name = tmp.name
    tmp.close()
    if trim is None:
        cmd = [
            'ffmpeg', '-loglevel', 'panic', '-i', afile, '-ac', '1', '-ar',
            str(fs), '-acodec', 'pcm_s16le', tmp_name
        ]
    else:
        cmd = [
            'ffmpeg', '-loglevel', 'panic', '-i', afile, '-ac', '1', '-ar',
            str(fs), '-ss', '0', '-t', str(trim), '-acodec', 'pcm_s16le',
            tmp_name
        ]

    LOG.debug('calling ffmepg with %s' % ' '.join(cmd))

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    o, e = psox.communicate()
    if not psox.returncode == 0:
        print(e)
        raise Exception("FFMpeg failed")

    return tmp_name


#@timecall(immediate=True)
def convert_and_trim_to_mp3(afile, fs=8000, trim=None, outfile=None):
    if outfile is None:
        tmp = tempfile.NamedTemporaryFile(mode='r+b', prefix='offset_',
                                          suffix='.mp3')
        tmp_name = tmp.name
        tmp.close()
        outfile = tmp_name

    cmd = ['ffmpeg', '-i', afile, '-ss', '0', '-t',
           str(trim), '-codec:a', 'libmp3lame', '-qscale:a', '6', outfile]

    print('calling ffmepg with %s' % ' '.join(cmd))

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)

    o, e = psox.communicate()
    if not psox.returncode == 0:
        print(e)
        raise Exception("FFMpeg failed")

    return outfile



def search_tunes(name, rk):
    # Pretty much everything is solen from https://github.com/robwebset/script.tvtunes/blob/master/resources/lib/themeFetcher.py
    # Thanks!
    baseurl = 'http://www.televisiontunes.com'
    res = requests.get('http://www.televisiontunes.com/search.php', params={'q': name})
    result = defaultdict(list)
    if res:
        soup = BeautifulSoup(res.text, 'html5lib')

        search_results = soup.select('div.jp-title > ul > li > a')
        if search_results:
            for sr in search_results:
                # Since this can be may shows lets atleast try to get the correct one.
                sname = sr.text.strip()
                if sname == name:
                    result['%s__%s' % (name, rk)].append(baseurl + sr['href'])

    if result:
        # Find the real download url.
        fin_res = {}
        final_urls = []
        for k, v in result.items():

            for item in v:
                res2 = requests.get(item)
                if res2:
                    sub_soup = BeautifulSoup(res2.text, 'html5lib')

                    link = sub_soup.find('a', id='download_song')
                    final_urls.append(baseurl + link['href'])

        # this is buggy fix me plx
        fin_res[k] = final_urls

    return fin_res


def search_for_theme_youtube(name, rk=1337, save_path=None):
    import youtube_dl

    if save_path is None:
        save_path = os.getcwd()

    fp = os.path.join(save_path, '%s__%s__' % (name, rk))
    fp = get_valid_filename(fp)
    # Youtuble dl requires the template to be unicode.
    t = u'%s' % fp

    ydl_opts = {
        'verbose': True,
        'outtmpl': t + u'%(autonumber)s.%(ext)s',
        'default_search': 'ytsearch',
        'format': 'bestaudio',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        #'logger': LOG,
    }

    ydl = youtube_dl.YoutubeDL(ydl_opts)

    #def nothing(*args, **kwargs):
    #    pass

    #ydl.to_screen = nothing

    with ydl:
        try:
            ydl.download([name + ' theme song'])
            return t
        except:
            LOG.exception('Failed to download theme song %s' % name)

    return fp


if __name__ == '__main__':
    def zomg():
        print('zomg')
        ht = '' # path to db
        fp = '' # path to wav.
        from audfprint.hash_table import HashTable
        HT = HashTable(ht)
        n = get_offset_end(fp, HT)
        print(n)

    #search_for_theme_youtube('solsidan')
    #search_tunes('Dexter', 1)
