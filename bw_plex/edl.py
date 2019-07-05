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
    elds = []

    # Add credits
    if (item.correct_theme_start and
        item.correct_theme_start != -1 and
        item.correct_theme_end and
        item.correct_theme_end != -1):

        elds.append([item.correct_theme_start,
                     item.correct_theme_end,
                     TYPES[type]])

    elif (item.theme_start and
          item.theme_start != -1 and
          item.theme_end and
          item.theme_end != -1):

        elds.append([item.theme_start,
                     item.theme_end,
                     TYPES[type]])

    if (item.credits_start and
        item.credits_start != -1 and
        item.credits_end and
        item.credits_end != -1):

        elds.append([item.credits_start,
                     item.credits_end,
                     TYPES[type]])

    return elds


def dir_has_edl(path):
    """reuse all folders in root to check if edl exists returns
       a list off all edls or a empty list"""
    edls = []
    for root, _, files in os.walk(path):
        for fil in files:
            if fil.endswith('.edl'):
                fp = os.path.join(root, fil)
                edls.append(fp)

    return edls


def create_edl_path(path):
    """Convert a file with a ext to .edl ext."""
    from bw_plex import CONFIG
    if not os.path.exists(path):
        for key, value in CONFIG.get('remaps'):
                fp = path.replace(key, value)
                if os.path.exists(fp):
                    path = fp
                    break

    f_without_ext = os.path.splitext(path)[0]
    edl_path = f_without_ext + '.edl'
    return edl_path


def has_edl(path):
    """Check if we have a edl with the same name as the file."""
    # Check the the video file exist.
    if os.path.isfile(path):
        edl_path = create_edl_path(path)

        # Lets check if the edl exists if does we should edit it.
        if os.path.isfile(edl_path):
            # edit the damn edl
            return edl_path
        else:
            return ''

    return ''


def write_edl(path, lines):
    """Write a edl file.

       path(str): path,
       lines(list): [[1,2,3]]

       return:
            path.

    """
    if not len(lines):
        return

    path = create_edl_path(path)
    try:
        with open(path, 'w+') as f:
            for line in lines:
                f.write('%s\n' % '    '.join(str(i) for i in line))

        return path
    except FileNotFoundError:
        LOG.error('Failed to write edl. Try adding a adding curret path to remaps in config')


def edl_to_metadata_file(path):
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

    with open(path, 'rb') as e:
        lines = e.readlines()
        lines = [i.split() for i in lines if i]

    with open(meta_name, 'w') as mf:
        last_en = len(lines) - 1
        mf.write(header)
        for en, l in enumerate(lines):
            if en == 0:
                title = 'first'
            elif en == last_en:
                title = 'last'
            else:
                title = ''

            mf.write(chapter_template % (int(l[0]) * 1000, int(l[1]) * 1000, title))

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
    if input_edl is None:
        input_edl = has_edl(path)

    mf_file = edl_to_metadata_file(input_edl)
    mf_file = str(mf_file)

    outfile, ext = os.path.splitext(path)
    outfile = outfile + '__bw_plex_meta' + ext

    cmd = ['ffmpeg', '-i', path, '-i', mf_file, '-map_metadata', '1', '-codec', 'copy', outfile]

    proc = subprocess.Popen(cmd)
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

    return path


if __name__ == '__main__':
    edl_to_metadata_file(r'C:\Users\alexa\.config\bw_plex\test.edl')
