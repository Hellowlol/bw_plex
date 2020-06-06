import math
from collections import defaultdict

import numpy as np
from bw_plex import LOG
from bw_plex.audio import create_audio_fingerprint_from_folder
from bw_plex.hashing import find_common_intro_hashes_fpcalc, ham_np
from bw_plex.misc import sec_to_hh_mm_ss
from more_itertools import unzip


def is_smooth(data, ness=1):
    """Check if the diff between this less then ness."""
    res = []
    for i, e in enumerate(data):
        try:
            if abs(data[i + 1] - e) <= ness:
                res.append(True)
            else:
                res.append(False)
                break
        except IndexError:
            if abs(data[i - 1] - e) <= ness:
                res.append(True)
            else:
                res.append(False)
    try:
        first_false = res.index(False)
        return False, first_false
    except ValueError:
        return True, len(res)


def keep(it):
    """ helper to remove remove stuff"""
    res = []
    it = list(sorted(list(set(it))))

    # Keep stripping for the start until
    # we get a large increase at the start.
    # I want to precheck this with a low ness as
    # this is usally the netflix intro.
    # We should check if thats the start..
    # Check for junk the first 6-7 sec
    if any(i for i in it[:50] if i < 50):
        smooth, idx = is_smooth(it[:50], ness=10)
        if smooth is False:
            LOG.debug("Cropped %s", it[: idx + 1])
            it = it[idx + 1 :]

    for i, v in enumerate(it):
        try:
            # Check the last value vs the next one
            part = [res[-1], v]
            sm, idxx = is_smooth(part, 100)
            if sm:
                res.append(v)
            else:
                break

        except IndexError:
            part = it[i : i + 2]
            smooth, idxx = is_smooth(part, 100)
            if smooth is True:
                res.append(v)
            else:
                if len(res) == 0:
                    continue
                break

    return res


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
        t, arr = unzip(value["fp"])
        timings = np.array(t)

        for ih in intro_hashes:
            res, idx = ham_np(ih, np.array(arr))

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
        LOG.debug("Using cutoff %s", cutoff)

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


def find_intros_fpcalc(data, base=None, cutoff=1):
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

    for k in sorted(intros.keys()):
        LOG.debug("%s %s", k, list(sorted(intros[k]["timings"])))

    return intros


def special_sauce_fpcalc(data):
    D = defaultdict(dict)
    for intro in sorted(data):
        T = keep(data[intro]["timings"])

        start = min(T) / data[intro]["hps"]
        end = max(T) / data[intro]["hps"]
        # raw_start = min(data[intro]["timings"])
        # raw_end = max(data[intro]["timings"])
        # print(len(data[intro]["timings"]))

        LOG.info(
            "[AUDIO] intro in %s start %s, end %s"
            % (intro, sec_to_hh_mm_ss(start), sec_to_hh_mm_ss(end))
        )
        D[intro]["start"] = start
        D[intro]["end"] = end

        if end - start < 15:
            print("Intro is shorter then 15 sec")
            # continue

    return D




if __name__ == "__main__":
    # Example usage :)
    print("start")
    import logging
    logging.basicConfig(level=logging.DEBUG)
    path_to_a_season =  r"C:\stuff\s13eps\dexter"
    audio_fingerprints = create_audio_fingerprint_from_folder(path_to_a_season)
    data = find_intros_fpcalc(audio_fingerprints)
    #print(data)
    result = special_sauce_fpcalc(data)
