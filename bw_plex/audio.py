import errno
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict

from bw_plex import CONFIG, LOG, MEMORY, THEMES

# Try to import the optional package.
try:
    import speech_recognition
except ImportError:
    speech_recognition = None
    LOG.warning('Failed to import speech_recognition this is required to check for recaps in audio. '
                'Install the package using pip install bw_plex[audio] or bw_plex[all]')


FPCALC_ENVVAR = "fpcalc"


def find_files(path, ext=None):
    if ext is None:
        ext = (".mkv",)

    fs = []
    for root_, dirs, files in os.walk(path):
        for f in files:
            # print(f)
            fp = os.path.join(root_, f)
            if fp.endswith(ext):
                fs.append(fp)
    return fs


def convert_and_trim(afile, fs=8000, trim=None, theme=False, filename=None):
    tmp = tempfile.NamedTemporaryFile(mode='r+b',
                                      prefix='offset_',
                                      suffix='.wav')

    tmp_name = tmp.name
    tmp.close()
    tmp_name = "%s" % tmp_name

    if os.name == 'nt' and not afile.startswith(("http", "https")):
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
    _, e = psox.communicate()

    if not psox.returncode == 0:  # pragma: no cover
        LOG.exception(e)
        raise Exception("FFMpeg failed")

    # Check if we passed a url.
    if afile.startswith(("http", "https")) and filename:
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
    """Convert a file to mp3 in fs sample rate."""
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


def create_raw_fp(path, maxlength=600):
    fpcalc = os.environ.get(FPCALC_ENVVAR, "fpcalc")
    #command = [fpcalc, "-raw", "-overlap", "-length", str(maxlength), "%s" % path]

    def run_cmd(path):
        command = [fpcalc, "-raw", "-length", str(maxlength), "%s" % path]
        LOG.debug(' '.join(command))
        try:
            with open(os.devnull, "wb") as devnull:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=devnull)
                output, _ = proc.communicate(timeout=120)
                return output
        except subprocess.TimeoutExpired:
            proc.kill()
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise NoBackendError("fpcalc not found")

    output = run_cmd(path)

    def parse_output(output, path):
        duration = fp = None
        for line in output.splitlines():
            try:
                parts = line.split(b"=", 1)
            except ValueError:
                return "malformed fpcalc output"
            if parts[0] == b"DURATION":
                try:
                    duration = float(parts[1])
                except ValueError:
                    return "shit"
            elif parts[0] == b"FINGERPRINT":
                fp = parts[1]

        if duration is None or fp is None:
            # THis can fail if audio is dts so some other crappy shit.
            return "missing fpcalc output for %s" % path

        dur = float(duration)
        hashes = [int(i) for i in fp.split(b",")]
        return (dur, hashes, len(hashes) / maxlength)

    if output is None:
        LOG.debug("Failed to ZOMG")

    out = parse_output(output, path)
    if out is None:
        return

    if isinstance(out, tuple):
        return out
    else:
        LOG.debug("Failed to read the video %s file directly, converting to .wav and retrying", path)
        temp_wave = convert_and_trim(path, trim=maxlength)
        output = run_cmd(temp_wave)
        out = parse_output(output, temp_wave)
        if isinstance(out, tuple):
            # Do some clean up.
            try:
                os.remove(temp_wave)
            except:
                pass
            return out
        else:
            return "crap" # <- fix me


def create_audio_fingerprint_from_folder(path, ext=None):
    """Create finger print for a folder"""
    # https://oxygene.sk/2011/01/how-does-chromaprint-work/
    if isinstance(path, list):
        fs = path
    else:
        fs = find_files(path, ext)

    result = defaultdict(dict)

    for file_to_check in fs:
        try:
            duration, fp, hps = MEMORY.cache(create_raw_fp)(file_to_check)
            result[file_to_check] = {
                "duration": duration,
                "fp": fp,
                "id": file_to_check,
                "hps": hps
            }

        except ValueError:
            #  Just print the error from fpcalc for now, need to improve this
            x = create_raw_fp(file_to_check)
            print(x)
            continue

    return result



if __name__ == "__main__":
    pass

    """"
    data =


    """
