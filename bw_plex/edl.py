import os
import shutil
import subprocess
import time

from bw_plex import LOG


TYPES = {'cut': 0,
         'mute': 1,
         'scene marker': 2,
         'commercial break': 3}


TYPES.update(dict((v, k) for (k, v) in TYPES.items()))


def db_to_edl(item, type=3):
    elds = {}

    if (item.correct_theme_start and
        item.correct_theme_start != -1 and
        item.correct_theme_end and
        item.correct_theme_end != -1):

        elds["manual intro"] = [item.correct_theme_start, item.correct_theme_end, TYPES[type]]
        elds["manual intro end"] = [item.correct_theme_end, item.correct_theme_end, 2]

    elif (item.theme_start and
          item.theme_start != -1 and
          item.theme_end and
          item.theme_end != -1):

        elds["intro"] = [item.theme_start, item.theme_end, TYPES[type]]
        elds["intro end"] = [item.theme_end, item.theme_end, 2]
    if (item.credits_start and
        item.credits_start != -1 and
        item.credits_end and
        item.credits_end != -1):

        elds["credits"] = [item.credits_start, item.credits_end, TYPES[type]]
        elds["credits end"] = [item.credits_end, item.credits_end, 2]

    return elds


def edl_dict_to_metadata_file(path, eld):
    """Convert a .edl file to a ffmepg metadata file.
       This way we can add chapters to shows as this isnt suppored by plex

       Args:
            path (str): path to the edl we should use.

       Return
            path to metadata file.
    """
    # Should we check if this file has metadata/chapters so we dont overwrite it
    # Lets come back to this later.
    #if not os.path.isfile(path) and path.endswith('.edl'):
    #    return
    header = ';FFMETADATA1\ntitle=%s\nartist=Made by bw_plex\n\n' % os.path.splitext(os.path.basename(path))[0]

    chapter_template = """[CHAPTER]\nTIMEBASE=1/1000\nSTART=%s\nEND=%s\ntitle=%s\n\n"""

    meta_name = os.path.splitext(path)[0] + '.metadata'

    with open(meta_name, 'w') as mf:
        mf.write(header)
        for key, value in eld.items():
            mf.write(chapter_template % (float(value[0]) * 1000, float(value[1]) * 1000, key))

    LOG.debug('Created a metadatafile %s', meta_name)

    return meta_name


def write_chapters_to_file(path, input_edl=None, replace=True, cleanup=True):
    """Use ffmpeg to add chapters to a videofile.mf_file


       Args:
            path(str): path to the video file we should add chapters to
            input_edl (str): path the the edl.
            replace (bool): Default True
            cleanup(bool): Default False, remove the .metadatafile
                           after chapters has been added.

       Return:
            path


    """

    if 'https://' or 'http://' in path:
        LOG.debug("Can't add chapters to as we dont have access to the file on the file system")

    mf_file = edl_dict_to_metadata_file(path, input_edl)
    mf_file = str(mf_file)

    outfile, ext = os.path.splitext(path)
    outfile = outfile + '__bw_plex_meta' + ext

    cmd = ['ffmpeg', '-i', path, '-i', mf_file, '-map_metadata', '1', '-codec', 'copy', outfile]

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    code = proc.wait()
    if code != 0:
        LOG.debug('Failed to write_chapters_to_file %s', code)

    # Try to replace the orginal with the one with have added
    # chapters too.
    if replace:
        for _ in range(3):
            try:
                shutil.move(outfile, path)
                break
            except OSError:
                time.sleep(1)

    if cleanup:
        os.remove(mf_file)
        LOG.debug('Deleted %s', mf_file)

    LOG.debug('writing chapters to file using command %s', ' '.join(cmd))

    return path
