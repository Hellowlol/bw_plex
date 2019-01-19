import hashlib
from collections import OrderedDict
from itertools import chain
from profilehooks import profile
#from scipy.spatial import KDTree


import numpy as np


def string_hash(stack):
    """convert a all hashes to one hash."""
    h = ''.join((str(i) for i in chain(*stack)))
    return hashlib.md5(h.encode('utf-8')).hexdigest()


# fix me
def _binary_array_to_hex(arr):
    """
    internal function to make a hex string out of a binary array.
    """
    bit_string = ''.join(str(b) for b in 1 * arr.flatten())
    width = int(np.ceil(len(bit_string) / 4))
    return '{:0>{width}x}'.format(int(bit_string, 2), width=width)



class ImageHash(object):
    """
    Hash encapsulation. Can be used for dictionary keys and comparisons.
    """
    __slots__ = ('name', 'pos', 'size', 'add_pos', 'hash')

    def __init__(self, binary_array):
        self.hash = binary_array.flatten()
        self.pos = []

    def add_pos(self, pos):
        self.pos.append(pos)

    def __str__(self):
        return _binary_array_to_hex(self.hash)

    def __repr__(self):
        return repr(self.hash)

    def __sub__(self, other):
        if other is None:
            raise TypeError('Other hash must not be None.')
        if self.hash.size != other.hash.size:
            raise TypeError('ImageHashes must be of the same shape.', self.hash.shape, other.hash.shape)
        return np.count_nonzero(self.hash != other.hash)

    def __eq__(self, other):
        if other is None:
            return False
        return np.array_equal(self.hash, other.hash)

    def __ne__(self, other):
        if other is None:
            return False
        return not np.array_equal(self.hash, other.hash)

    def __hash__(self):
        return sum([2 ** i for i, v in enumerate(self.hash) if v])

    def __iter__(self):
        yield self

    @property
    def size(self):
        return len(self.pos)

    def reshape(self, *args):
        # for lazy compat
        return self.hash.reshape(*args)



class Hash:
    """Hash and where the hash was found.""" # derp
    __slots__ = ('name', 'pos')

    def __init__(self, binary_array):
        self.hash = binary_array.flatten()
        self.pos = []

    def add_pos(self, pos):
        self.pos.append(pos)

    def __str__(self):
        return ''.join(hex(i) for i in self.hash)

    def __repr__(self):
        return repr(self.hash)

    def __sub__(self, other):
        if other is None:
            raise TypeError('Other hash must not be None.')
        if self.hash.size != other.hash.size:
            raise TypeError('ImageHashes must be of the same shape.', self.hash.shape, other.hash.shape)
        return np.count_nonzero(self.hash != other.hash)

    def __eq__(self, other):
        if other is None:
            return False
        return np.array_equal(self.hash, other.hash)

    def __ne__(self, other):
        if other is None:
            return False
        return not np.array_equal(self.hash, other.hash)

    def __hash__(self):
        return sum([2 ** i for i, v in enumerate(self.hash) if v])

    def __iter__(self):
        yield self

    @property
    def size(self):
        return len(self.pos)

    def reshape(self, *args):
        # for lazy compat
        return self.hash.reshape(*args)


def hex_to_hash(hexstr):
    """
    Convert a stored hash (hex, as retrieved from str(Imagehash))
    back to a Imagehash object.
    """ # check if this is compat with my way
    l = []
    if len(hexstr) != 2 * (16 * 16) / 8:
        raise ValueError('The hex string has the wrong length')
    for i in range(16 * 16 / 8):
        h = hexstr[i * 2: i * 2 + 2]
        v = int("0x" + h, 16)
        l.append([v & 2 ** i > 0 for i in range(8)])
    return ImageHash(np.array(l).reshape((16, 16)))


class Hashlist():
    """Wrapper class for the hashes."""
    _kek = OrderedDict()
    _needel = []
    _start = None
    _end = None
    _tresh = 5
    _added_stacks = 0

    def add_needel(cls, needel):
        cls._needel = needel

    def detect(cls):
        """ zomg"""
        times = []
        for i in cls:
            # Filter out black frames..
            if sum(i.name) and i.size > 1:
                for n in cls._needel:
                    print(n[0], i.name)
                    if n[0] == i.name:
                        times.append(n[1])
        print('times', times)
        if times:
            cls._end = max(times) / 1000
            cls._start = min(times) / 1000

        # assume recap if time isnt 0 sec?


    def add_items(cls, h, pos):
        if h not in cls._kek:
            cls._kek[h] = h
        # Add whrer thsi
        cls._kek[h].add_pos(pos)

    def add_stack(cls, stack):
        cls._added_stacks += 1
        for h, frame, pos in stack:
            cls.add_items(h, pos)

    #@profile(immediate=True)
    def most_common2(cls, n=None, thresh=5):
        """return a list of hashes sorted on the n most common
           (number of times in hashlist.) this only counts perfect match..
        """
        stuff = []
        #N = None
        _kek = {}
 
        #x = sorted(cls._kek.values(), key=lambda f: f.size, reverse=True)
        # We sort on size but remove all black frames. As they pretty common.
        x = sorted((i for i in cls._kek.values() if np.sum(i.hash)), key=lambda f: f.size, reverse=True)

        if n:
            return x[:n]

        return x


    #@profile(immediate=True)
    def kd(cls, stack):
        KD = KDTree(stack)
        return KD



# http://cs231n.github.io/python-numpy-tutorial/#numpyhttp://cs231n.github.io/python-numpy-tutorial/#numpy
        

    #@profile(immediate=True)
    def find_similar(cls, value, thresh=4):

        t =  np.array([i.hash for i in cls._kek.values()]) # if not np.array_equal(i.hash, value.hash)])
        #print(t.shape)
        binarydiff = t != value.hash.reshape((1,-1))
        hammingdiff = binarydiff.sum(axis=1)
        if thresh is not None:
            idx = np.where(hammingdiff < thresh)
            return t[idx], idx

        closestdbHash_i = np.argmin(hammingdiff)
        #print('closestdbHash_i', closestdbHash_i)
        closestdbHash = t[closestdbHash_i]
        #print([np.count_nonzero(z != value.hash) for z in closestdbHash])

        return closestdbHash, closestdbHash_i

    #@profile(immediate=True)
    def most_common(cls):
        """find the most common, this looks for any withing a certen hamming distance."""
        items = list(cls._kek.values())
        hashes = np.array([i.hash for i in items])
        result = []
        idx = []
        for h in hashes:
            hh, idxx = cls.lookslike(h, hashes)
            result.extend(h)
            idx.extend(idxx)

        #print(result)
        print(len(result))
        return result

    def lookslike(cls, img, stuff):
        """img in a iamge hash

           stuff is a array of hashes.

           stole from # https://stackoverflow.com/questions/39585069/quickest-way-to-find-smallest-hamming-distance-in-a-list-of-fixed-length-hexes
           slight modifications.
        """
        binarydiff = stuff != img.reshape((1, -1))
        hammingdiff = binarydiff.sum(axis=1)
        closestdbHash = np.where(hammingdiff < 5)
        return stuff[closestdbHash], closestdbHash


    @property
    def size(cls):
        """Get number of hashes"""
        return len(cls._kek)

    def __getitem__(cls, n):
        # see if we can make this more efficient.
        return list(cls._kek.values())[n]

    def __iter__(cls):
        for i in cls._kek.values():
            yield i
