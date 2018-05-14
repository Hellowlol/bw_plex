from __future__ import division

import glob
import os
import subprocess
import re
import sys

import click
import numpy as np

from bw_plex import LOG
from bw_plex.misc import sec_to_hh_mm_ss


color = {'yellow': (255, 255, 0),
         'red': (255, 0, 0),
         'blue': (0, 0, 255),
         'lime': (0, 255, 0),
         'white': (255, 255, 255),
         'fuchsia': (255, 0, 255)
        }

image_type = ('.png', '.jpeg', '.jpg')

if sys.version_info > (3, 0):
    basestring = str


def make_imgz(afile, start=600, dest=None, fps=1):
    """Helper to generate images."""

    dest_path = dest + '\out%d.png'
    fps = 'fps=%s' % fps
    t = sec_to_hh_mm_ss(start)

    cmd = [
        'ffmpeg', '-ss', t, '-i',
        afile, '-vf', fps, dest_path
    ]

    # fix me
    subprocess.call(cmd)
    print(dest)
    return dest


def extract_text(img, lang='eng', encoding='utf-8'):
    import pytesseract
    try:
        import Image
    except ImportError:
        from PIL import Image

    if isinstance(img, basestring):
        img = Image.open(img)

    return pytesseract.image_to_string(img, lang=lang).encode(encoding, 'ignore')


def video_frame_by_frame(path, offset=0, frame_range=None, step=1):
    """ Returns a video files frame by frame.by

        Args:
            path (str): path to the video file
            offset (int): Should we start from offset inside vid
            frame_range (list, None): List of frames numbers we should grab.
            step(int): check every n, note this is ignored if frame_range is False

        Returns:
            numpy.ndarray

    """

    import cv2

    cap = cv2.VideoCapture(path)

    if frame_range:
        fps = cap.get(cv2.CAP_PROP_FPS)

        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
        duration = int(duration)
        end = duration
        start = offset

        # Just yield very step frame and currect time.
        frame_range = (i * fps for i in range(start, end, step))
        for fr in frame_range:
            # Set the correct frame number to read.
            cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
            ret, frame = cap.read()
            if ret:
                yield frame, cap.get(cv2.CAP_PROP_POS_MSEC)
            else:
                yield None, cap.get(cv2.CAP_PROP_POS_MSEC)

    else:
        if offset:
            # Set the correct offset point so we
            # dont read shit we dont need.
            fps = cap.get(cv2.CAP_PROP_FPS)
            fn = offset * fps
            cap.set(cv2.CAP_PROP_POS_FRAMES, fn)

        while cap.isOpened():
            ret, frame = cap.read()
            pos = cap.get(cv2.CAP_PROP_POS_MSEC)

            if ret:
                yield frame, pos
            else:
                break

    cap.release()
    cv2.destroyAllWindows()


def calc_success(rectangles, img_height, img_width, success=0.9):
    """Helper to check the n percentage of the image is covered in text."""
    t = sum([i[2] * i[3] for i in rectangles if i])
    p = 100 * float(t) / float(img_height * img_width)
    return p > success


def locate_text(image, debug=False):
    """Locate where and if there are text in the images.

       Args:
            image(numpy.ndarray, str): str would be path to image
            debug(bool): Show each of the images using open cv.

       Returns:
            list of rectangles


    """
    # Mostly ripped from https://github.com/hurdlea/Movie-Credits-Detect
    # Thanks!
    import cv2

    # Compat so we can use a frame and img file..
    if isinstance(image, basestring) and os.path.isfile(image):
        image = cv2.imread(image)

    if debug:
        cv2.imshow('original image', image)

    height, width, depth = image.shape
    mser = cv2.MSER_create(4, 10, 8000, 0.8, 0.2, 200, 1.01, 0.003, 5)
    # Convert to gray.
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if debug:
        cv2.imshow('grey', grey)

    # Pull out grahically overlayed text from a video image
    #blur = cv2.GaussianBlur(grey, (5, 5), 0)
    # test media blur
    blur = cv2.medianBlur(grey, 7)

    if debug:
        cv2.imshow('blur', blur)

    adapt_threshold = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                            cv2.THRESH_BINARY, 5, -25)

    contours, _ = mser.detectRegions(adapt_threshold)

    # for each contour get a bounding box and remove
    rects = []
    for contour in contours:
        # get rectangle bounding contour
        [x, y, w, h] = cv2.boundingRect(contour)

        # Remove small rects
        if w < 2 or h < 2: # 2
            continue

        # Throw away rectangles which don't match a character aspect ratio
        if (float(w * h) / (width * height)) > 0.005 or float(w) / h > 1:
            continue

        rects.append(cv2.boundingRect(contour))

    # Mask of original image
    mask = np.zeros((height, width, 1), np.uint8)
    # To expand rectangles, i.e. increase sensitivity to nearby rectangles
    # Add knobs?
    xscaleFactor = 12  # 12
    yscaleFactor = 3  # 0
    for box in rects:
        [x, y, w, h] = box
        # Draw filled bounding boxes on mask
        cv2.rectangle(mask, (x - xscaleFactor, y - yscaleFactor),
                      (x + w + xscaleFactor, y + h + yscaleFactor),
                      color['white'], cv2.FILLED)
    if debug:
        cv2.imshow("Mask", mask)

    # Find contours in mask if bounding boxes overlap,
    # they will be joined by this function call
    rectangles = []
    contours = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    for contour in contours[1]:

        # Only preserve "squarish" features
        #peri = cv2.arcLength(contour, True)
        #approx = cv2.approxPolyDP(contour, 0.01 * peri, True)

        # the contour is 'bad' if it is not a rectangluarish
        # This doesnt have to be bad, since we match more then one char.
        #if len(approx) > 8:
        #    cv2.drawContours(image, [contour], -1, color['lime'])
        #    if debug:
        #        cv2.imshow("bad Rectangles check lime", image)
        #    continue

        rect = cv2.boundingRect(contour)

        x, y, w, h = rect
        cv2.rectangle(image, (x, y), (x + w, y + h), color['blue'], 2)

        # Remove small areas and areas that don't have text like features
        # such as a long width.
        if ((float(w * h) / (width * height)) < 0.006):
            # remove small areas
            if float(w * h) / (width * height) < 0.0018:
                continue

            # remove areas that aren't long
            if (float(w) / h < 2.5):
                continue

        else:
            # General catch for larger identified areas that they have
            # a text width profile
            if float(w) / h < 1.8:
                continue

        rectangles.append(rect)

        cv2.rectangle(image, (x, y), (x + w, y + h), color['fuchsia'], 2)

    if debug:
        cv2.imshow("Final image", image)
        cv2.waitKey(0)

    return rectangles


def find_credits(path, offset=0, fps=None, duration=None, check=7, step=1, frame_range=True):
    """Find the start/end of the credits and end in a videofile.
       This only check frames so if there is any silence in the video this is simply skipped as
       opencv only handles videofiles.

       use frame_range to so we only check frames every 1 sec.

       # TODO just ffmepg to check for silence so we calculate the correct time? :(

       Args:
            path (str): path to the videofile
            offset(int): If given we should start from this one.
            fps(float?): fps of the video file
            duration(None, int): Duration of the vfile in seconds.
            check(int): Stop after n frames with text, set a insane high number to check all.
                        end is not correct without this!
            step(int): only use every n frame
            frame_range(bool). default true, precalc the frames and only check thous frames.

       Returns:
            1, 2


    """
    import cv2
    frames = []
    start = -1
    end = -1
    LOG.debug('Trying to find the credits for %s', path)

    if fps is None:
        # we can just grab the fps from plex.
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()

    for i, (frame, millisec) in enumerate(video_frame_by_frame(path, offset=offset,
                                                               step=step, frame_range=frame_range)):
        LOG.debug('progress %s', millisec / 1000)
        if frame is not None:
            recs = locate_text(frame, debug=False)

            if recs:
                frames.append(millisec)

            if len(frames) >= check:
                break

    if frames:
        LOG.debug(frames)
        start = min(frames) / 1000
        end = max(frames) / 1000

    return start, end


@click.command()
@click.argument('path')
@click.option('-c', type=float, default=0.0)
@click.option('-d', '--debug', is_flag=True, default=False)
@click.option('-p', '--profile', is_flag=True, default=False)
@click.option('-o', '--offset', default=0, type=int)
def cmd(path, c, debug, profile, offset):

    if os.path.isfile(path):
        files = [path]
    else:
        files = glob.glob(path)

    d = {}
    print(files)

    for f in files:
        if f.endswith(image_type):
            filename = os.path.basename(f)
            hit = re.search(r'(\d+)', filename)

            t = locate_text(f, debug=debug)

            if hit:
                d[int(hit.group()) + offset] = (bool(t), filename)
        else:
            t = find_credits(f, offset=offset)

        if c:
            t = calc_success(t, c)

    if d:
        click.echo('Image report')
        for k, v in sorted(d.items()):
            if v[0] is True:
                color = 'green'
            else:
                color = 'red'
            click.secho('%s %s %s %s' % (k, sec_to_hh_mm_ss(k), v[0], v[1]), fg=color)


if __name__ == '__main__':
    cmd()
