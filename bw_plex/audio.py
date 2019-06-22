import os
import shutil
import subprocess
import tempfile


from bw_plex import THEMES, CONFIG, LOG, FP_HASHES

# Try to import the optional package.
try:
    import speech_recognition
except ImportError:
    speech_recognition = None
    LOG.warning('Failed to import speech_recognition this is required to check for recaps in audio. '
                'Install the package using pip install bw_plex[audio] or bw_plex[all]')


def convert_and_trim(afile, fs=8000, trim=None, theme=False, filename=None):
    tmp = tempfile.NamedTemporaryFile(mode='r+b',
                                      prefix='offset_',
                                      suffix='.wav')

    tmp_name = tmp.name
    tmp.close()
    tmp_name = "%s" % tmp_name

    if os.name == 'nt' and '://' not in afile:
        q_file = '"%s"' % afile
    else:
        q_file = afile

    if trim is None:
        cmd = [
            'ffmpeg', '-i', q_file, '-ac', '1', '-ar',
            str(fs), '-acodec', 'pcm_s16le', tmp_name
        ]

    else:
        cmd = [
            'ffmpeg', '-i', q_file, '-ac', '1', '-ar',
            str(fs), '-ss', '0', '-t', str(trim), '-acodec', 'pcm_s16le',
            tmp_name
        ]

    LOG.debug('calling ffmpeg with %s' % ' '.join(cmd))

    if os.name == 'nt':
        cmd = '%s' % ' '.join(cmd)

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    o, e = psox.communicate()

    if not psox.returncode == 0:  # pragma: no cover
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


def convert_and_trim_to_mp3(afile, fs=8000, trim=None, outfile=None):  # pragma: no cover
    if outfile is None:
        tmp = tempfile.NamedTemporaryFile(mode='r+b', prefix='offset_',
                                          suffix='.mp3')
        tmp_name = tmp.name
        tmp.close()
        outfile = tmp_name
        outfile = "%s" % outfile

    if os.name == 'nt' and '://' not in afile:
        q_file = '"%s"' % afile
    else:
        q_file = afile

    cmd = ['ffmpeg', '-i', q_file, '-ss', '0', '-t',
           str(trim), '-codec:a', 'libmp3lame', '-qscale:a', '6', outfile]

    LOG.debug('calling ffmepg with %s' % ' '.join(cmd))

    if os.name == 'nt':
        cmd = '%s' % ' '.join(cmd)

    psox = subprocess.Popen(cmd, stderr=subprocess.PIPE)

    o, e = psox.communicate()
    if not psox.returncode == 0:
        raise Exception("FFMpeg failed %s" % e)

    return outfile


def has_recap_audio(audio, phrase=None, thresh=1, duration=30):
    """ audio is wave in 16k sample rate."""
    if speech_recognition is None:
        return False

    if phrase is None:
        phrase = CONFIG['tv'].get('words', [])

    try:
        r = speech_recognition.Recognizer()
        with speech_recognition.AudioFile(audio) as source:
            r.adjust_for_ambient_noise(source)
            audio = r.record(source, duration=duration)
            result = r.recognize_sphinx(audio, keyword_entries=[(i, thresh) for i in phrase])
            LOG.debug('Found %s in audio', result)
            return result.strip()

    except speech_recognition.UnknownValueError:
        pass

    return False
