import os


def visulize_intro_from_hashes(first, hashes, pause=0.2, end=500):
    import matplotlib.pyplot as plt
    import cv2

    first_vid = video_frame_by_frame(first, frame_range=False, end=end)
    ax1 = plt.subplot(1, 2, 1)
    im1 = ax1.imshow(np.zeros([150, 150, 3], dtype=np.uint8))
    ax1.set_xlabel(os.path.basename(first))

    for first_frame, first_pos in first_vid:
        h = ImageHash(create_imghash(first_frame))
        if h and str(h) in hashes:

            ax1.set_title('Source %s' % to_time(first_pos / 1000))
            im1.set_data(first_frame)
            plt.pause(pause)

    #plt.ioff() # due to infinite loop, this gets never called.
    plt.show()