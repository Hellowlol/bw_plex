import operator
import itertools
from collections import OrderedDict


class Hash:
    __slots__ = ('name', 'pos')

    def __init__(self, name):
        self.name = name
        self.pos = []

    def add_pos(self, pos):
        self.pos.append(pos)

    @property
    def size(self):
        return len(self.pos)

    def __str__(self):
        return r'<Hash %s>' % self.name


class Hashlist():
    """Wrapper class for the hashes."""
    _kek = OrderedDict()

    def add_items(cls, h, pos):
        # covert the list to tuple so its hashable
        hh = tuple(h)
        if hh not in cls._kek:
            cls._kek[hh] = Hash(name=hh)
        # Add whrer thsi
        cls._kek[hh].add_pos(pos)

    def add_stack(cls, stack):
        for h, pos in stack:
            cls.add_items(h, pos)

    def most_common(cls, n=None):
        """return a list of hashes sorted on the n most common
           (number of times in hashlist.)
        """
        x = sorted(cls._kek.values(), key=lambda f: f.size, reverse=True)
        if n:
            return x[n:]

        return x

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



"""
k = Hashlist()

t = [([1],2), ([1],3), ([3],3), ([3],3), ([3],3), ([3],3)]
for tt in t:
    h, u = tt
    k.add_items(h, u)


#print(vars(k))

stuff = k.most_common()
for i in stuff:
    print(i)
    #print(i.size)

first = k[0]
print(first.name)
print(first.size)
print(first.pos)
"""
