import os

TYPES = {'cut': '0',
         'mute': '1',
         'scene marker': '2',
         'commercial break': '3'}


TYPES.update(dict((v,k) for (k,v) in TYPES.items()))


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
    for root, dirs, files in os.walk(path):
        for fil in files:
            if fil.endswith('.edl'):
                fp = os.path.join(root, fil)
                edls.append(fp)

    return edls


def create_edl_path(path):
    """Convert a file with a ext to .edl ext."""
    f_without_ext = os.path.splitext(path)[0]
    edl_path = f_without_ext + '.edl'
    return edl_path


def has_edl(path):
    """Check if we have a edl with the same name as the file."""

    # check that we has access to the file incase bw_plex doesnt use the same
    # source mapping as bw_plex (running in a docker or what evs)
    if not os.path.exists(path):
        pass
        # do remapping here
        # TODO
    # Check the the video file exist.
    if os.path.isfile(path):
        edl_path = create_edl_path(path)

        # Lets check if the edl exists if does we should edit it.

        if os.path.isfile(edl_path):
            # edit the damn edl
            return True
        else:
            return False

    return False


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
    with open(path, 'w') as f:
        for line in lines:
            f.write('%s' % '    '.join(str(i) for i in line))

    return path

