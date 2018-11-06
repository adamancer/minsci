from __future__ import unicode_literals
from builtins import str
from collections import MutableSequence




class SiteList(MutableSequence):
    itemclass = None

    def __init__(self, *args, **kwargs):
        self.obj = [self.itemclass(site) for site in list(*args, **kwargs)]


    def __getitem__(self, i):
        return self.obj[i]


    def __setitem__(self, i, val):
        self.obj[i] = self.itemclass(val)


    def __delitem__(self, i):
        del self.obj[i]


    def __len__(self):
        return len(self.obj)


    def insert(self, i, val):
        self.obj.insert(i, self.itemclass(val))


    def __contains__(self, val):
        return val in self.obj


    def __str__(self):
        return str(self.obj)


    def __repr__(self):
        return repr(self.obj)


    def irns(self):
        return [s.irn for t in self.obj]


    def names(self):
        return [s.name for t in self.obj]


    def best_match(self, name=None, site=None):
        """Finds the best match for a given name in this list"""
        matches = [s for s in self if self.same(s.country, site.country)]
        if site.state_province:
            matches = [s for s in self if self.same(s.state_province,
                                                    site.state_province)]
        if site.county:
            matches = [s for s in self if self.same(s.county, site.county)]
        return self.__class__(matches)


    def copy(self):
        return self.__class__(self[:])


    @staticmethod
    def same(val1, val2):
        return val1.lower() == val2.lower()