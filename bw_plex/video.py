from bw_plex import LOG


def video_frame_by_frame(path, offset=0, frame_range=None, step=1, end=None):
    """ Returns a video files frame by frame.by
        Args:
            path (str): path to the video file
            offset (int): Should we start from offset inside vid
            frame_range (list, None): List of frames numbers we should grab.
            step(int): check every n, note this is ignored if frame_range is False
            end (int, None):
        Returns:
            numpy.ndarray
    """

    import cv2

    cap = cv2.VideoCapture(path)

    if frame_range:
        fps = cap.get(cv2.CAP_PROP_FPS)

        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
        duration = int(duration)
        if end is None:
            end = duration
        start = int(offset)

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

            if end and pos / 1000 > end:
                LOG.debug("Stopped reading the file because of %s", end)
                break

    cap.release()

    # Keeping it for now, i cant remember if its needed but seems to be a issue
    # for opencv 4 with the contrib version.
    # if hasattr(cv2, 'destroyAll
