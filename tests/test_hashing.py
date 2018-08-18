
from conftest import hashing


def test_hashing():
    k = hashing.Hashlist()

    t = [([1], 2), ([1], 3), ([3], 3), ([3], 3), ([3], 3), ([3], 3)]
    for tt in t:
        h, u = tt
        k.add_items(h, u)

    stuff = list(k.most_common())
    first = stuff[0]
    assert first.name == (3,)
    assert first.size == 4
    assert first.pos == [3, 3, 3, 3]
