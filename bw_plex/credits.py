from __future__ import division

import math
import os
import subprocess

import numpy as np

from bw_plex import LOG
from bw_plex.video import video_frame_by_frame
from bw_plex.misc import sec_to_hh_mm_ss

try:
    import cv2
except ImportError:
    cv2 = None
    LOG.warning('Scanning for credits is not supported. '
                'Install the package with pip install bw_plex[all] or bw_plex[video]')

try:
    import pytesseract
except ImportError:
    pytesseract = None
    LOG.warning('Extracting text from images is not supported. '
                'Install the package with pip install bw_plex[all] or bw_plex[video]')

try:
    import Image
except ImportError:
    from PIL import Image

# b g, r

# (255, 0, 0)
color = {'yellow': (0, 255, 255),
         'red': (0, 0, 255),
         'blue': (255, 0, 0),
         'lime': (0, 255, 0),
         'white': (255, 255, 255),
         'fuchsia': (255, 0, 255),
         'black': (0, 0, 0)
         }


NET = None

EAST_MODEL = os.path.join(os.path.dirname(__file__), 'models', 'frozen_east_text_detection.pb')


class DEBUG_STOP(Exception):
    pass


def check_stop_in_credits(value, cutoff=1500):
    """Helper to check if the credits are consecutive."""
    for i, v in enumerate(np.diff(value, n=1).tolist()):
        if v > cutoff:
            return i, v

    return None, None


def crop_img(i, edge=0):
    """ crop the image edge % pr side."""
    new_img = i.copy()
    height = new_img.shape[0]
    width = new_img.shape[1]
    sh = int(height / 100 * edge)
    sw = int(width / 100 * edge)

    return new_img[sh:height - sh, sw:width - sw]


def decode(scores, geometry, scoreThresh=0.9999):
    # Stolen from https://github.com/opencv/opencv/blob/master/samples/dnn/text_detection.py
    # scoreTresh is set insanely high as we dont want false positives.
    detections = []
    confidences = []

    # CHECK DIMENSIONS AND SHAPES OF geometry AND scores #
    assert len(scores.shape) == 4, "Incorrect dimensions of scores"
    assert len(geometry.shape) == 4, "Incorrect dimensions of geometry"
    assert scores.shape[0] == 1, "Invalid dimensions of scores"
    assert geometry.shape[0] == 1, "Invalid dimensions of geometry"
    assert scores.shape[1] == 1, "Invalid dimensions of scores"
    assert geometry.shape[1] == 5, "Invalid dimensions of geometry"
    assert scores.shape[2] == geometry.shape[2], "Invalid dimensions of scores and geometry"
    assert scores.shape[3] == geometry.shape[3], "Invalid dimensions of scores and geometry"
    height = scores.shape[2]
    width = scores.shape[3]
    for y in range(0, height):

        # Extract data from scores
        scoresData = scores[0][0][y]
        x0_data = geometry[0][0][y]
        x1_data = geometry[0][1][y]
        x2_data = geometry[0][2][y]
        x3_data = geometry[0][3][y]
        anglesData = geometry[0][4][y]
        for x in range(0, width):
            score = scoresData[x]

            # If score is lower than threshold score, move to next x
            if(score < scoreThresh):
                continue

            # Calculate offset
            offsetX = x * 4.0
            offsetY = y * 4.0
            angle = anglesData[x]

            # Calculate cos and sin of angle
            cosA = math.cos(angle)
            sinA = math.sin(angle)
            h = x0_data[x] + x2_data[x]
            w = x1_data[x] + x3_data[x]

            # Calculate offset
            offset = ([offsetX + cosA * x1_data[x] + sinA * x2_data[x], offsetY - sinA * x1_data[x] + cosA * x2_data[x]])

            # Find points for rectangle
            p1 = (-sinA * h + offset[0], -cosA * h + offset[1])
            p3 = (-cosA * w + offset[0], sinA * w + offset[1])
            center = (0.5 * (p1[0] + p3[0]), 0.5 * (p1[1] + p3[1]))
            detections.append((center, (w, h), -1 * angle * 180.0 / math.pi))
            # This should be the format for non rotation nms boxes
            #detections.append([int(center[0]), int(center[1]), int(w), int(h)])
            confidences.append(float(score))

    #print(detections)
    #print(confidences)

    # Return detections and confidences
    return [detections, confidences]


def make_imgz(afile, start=600, dest=None, fps=1):  # pragma: no cover
    """Helper to generate images."""

    dest_path = dest + '\out%d.jpg'
    fps = 'fps=%s' % fps
    t = sec_to_hh_mm_ss(start)

    cmd = [
        'ffmpeg', '-ss', t, '-i',
        afile, '-vf', fps, dest_path
    ]

    # fix me
    subprocess.call(cmd)
    return dest


def extract_text(img, lang='eng', encoding='utf-8'):
    """Very simple way to find the text in a image, it don't work work well for
       natural scene images but it good enoght for clean frames like credits.

       Ideally we should prop set some roi, but cba for now.

    """
    if pytesseract is None:
        return

    if isinstance(img, str):
        img = Image.open(img)

    return pytesseract.image_to_string(img, lang=lang).encode(encoding, 'ignore')


def calc_success(rectangles, img_height, img_width, success=0.9):  # pragma: no cover
    """Helper to check the n percentage of the image is covered in text."""
    t = sum([i[2] * i[3] for i in rectangles if i])
    p = 100 * float(t) / float(img_height * img_width)
    return p > success


def locate_text_east(image, debug=False, width=320, height=320, confedence_tresh=0.5, nms_treshhold=0):
    import cv2

    global NET

    if NET is None:
        NET = cv2.dnn.readNet(EAST_MODEL)

    features = ['feature_fusion/Conv_7/Sigmoid', 'feature_fusion/concat_3']

    if isinstance(image, str) and os.path.isfile(image):
        image = cv2.imread(image)

    frame = image

    # crop the image as we dont want
    # the logo and burnt in subs.
    # Maybe this edge needs to be a config option # TODO
    frame = crop_img(frame, edge=15)

    # Get frame height and width
    height_ = frame.shape[0]
    width_ = frame.shape[1]
    rW = width_ / float(width)
    rH = height_ / float(height)

    # Create a 4D blob from frame.
    blob = cv2.dnn.blobFromImage(frame, 1.0, (width, height), (123.68, 116.78, 103.94), swapRB=True, crop=False)

    # Run the model
    NET.setInput(blob)
    kWinName = "EAST: An Efficient and Accurate Scene Text Detector"
    # Get scores and geometry
    scores, geometry = NET.forward(features)
    t, _ = NET.getPerfProfile()
    label = 'Inference time: %.2f ms' % (t * 1000.0 / cv2.getTickFrequency())
    boxes, confidences = decode(scores, geometry)
    # print(confidences)
    indices = cv2.dnn.NMSBoxesRotated(boxes, confidences, confedence_tresh, nms_treshhold)
    # Why the fuck dont you work??
    # https://github.com/opencv/opencv/issues/12299
    # indices = cv2.dnn.NMSBoxes(boxes, confidences, confedence_tresh, nms_treshhold)
    locs = []

    if debug is False:
        if isinstance(indices, tuple):
            return []
        else:
            return indices

    for i in indices:
        vertices = cv2.boxPoints(boxes[i[0]])
        # scale the bounding box coordinates based on the respective ratios
        for j in range(4):
            vertices[j][0] *= rW
            vertices[j][1] *= rH

        box = np.int0(vertices)
        cv2.drawContours(frame, [box], 0, color['blue'], 2)
        locs.append([box])
        # print(t)
        # rects will do for now.
        # for j in range(4):
        #     p1 = (vertices[j][0], vertices[j][1])
        #     p2 = (vertices[(j + 1) % 4][0], vertices[(j + 1) % 4][1])
        #     cv2.line(frame, p1, p2, (0, 255, 0), 2)

    # Display the frame
    if debug:
        # Put efficiency information
        cv2.putText(frame, label, (0, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0))
        cv2.imshow(kWinName, frame)

        k = cv2.waitKey(0) & 0xff
        if k == 27:
            raise DEBUG_STOP

    if isinstance(indices, tuple):
        return []
    else:

        return locs


def check_movement(path, debug=True):  # pragma: no cover
    """Nothing usefull atm. TODO"""

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    #k = np.zeros((3,3),np.uint8)
    #fgbg = cv2.createBackgroundSubtractorGMG()
    #fgbg = cv2.createBackgroundSubtractorMOG2(history=1, varThreshold=2, detectShadows=False)
    #fgbg = cv2.createBackgroundSubtractorMOG()
    # (int history=500, double dist2Threshold=400.0, bool detectShadows=true
    fgbg = cv2.createBackgroundSubtractorKNN(1, 200, False)
    frame = None
    r_size = (640, 480)

    for _, (frame, millisec) in enumerate(video_frame_by_frame(path, offset=0,
                                                               step=0, frame_range=False)):
        if frame is not None:
            fgmask = fgbg.apply(frame)
            fgmask = cv2.erode(fgmask, kernel, iterations=20)
            fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_OPEN, kernel)
            fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, kernel)

            if debug:
                # Need to add a extra channel
                m = cv2.cvtColor(fgmask, cv2.COLOR_GRAY2BGR)
                # Resize so it easier to see them side by side.
                m = cv2.resize(m, r_size)
                f = cv2.resize(frame.copy(), r_size)
                vis = np.concatenate((m, f), axis=1)

                cv2.imshow('frame', vis)

            k = cv2.waitKey(0) & 0xff
            if k == 27:
                break

    # cv2.destroyAllWindows()


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
    if isinstance(image, str) and os.path.isfile(image):
        image = cv2.imread(image)

    height, width, _ = image.shape
    mser = cv2.MSER_create(4, 10, 8000, 0.8, 0.2, 200, 1.01, 0.003, 5)
    # Convert to gray.
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Pull out grahically overlayed text from a video image
    blur = cv2.GaussianBlur(grey, (3, 3), 0)
    adapt_threshold = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                            cv2.THRESH_BINARY, 5, -25)

    contours, _ = mser.detectRegions(adapt_threshold)

    # for each contour get a bounding box and remove
    rects = []
    for contour in contours:
        # get rectangle bounding contour
        [x, y, w, h] = cv2.boundingRect(contour)

        # Remove small rects
        if w < 5 or h < 5:  # 2
            continue

        # Throw away rectangles which don't match a character aspect ratio
        if (float(w * h) / (width * height)) > 0.005 or float(w) / h > 1:
            continue

        rects.append(cv2.boundingRect(contour))

    # Mask of original image
    mask = np.zeros((height, width, 1), np.uint8)
    # To expand rectangles, i.e. increase sensitivity to nearby rectangles
    # Add knobs?
    # lets scale this alot so we get mostly one big square
    # todo when/if detect motion.
    xscaleFactor = 14  # 14
    yscaleFactor = 4  # 4
    for box in rects:
        [x, y, w, h] = box
        # Draw filled bounding boxes on mask
        cv2.rectangle(mask, (x - xscaleFactor, y - yscaleFactor),
                      (x + w + xscaleFactor, y + h + yscaleFactor),
                      color['white'], cv2.FILLED)

    # Find contours in mask if bounding boxes overlap,
    # they will be joined by this function call
    rectangles = []
    contours = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if cv2.__version__.startswith('4'):
        contours = contours[0]
    else:
        contours = contours[1]

    for contour in contours:
        # This is disabled since we are not after the text but the text area.
        # Only preserve "squarish" features
        # peri = cv2.arcLength(contour, True)
        # approx = cv2.approxPolyDP(contour, 0.01 * peri, True)

        # the contour is 'bad' if it is not a rectangluarish
        # This doesnt have to be bad, since we match more then one char.
        # if len(approx) > 8:
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
            pass
            # This is disabled as we want to cache the large area of text
            # to backup this shit for movement detection
            # General catch for larger identified areas that they have
            # a text width profile
            # and it does not fit for jap letters.

            # if float(w) / h < 1.8:
            #    continue

        rectangles.append(rect)

        cv2.rectangle(image, (x, y), (x + w, y + h), color['fuchsia'], 2)

    if debug:
        cv2.imshow("Final image", image)
        cv2.waitKey(0)

    return rectangles


def find_credits(path, offset=0, fps=None, duration=None,
                 check=7, step=1, frame_range=True, debug=False, method='east'):
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
            debug(bool): Disable the images.
            method(str): east is better but slower.

       Returns:
            1, 2


    """
    # LOG.debug('%r %r %r %r %r %r %r', path, offset, fps, duration, check, step, frame_range)
    if cv2 is None:
        return
    frames = []
    start = -1
    end = -1
    LOG.debug('Trying to find the credits for %s', path)

    if method == 'east':
        func = locate_text_east
    else:
        func = locate_text

    try:
        if fps is None:
            # we can just grab the fps from plex.
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()

        for _, (frame, millisec) in enumerate(video_frame_by_frame(path, offset=offset,
                                                                   step=step, frame_range=frame_range)):

            try:
                # LOG.debug('progress %s', millisec / 1000)
                if frame is not None:
                    # recs = locate_text(frame, debug=True)
                    recs = func(frame, debug=debug)
                    len_recs = len(recs)

                    # If we get 1 match we should verify.
                    # now this is pretty harsh but we really
                    # don't want false positives.
                    if len_recs == 0:
                        continue
                    elif len_recs == 1:
                        t = extract_text(frame)
                        if t:
                            frames.append(millisec)
                    else:
                        frames.append(millisec)

                    # check for motion here?

                    if check != -1 and len(frames) >= check:
                        break

            except DEBUG_STOP:
                break
                if hasattr(cv2, 'destroyAllWindows'):
                    cv2.destroyAllWindows()

        if frames:
            start = min(frames) / 1000
            end = max(frames) / 1000

        LOG.debug('credits_start %s, credits_end %s', start, end)

    except:  # pragma: no cover
        # We just want to log the exception not halt the entire process to db.
        LOG.exception('There was a error in find_credits')

    return start, end


def fill_rects(image, rects):  # pragma: no cover
    """This is used to fill the rects (location of credits)

       The idea if to mask the credits so we can check if there is any background
       movement while the credits are running. Like the movie cars etc.
       See if we can grab something usefull from
       https://gist.github.com/luipillmann/d76eb4f4eea0320bb35dcd1b2a4575ee
    """
    for rect in rects:
        try:
            x, y, w, h = rect
            cv2.rectangle(image, (x, y), (x + w, y + h), color['black'], cv2.FILLED)
        except ValueError:
            cv2.drawContours(image, rect, 0, color['black'], cv2.FILLED)

    return image


if __name__ == '__main__':
    def test():
        import logging
        # logging.basicConfig(level=logging.DEBUG)
        import cv2
        # i = r"C:\Users\steff\Documents\GitHub\bw_plex\tests\test_data\blacktext_whitebg_2.png"
        # i = r'C:\Users\alexa\.config\bw_plex\third_images\out165.jpg'

        # img = cv2.imread(i)
        # ffs = img.copy()
        # rects = locate_text(ffs, debug=True)
        # locate_text2(img, debug=True, width=320, height=320, confedence_tresh=0.8, nms_treshhold=0.1)
        #out = r'C:\stuff\GUNDAM BUILD FIGHTERS TRY-Episode 1 - The Boy Who Calls The Wind (ENG sub)-M7fLOQXlPmE.mkv' # 21*60
        # out = r'C:\Users\steff\Documents\GitHub\bw_plex\tests\test_data\part.mkv'
        out = r'C:\Users\steff\Documents\GitHub\bw_plex\tests\test_data\out.mkv'
        t = find_credits(out, offset=0, fps=None, duration=None, check=600, step=1, frame_range=True, debug=True)
        print(t)
        # print(out)
        # for z in check_movement(out):
        #     print()



        # f = fill_rects(img, rects)
        # cv2.imshow('ass', f)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()


    test()
