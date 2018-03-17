
import glob
import os

import click
from profilehooks import timecall
from bwplex.misc import sec_to_hh_mm_ss


color = {'yellow': (255, 255, 0),
         'red': (255, 0, 0),
         'blue': (0, 0, 255),
         'lime': (0, 255, 0),
         'white': (255, 255, 255),
         'fuchsia': (255, 0 , 255)

    }


def make_imgz(afile, start=600, every=1):
    import subprocess

    t = sec_to_hh_mm_ss(start)

    cmd = [
        'ffmpeg', '-ss', t, '-i', afile, '-vf',
        'fps=1', 'out%d.png' # <-- fix out
    ]

    #ffmpeg -i input.flv -vf fps=1 out%d.png

    subprocess.call(cmd)



def stream():
    pass


def calc_success(rectangles, img_height, img_width, success=0.9):
    """Helper to check the n percentage of the image is covered in text."""
    t = sum([i[2] * i[3] for i in rectangles if i])
    p = 100 * float(t) / float(img_height * img_width)
    return p > success


def locate_text(image, debug=False):
    # Mostly ripped from https://github.com/hurdlea/Movie-Credits-Detect
    # Thanks!

    import cv2
    import numpy as np
    # Compat so we can use a frame and a file..
    if os.path.exists(image) and os.path.isfile(image):
        image = cv2.imread(image)

    if debug:
        cv2.imshow('original image', image)

    height, width, depth = image.shape
    img_height = height
    img_width = width
    mser = cv2.MSER_create(4, 10, 8000, 0.8, 0.2, 200, 1.01, 0.003, 5)
    # Convert to gray.
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if debug:
        cv2.imshow('grey', grey)

    # Pull out grahically overlayed text from a video image
    blur = cv2.GaussianBlur(grey, (3, 3), 0)

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
        # Knobs?
        if w < 2 or h < 2:
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
    yscaleFactor = 0  # 0
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
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.01 * peri, True)

        # the contour is 'bad' if it is not a rectangluarish
        # This doesnt have to be bad, since we match more then one char.
        if len(approx) > 8:
            cv2.drawContours(image, [contour], -1, color['lime'])
            if debug:
                cv2.imshow("bad Rectangles check lime", image)
            continue

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


@click.command()
@click.argument('path')
@click.option('-c', type=float, default=0.0)
@click.option('-d', '--debug', is_flag=True, default=False)
@click.option('-p', '--profile', is_flag=True, default=False)
def cmd(path, c, debug, profile):
    if os.path.isfile(path):
        files = [path]
    else:
        files = glob.glob(path)

    for f in files:
        if profile:
            t = timecall(locate_text(f, debug=debug), immediate=True)
        else:
            t = locate_text(f, debug=debug)

        if c:
            t = calc_success(t, c)

        n = True if t else False
        click.echo(n, t)


if __name__ == '__main__':
    cmd()



