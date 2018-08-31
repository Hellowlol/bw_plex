import os

TYPES = {'cut': '0',
         'mute': '1',
         'scene marker': '2',
         'commercial break': '3'}


TYPES.update(dict((v,k) for (k,v) in TYPES.items()))


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
    f_without_ext = os.path.splitext(path)[0]
    edl_path = f_without_ext + '.edl'
    return edl_path


def has_edl(path):

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
    path = create_edl_path(path)
    with open(path, 'w') as f:
        for line in lines:
            f.write('%s' % '    '.join(str(i) for i in line))

    return path

