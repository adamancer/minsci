from __future__ import unicode_literals
from builtins import str

import re
from collections import MutableSequence

from unidecode import unidecode




class SiteList(MutableSequence):
    itemclass = None

    def __init__(self, *args, **kwargs):
        self._obj = [self.itemclass(site) for site in list(*args, **kwargs)]
        self.orig = self._obj[:]
        standardize = {
            'co': '',
            'county': '',
            'dist': '',
            'district': '',
            'historical': '',
            'prov': '',
            'province': '',
            'saint': 'st',
            'ste': 'st',
            'mts': 'mt',
            'mount(?:ains?)?': 'mt'
        }
        self.standardize = [(k, v) for k, v in standardize.items()]
        self.standardize.sort(key=len, reverse=True)


    def __getitem__(self, i):
        return self._obj[i]


    def __setitem__(self, i, val):
        self._obj[i] = self.itemclass(val)


    def __delitem__(self, i):
        del self._obj[i]


    def __len__(self):
        return len(self._obj)


    def insert(self, i, val):
        self._obj.insert(i, self.itemclass(val))


    def restore(self):
        self._obj = self.orig[:]


    def __contains__(self, val):
        return val in self._obj


    def __str__(self):
        return str(self._obj)


    def __repr__(self):
        return repr(self._obj)


    def irns(self):
        return [s.irn for t in self._obj]


    def names(self):
        return [s.name for t in self._obj]


    def match(self, name=None, site=None):
        """Finds the best match for a given name in this list"""
        if site is not None:
            self._match_site(site)
        if name is not None:
            self._match_name(name)
        return self


    def match_one(self, name=None, site=None):
        matches = self.match(name=name, site=site)
        if len(matches) == 1:
            return matches[0]
        raise ValueError('Could not match uniquely')


    def _match_name(self, name):
        #print('Matching name={}...'.format(name))
        matches = []
        name = self._std(name)
        for site in self:
            names = [self._std(n) for n in site.site_names + site.synonyms]
            matched = name in names
            if matched:
                matches.append(site)
            print("'{}'".format(name), 'in' if matched else 'not in', names)
        self._obj = matches
        return self


    def _match_site(self, site):
        self.match_attr(site, 'country')
        if site.state_province:
            self.match_attr(site, 'state_province')
        if site.county:
            self.match_attr(site, 'county')
        return self


    def copy(self):
        return self.__class__(self[:])


    def match_attr(self, site, attr):
        refval = getattr(site, attr)
        scored = [self.score_one(refval, getattr(s, attr)) for s in self]
        maxscore = max(scored)
        if maxscore >= 0:
            self._obj = [m for m, s in zip(self, scored) if s == maxscore]
        else:
            self._obj = []
        return self


    def score_one(self, val1, val2, points=1):
        score = 0
        if bool(val1) == bool(val2):
            score = points if self._std(val1) == self._std(val2) else -points
        print(val1, '==' if score >= 0 else '!=', val2)
        return score


    def _std(self, val):
        orig = val
        if not val:
            val = ''
        val = unidecode(val)
        # Strip punctuation
        for char in ' !"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n':
            val = val.replace(char, '-')
        val = re.sub('-+', '-', val).lower().strip('-')
        for search, repl in self.standardize:
            val = re.sub(r'(\b)' + search + r'(\b)',
                         r'\1' + repl + r'\2',
                         val).strip('-')
        #print('{} => {}'.format(orig, val))
        return val
