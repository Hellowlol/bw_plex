import os
import math
import numpy as np

from bw_plex import LOG
from bw_plex.video import video_frame_by_frame
from bw_plex.hashing import ImageHash, create_imghash
from bw_plex.misc import to_time
from bw_plex.db import session_scope, Reference_Frame


def visulize_intro_from_hashes(videofile, hashes, pause=0.01, end=600):
    """Play the frames that maches the hashes."""
    import matplotlib.pyplot as plt
    import cv2

    first_vid = video_frame_by_frame(videofile, frame_range=False, end=end)
    ax1 = plt.subplot(1, 2, 1)
    im1 = ax1.imshow(np.zeros([150, 150, 3], dtype=np.uint8))
    ax1.set_xlabel(os.path.basename(videofile))

    for first_frame, first_pos in first_vid:
        h = ImageHash(create_imghash(first_frame))
        H = str(h)
        if h and H in hashes:
            # Convert as the colors are off for matplotlib.
            vis_frame = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

            ax1.set_title('Source %s | %s' % (to_time(first_pos / 1000), H))
            im1.set_data(vis_frame)
            plt.pause(pause)

    #plt.ioff() # due to infinite loop, this gets never called.
    plt.show()


def play(first, pause=0.02, end=600, key=None):
    """This is intended to be a player where the user add the video manually select what
       type reframe we should add to the db

       Args:
            first(str): path to file
            pause(float): how long should we pause playback between the frames.
            end(int): seconds intro the file we should stop playback.
            key(None, int): If to fill out shit. Not in use atm but will be used when called
                            from bw_plex cli.
    """
    global GOGO, cap, CURR_FRAME_NR, CURR_MS, KEY

    import matplotlib.pyplot as plt
    from matplotlib.widgets import Button, Slider, RadioButtons, TextBox
    import cv2

    CURR_FRAME = None
    CURR_FRAME_NR = None
    CURR_MS = None
    POS = 0
    CN = 0
    GOGO = True
    KEY = None

    # remove later..
    def to_hhmmss(sec):
        min, sec = divmod(sec, 60)
        hr, min = divmod(min, 60)
        return "%02d:%02d:%02.2f" % (hr, min, sec)

    if key is None:
        KEY = ''
    else:
        KEY = key

    cap = cv2.VideoCapture(first)
    FPS = cap.get(cv2.CAP_PROP_FPS)
    TOTAL_FRAMES = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    dur_sec = TOTAL_FRAMES / FPS
    dur_ms = dur_sec * 1000

    fig, ax = plt.subplots()
    ax.set_axis_off()
    fig.canvas.set_window_title('Find frames')

    im1 = ax.imshow(np.zeros([300, 400, 3], dtype=np.uint8))
    # I have noe idea what this does. Leave it.
    plt.subplots_adjust(left=0.25, bottom=0.25)

    axcolor = 'lightgoldenrodyellow'
    axfreq = plt.axes([0.25, 0.1, 0.65, 0.03], facecolor=axcolor)
    axbox = plt.axes([0.6, 0.025, 0.1, 0.04])
    sfreq = Slider(axfreq, 'T', 0, dur_ms, valinit=0)
    text_box = TextBox(axbox, 'id', initial=KEY)

    def event_tb(event):
        global KEY
        if KEY and key != KEY:
            KEY = event
        else:
            KEY = event
        # Do some shit here.
        print('KEY', KEY)

    text_box.on_submit(event_tb)

    def update(val):
        """update slider on click this will also change set CURR_MS so cv reads the correct frame"""
        global CURR_MS
        CURR_MS = int(math.floor(val))

        # Set the text we we dont wait for the next frame
        sfreq.valtext.set_text(to_hhmmss(CURR_MS / 1000))
        # update the bar.
        xy = sfreq.poly.xy
        xy[2] = CURR_MS, 1
        xy[3] = CURR_MS, 0
        sfreq.poly.xy = xy
        fig.canvas.draw_idle()

    sfreq.on_changed(update)

    # Add location of zhe buttons
    match_button_loc = plt.axes([0.8, 0.025, 0.1, 0.04])
    pause_button_loc = plt.axes([0.7, 0.025, 0.1, 0.04])
    match_button = Button(match_button_loc, 'Match', color=axcolor, hovercolor='0.975')
    pause_button = Button(pause_button_loc, 'P/P', color=axcolor, hovercolor='0.975')

    # Events..
    def pause_event(event):
        global GOGO
        GOGO = not GOGO
        LOG.debug('set pause to %s', GOGO)
    pause_button.on_clicked(pause_event)

    def close_event(event):
        # We only adda a close event so opencv dont keep reading the
        # file after we close matplotlib.
        global GOGO
        GOGO = False
    fig.canvas.mpl_connect('close_event', close_event)

    rax = plt.axes([0.025, 0.5, 0.15, 0.15], facecolor=axcolor)
    radio = RadioButtons(rax, ('start', 'end'), active=0)

    # Change me
    def radio_event(label):
        LOG.debug('Changed label %s', label)
        fig.canvas.draw_idle()
    radio.on_clicked(radio_event)

    def match_event(event):
        val = radio.value_selected

        h = ImageHash(create_imghash(CURR_FRAME))

        with session_scope() as se:
            rf = Reference_Frame(hex=str(h), type=val, tvdbid=KEY)
            LOG.debug('Added %s %s from %s in %s', str(h), val, POS, first)
            se.add(rf)

    match_button.on_clicked(match_event)


    while cap.isOpened():
        if GOGO:
            # Check if the user had moved the slider.
            # if so we should read the correct frame.
            if CURR_MS is not None:
                # Seek cap of the corret offset in ms.
                cap.set(cv2.CAP_PROP_POS_MSEC, CURR_MS)
                # Set to None as the video has moved position.
                CURR_MS = None

            ret, frame = cap.read()

            if ret:
                POS = cap.get(cv2.CAP_PROP_POS_MSEC)

                # Remove this?
                # if POS / 1000 > end:
                #    GOGO = None
                #    #print('end')
                #    break

                # This is needed for the hex of the frame.
                CURR_FRAME = frame.copy()
                # Resize the frame using cv as mathplotlib is slow if not.
                frame = cv2.resize(frame, (300, 400))
                # Fixup colors for matplotlib.
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                im1.set_data(frame)
                ax.set_title('%s|%s' % (to_hhmmss(POS / 1000), CN))
                # Update the slider without triggering it.
                xy = sfreq.poly.xy
                xy[2] = POS, 1
                xy[3] = POS, 0
                sfreq.poly.xy = xy
                sfreq.valtext.set_text(to_hhmmss(POS / 1000))
                sfreq.ax.figure.canvas.draw_idle()

                plt.pause(0.01)
        else:
            # Pause button has been pressed.
            plt.pause(0.1)

    cap.release()
    plt.show()
