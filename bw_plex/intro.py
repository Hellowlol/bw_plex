import json
import logging
import math
import os
from collections import defaultdict
from operator import itemgetter

import numpy as np
from bw_plex import DEFAULT_FOLDER, LOG, MEMORY
from bw_plex.audio import create_audio_fingerprint_from_folder
from bw_plex.hashing import (create_video_fingerprint_from_folder,
                             find_common_intro_hashes_fpcalc, ham_np)
from bw_plex.misc import (_find_offset_ffmpeg, get_pms, grouper, measure,
                          ms_to_hh_mm_ms, sec_to_hh_mm_ss)
from more_itertools import unzip

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)



def find_closest_scene(it, ep_start, ep_end, type="start", cutoff=7):
    it = list(sorted(it))

    _LOGGER.debug("ORG: %s", it)
    _LOGGER.debug("start: %s end: %s", ep_start, ep_end)
    result_start = []
    result_end = []
    for item in it:
        start, end, duration = item

        ep_start_scene_start_diff = abs(start - ep_start)
        ep_start_scene_end_diff = abs(end - ep_start)

        ep_end_scene_start_diff = abs(start - ep_end)
        ep_end_scene_end_diff = abs(end - ep_end)

        if ep_start_scene_start_diff < cutoff and ep_start_scene_end_diff < cutoff:
            result_start.append(
                [
                    start,
                    end,
                    duration,
                    ep_start_scene_start_diff,
                    ep_start_scene_end_diff,
                ]
            )
        elif ep_end_scene_start_diff < cutoff and ep_end_scene_end_diff < cutoff:
            result_end.append(
                [start, end, duration, ep_end_scene_start_diff, ep_end_scene_end_diff]
            )

    scene_start = sorted(result_start, key=itemgetter(3))
    scene_end = sorted(result_end, key=itemgetter(4))
    _LOGGER.debug("Scene start: %s", scene_start)
    _LOGGER.debug("Scene end: %s", scene_end)
    try:
        selected_start = scene_start[0][0]
        selected_end = scene_end[0][1]
        _LOGGER.debug("Picked start %s |%s (%s) and end %s |%s (%s)", selected_start, ms_to_hh_mm_ms(selected_start*1000), ep_start, selected_end, ms_to_hh_mm_ms(selected_end*1000), ep_end)
        return selected_start, selected_end
    except IndexError:
        _LOGGER.debug("Failed to get a scene")
        return ep_start, ep_end


def keep(it, ness, name=None):
    result = grouper(it, ness)
    result = sorted(result, key=len, reverse=True)

    _LOGGER.debug("%s", os.path.basename(name))
    _LOGGER.debug("Orginal: %s", it)
    if len(result):

        selected = result[0]
        dropped = result[1:]
        _LOGGER.debug(
            "Using: %s", [(i, ms_to_hh_mm_ms(i / 8.04 * 1000)) for i in selected]
        )
        for d in dropped:
            _LOGGER.debug(
                "Dropped: %s", [(i, ms_to_hh_mm_ms(i / 8.04 * 1000)) for i in d]
            )

        return selected

    _LOGGER.debug("Didnt find anything usefull %s", it)


def keep_hashes(it, ness, name=None):
    result = grouper(it, ness)
    result = sorted(result, key=len, reverse=True)

    _LOGGER.debug("%s", os.path.basename(name))
    _LOGGER.debug("Orginal: %s", it)
    if len(result):

        selected = result[0]
        dropped = result[1:]
        _LOGGER.debug(
            "Using: %s", [(i, ms_to_hh_mm_ms(i)) for i in selected]
        )
        for d in dropped:
            _LOGGER.debug(
                "Dropped: %s", [(i, ms_to_hh_mm_ms(i)) for i in d]
            )

        return selected

    _LOGGER.debug("Didnt find anything usefull %s", it)


def find_intros_frames(data, base=None, intro_hashes=None):
    """Find intros using numpy

       data: {"file_name": {"duration": 600, "fp": [(1, [0,1,2,3,4,5,6,7])], "id": "file_name"}}
       base: [[0,1,2,3,4,5,6,7]..]

    """
    intros = defaultdict(dict)
    if base is None:
        base = list(data.keys())[0]

    if intro_hashes is None:
        intro_hashes, _ = find_common_intro_hashes_frames(data, None)

    for key, value in data.items():
        timings = np.array([i[0] for i in value["fp"]])
        arr = np.array([i[1] for i in value["fp"]])

        for ih in intro_hashes:
            res, idx = ham_np(ih, arr)

            if res.size > 0:
                for k, ffs in zip(timings[idx], arr[idx]):
                    if "timings" not in intros[key]:
                        intros[key]["timings"] = []

                    intros[key]["timings"].append(k)

                    if "hashes" not in intros[key]:
                        intros[key]["hashes"] = []

                    intros[key]["hashes"].append((k, ffs))

    return intros


def find_common_intro_hashes_frames(data, base=None, cutoff=None):
    """Extact all common hashes from a season that is in """
    if cutoff is None:
        cutoff = math.floor(len(data.keys()) / 100 * 70)
        LOG.debug("Hashes has to be in %s items", cutoff)

    d = {}
    # Extract all hashes for all eps
    for key, value in data.items():
        # Remove duplicate frames from each episode.
        hashes_base = np.array([i[1] for i in value["fp"]])
        timings = np.array([i[0] for i in value["fp"]])
        unique_hashes, unique_hashes_idx = np.unique(
            hashes_base, axis=0, return_index=True
        )
        d[key] = {"timings": timings[unique_hashes_idx], "hashes": unique_hashes}

    # Combine hashes for all eps
    intros = np.vstack([v["hashes"] for v in d.values()])
    # Find the number of time we have seen the hashes in each ep.
    unique_hashes, counts = np.unique(intros, axis=0, return_counts=True)

    f = zip(unique_hashes, counts)
    # Filter out all hashes that wasnt seen in cutoff episodes
    res = [a[0] for a in f if a[1] >= cutoff]
    return res, d


@measure
@MEMORY.cache
def find_intros_fpcalc(data: dict, base=None, cutoff: int = 1) -> dict:
    """find intros using fpcalc

       Arguments:
            data: dict
            base: dict
            cutoff: int

        returns:
            dict

    """
    intros = defaultdict(dict)

    common_hashes = find_common_intro_hashes_fpcalc(data)
    LOG.debug("common hashes %s", common_hashes)
    if base is None:
        base_name = list(data.keys())[0]
        LOG.info("Using %s as base", base_name)
        base = data.pop(base_name)
        numer_of_hashes_intro_search_intro = len(base["fp"])

    for i, base_fp in enumerate(base["fp"]):
        for key, value in data.items():
            # Make sure we dont test against the same
            # intro as we using as base.
            if base_name == key:
                continue
            # LOG.debug("Checking %s", key)
            for ii, fp in enumerate(value["fp"]):
                # Use the int.bit_count() in py 3.10
                # or use gmpy to speedup
                if bin(base_fp ^ fp).count("1") <= cutoff:
                    # if base_fp == fp and base_name != key:
                    if base_fp in common_hashes:
                        LOG.debug(
                            "[Common] %s %s %s"
                            % (
                                fp,
                                sec_to_hh_mm_ss(i / base["hps"]),
                                sec_to_hh_mm_ss(ii / value["hps"]),
                            )
                        )

                    if "timings" not in intros[key]:
                        intros[key]["timings"] = []

                    intros[key]["timings"].append(ii)

                    if "hashes" not in intros[key]:
                        intros[key]["hashes"] = []

                    intros[key]["hashes"].append(base_fp)
                    intros[key]["hps"] = value["hps"]

                    if "timings" not in intros[base["id"]]:
                        intros[base["id"]]["timings"] = []

                    if "hashes" not in intros[base["id"]]:
                        intros[base["id"]]["hashes"] = []

                    intros[base["id"]]["timings"].append(i)
                    intros[base["id"]]["hashes"].append(base_fp)
                    intros[base["id"]]["hps"] = base["hps"]

    return intros


def special_sauce(data):
    """Helper to remove unwanted timings"""
    D = defaultdict(dict)
    for intro in sorted(data):

        try:
            # Uses fpcalc
            T = keep(data[intro]["timings"], 100, intro)
            start = min(T) / data[intro]["hps"]
            end = max(T) / data[intro]["hps"]
        except KeyError:
            # Uses videofingerprint
            T = keep_hashes(data[intro]["timings"], 7000, intro)
            # Convert to the timings to seconds as this is whats used by fpcalc.
            T = [i / 1000 for i in T]
            start = min(T)
            end = max(T)

        raw_start = min(data[intro]["timings"])
        raw_end = max(data[intro]["timings"])
        # Try to find a scene shift using start and end as a guide line.
        # The start and end is the most correct way, but since we want the skip fade
        # to black and shit like this we try to find the end of the previous scene.
        f_v, f_a = MEMORY.cache(_find_offset_ffmpeg)(intro, offset=start-10, trim=end - start + 10)
        scene_start, scene_end = find_closest_scene(f_v, start, end)

        LOG.debug(
            "start %s scene_start %s end %s scene_end %s",
            ms_to_hh_mm_ms(start * 1000),
            ms_to_hh_mm_ms(scene_start * 1000),
            ms_to_hh_mm_ms(end * 1000),
            ms_to_hh_mm_ms(scene_end * 1000),
        )
        D[intro]["start"] = scene_start
        D[intro]["end"] = scene_end
        D[intro]["raw_start"] = raw_start
        D[intro]["raw_end"] = raw_end

        if end - start < 15:
            print("Intro is shorter then 15 sec")
            # continue

    return D


def test_vs_plex(show, method="audio"):
    from plexapi.server import PlexServer

    pms = PlexServer()
    print(pms.friendlyName)

    show = pms.library.section("TV Shows").get(show)
    print(show)

    season = show.seasons()[6]
    _LOGGER.debug("Season has %s episodes", len(season.episodes()))

    episodes = [e for e in season.episodes() if e.hasIntroMarker]
    _LOGGER.debug("%s episodes has intro markers", len(episodes))
    # Only uses epsideos that has markers
    ep_files = []

    items = {}

    if not len(episodes):
        return

    for e in episodes:
        fs = list(e.iterParts())[0].file
        new_name = fs.replace("/tvseries/", "W://")
        ep_files.append(new_name)
        items[new_name] = e

    if method == "audio":
        data = create_audio_fingerprint_from_folder(ep_files)
        _LOGGER.debug("Got %s audio fingerprints", len(data))
        data = find_intros_fpcalc(data)
        sau = special_sauce(data)

    elif method == "video":
        data = create_video_fingerprint_from_folder(ep_files)
        data = find_intros_frames(data)
        sau = special_sauce(data)

    for k, v in sau.items():
        pms_ep = items.get(k)
        if pms_ep:
            markers = pms_ep.markers[0]
            start = markers.start
            end = markers.end
            print(
                "[pms] intro in %s start %s T %s (plex %s) dev %s, end %s  T %s (plex %s) dev %s"
                % (
                    os.path.basename(k),
                    ms_to_hh_mm_ms(sau[k]["start"] * 1000),
                    sau[k]["raw_start"],
                    ms_to_hh_mm_ms(start),
                    round(abs(sau[k]["start"] * 1000 - start), 4),
                    ms_to_hh_mm_ms(sau[k]["end"] * 1000),
                    sau[k]["raw_end"],
                    ms_to_hh_mm_ms(end),
                    round(abs(sau[k]["end"] * 1000 - end), 4),
                )
            )


if __name__ == "__main__":
    # Example usage :)
    print("start")
    test_vs_plex("Dexter", method="video")
