
from conftest import hashing
import numpy as np
from bw_plex.hashing import ImageHash

def test_hashing(): # fixme
    k = hashing.Hashlist()

    t = [(np.array([1]), 2), (np.array([3]), 3), (np.array([3]), 3), (np.array([3]), 3), (np.array([3]), 3), (np.array([1]), 3)]
    for tt in t:
        h, u = tt
        H = ImageHash(h)
        k.add_items(H, u)

    #stuff = list(k.most_common())
    
    #first = stuff[0]
    #print(stuff[0])
    #print(str(stuff[0]))
    #assert first.name == (3,)
    #assert first.size == 4
    #assert first.pos == [3, 3, 3, 3]


def test_string_hash():
    assert 'c20ad4d76fe97759aa27a0c99bff6710' == hashing.string_hash([[1], [2]])

