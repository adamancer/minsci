from __future__ import unicode_literals
from builtins import str

import logging
logger = logging.getLogger(__name__)

import re
from collections import namedtuple, MutableSequence

from unidecode import unidecode

from .helpers import eq
from ...standardizer import LocStandardizer




class SiteList(MutableSequence):
    itemclass = None
    gl_bot = None
    gn_bot = None

    def __init__(self, *args, **kwargs):
        self._obj = [self.itemclass(s) if type(s) != self.itemclass else s
                     for s in list(*args, **kwargs)]
        self.orig = self._obj[:]
        self._std = LocStandardizer(remove_collations=True)
        self._filters = []
        self._aggressive = False


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


    def clone(self):
        return self.__class__(self._obj[:])


    def irns(self):
        return [s.irn for t in self._obj]


    def names(self):
        return [s.name for t in self._obj]


    def dedupe(self, lst):
        return [s for i, s in enumerate(lst) if s not in lst[:i]]


    def filters(self):
        return self.dedupe(self._filters)


    def filter(self, name=None, site=None, attr=None, syndex=3):
        self._match(name, site=site, attr=attr, syndex=syndex)
        if not self:
            # Test name against blacklist before attempting a more
            # aggressive search
            if name in set(['township',
                            'village']):
                return self
            self._filters = []
            self._aggressive = True
            self._match(name, site=site, attr=attr, syndex=syndex)
            self._aggressive = False
        return self


    def _match(self, name=None, site=None, attr=None, syndex=3):
        """Finds the best match for a given name in this list"""
        assert self._check_codes()
        orig_filters = self.filters()[:]
        field = attr if attr else 'value'
        logging.debug('Filtering on {}="{}"...'.format(field, name))
        while True:
            self._filters = orig_filters[:]
            # Match from most to least specific attribute
            if name is not None and self:
                self._match_name(name, attr=attr)
            if site is not None and self:
                self._match_site(site)
            # If match fails, query geonames for additional synonyms and retry
            if not self and syndex:
                self.get_additional_synonyms()
                syndex = None
            else:
                break
        logger.debug('{}/{} records matched filter'.format(len(self._obj),
                                                           len(self.orig)))
        return self


    def get_additional_synonyms(self, syndex=3):
        self._obj = self.orig[:]
        for i, site in enumerate(self._obj):
            if i < syndex:
                site.find_synonyms()


    def match_one(self, name=None, site=None, attr=None, **kwargs):
        matches = self.match(name=name, attr=attr, site=site)
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise ValueError('Multiple records matched filter')
        else:
            raise ValueError('No records matched filter')


    def _match_name(self, name, attr=None):
        if self._obj:
            logger.debug('Filtering on name="{}"...'.format(name))
            matches = []
            orig = name
            name = self._std_to_field(name, attr)
            for site in self:
                names = [self._std_to_field(n, attr)
                         for n in site.site_names + site.synonyms]
                matched = self._eq(name, names)
                if matched:
                    matches.append(site)
                stnames = str(names)[:60] + '...'
                in_ = 'in' if matched else 'not in'
                logger.debug('{} {} {}...'.format(name, in_, str(names)[:80]))
            self._obj = matches
            if self._obj:
                if self._aggressive:
                    orig = '%{}%'.format(orig)
                self._filters.extend([{'_name': orig}, {attr: 1}])
        return self


    def _match_site(self, site):
        # Match countires/ADM2
        if site.admin_code_2:
            self.match_attr(site, 'admin_code_2')
        elif site.county:
            self.match_attr(site, 'county')
        # Match states/ADM1
        if site.admin_code_1:
            self.match_attr(site, 'admin_code_1')
        elif site.state_province:
            self.match_attr(site, 'state_province')
        # Match countries/REQUIRED
        if site.country_code:
            self.match_attr(site, 'country_code')
        elif site.country:
            self.match_attr(site, 'country')
        elif site.ocean or site.sea:
            # Ocean/sea names are squirrelly, so check that they exist but
            # don't try to match on it
            pass
        else:
            raise ValueError('Country/ocean missing: {}'.format(repr(site)))
        return self


    def match_attr(self, site, attr):
        if self._obj:
            refval = getattr(site, attr)
            scored = [self.score_one(refval, getattr(s, attr)) for s in self]
            maxscore = max(scored) if scored else 0
            self._filters.append({attr: maxscore})
            if maxscore >= 0:
                self._obj = [m for m, s in zip(self, scored) if s == maxscore]
            else:
                self._obj = []
        return self


    def _check_codes(self):
        for site in self:
            try:
                site.codes[site.site_kind]
            except KeyError:
                raise KeyError('Unrecognized code: {}'.format(site.site_kind))
        return True


    def score_one(self, val1, val2, points=1):
        score = 0
        if bool(val1) == bool(val2):
            score = points if self._eq(val1, val2) else -points
        eq = '==' if score >= 0 else '!='
        logger.debug('{} {} {}'.format(val1, eq, val2))
        return score


    def std(self, val):
        if isinstance(val, list):
            return [self._std(s) for s in val]
        return self._std(val)


    def _std_to_field(self, name, attr):
        """Creates a list of names customized for the field being match on"""
        words = {
            'island': ['isla', 'isle', 'island'],
            'water_body': ['ocean', 'sea'],
            'volcano': ['mt', 'mount', 'mountain', 'volcano']
        }
        name = self.std(name)
        # Field-specific words
        words = words.get(attr, [])
        for word in words:
            pattern = r'\b{}\b'.format(word)
            name = re.sub(pattern, '', name)
        # Terms related to mountains are by far the most likely to miss due
        # to formatting/voacab issues, so standardize them here
        if self._aggressive:
            words = ['mont', 'monte', 'mountains?', 'mount', 'mts', 'mt']
            for word in words:
                pattern = r'\b{}\b'.format(word)
                name = re.sub(pattern, 'mt', name)
            if 'mt' in name:
                words = [w for w in name.split('-') if w !='mt']
                words.insert(0, 'mt')
                name = '-'.join(words)
        # Strip neighborhood terms
        name = self._std.strip_words(name, ['area', 'near', 'nr', 'off',
                                            'vicinity', 'vicinity'])
        name = name.replace('-', '')
        return name


    def _eq(self, val1, val2):
        """Tests if values match by equals or in"""
        return eq(val1,
                  val2,
                  std=self._std,
                  strict=False,
                  aggressive=self._aggressive)
