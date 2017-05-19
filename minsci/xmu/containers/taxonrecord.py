"""Subclass of XMuRecord with methods specific to emultimedia"""

import json
import os
import re
from collections import namedtuple

from unidecode import unidecode

from .xmurecord import XMuRecord
from ..constants import FIELDS




JSONPATH = os.path.join(os.path.dirname(__file__), '..', 'files', 'taxa', 'geotaxa.json')

Part = namedtuple('Part', ['word', 'stem', 'rank'])


class _Taxon(XMuRecord):
    """Taxon container with no methods requiring knowledge of the tree"""

    def __init__(self, *args, **kwargs):
        super(_Taxon, self).__init__(*args, **kwargs)
        self._modifiers = ('', 'var')
        self.fields = FIELDS
        self.module = 'etaxonomy'
        # Quick integrity check
        if self:
            try:
                assert len(self('ClaOtherValue_tab')) == 1
                assert len(self('ClaOtherRank_tab')) == 1
            except AssertionError:
                raise AssertionError(self('irn'))


    def find(self, val=None):
        if self.taxa is None:
            return True
        else:
            return self.taxa.get(self.key(val))


    def key(self, val=None):
        """Returns a standardized form of the name"""
        if val is None:
            val = self.name()
        return unicode(re.sub(r'[^A-Za-z0-9 \-]', '', unidecode(val)).lower())


    def name(self):
        """Returns the formatted name"""
        return self('ClaScientificName')


    def value(self):
        return self('ClaOtherValue_tab')[0]


    def rank(self):
        return self('ClaOtherRank_tab')[0]


    def is_defined(self):
        """Checks if a taxon is defined beyond having a name"""
        return (self.is_official()
                or bool(self('TaxValidityReason_tab'))
                or bool(self('CitCitedInRef_tab'))
                or bool(self('CitSpecimenRef_nesttab'))
                or bool(self('DesLabel0'))
                or bool(self('DesDescription0')))


    def is_official(self):
        return self('TaxValidityStatus') == 'Valid'


    def is_accepted(self):
        return self('ClaCurrentlyAccepted').lower() == 'yes'


    def segment(self):
        """Splits a name into segments"""
        name = self.key().rstrip(') ')
        if '(var' in name:
            main = name.split('(var')[1].strip(' .)')
            return [Part(main, self.stem(main), 0)]
        # Split into parts, checking for hyphenates
        try:
            mod, main = name.rsplit(' ', 1)
        except ValueError:
            mod = ''
            main = name
        parts = [Part(main, self.stem(main), 0)]
        for i, modifier in enumerate(re.split('\W', mod)):
            if modifier in self._modifiers:
                continue
            parts.append(Part(modifier, self.stem(modifier), i + 1))
        return parts


    def stem(self, val):
        """Stems a value"""
        # Exclude numerics (e.g., Dana groups)
        if val and val[0].isdigit():
            return None
        # Strip endings
        endings = [
            'ally',
            'e',
            'ey',
            'ian',
            'ic',
            'ically',
            'iferous',
            'itic',
            'ium',
            'oan',
            'ose',
            'ous',
            'y'
        ]
        endings.sort(key=len, reverse=True)
        if self.taxa is not None:
            endings.insert(0, '')
        else:
            endings.append('')
        for ending in endings:
            if val.endswith(ending):
                stem = val[:-len(ending)] if ending else val
                if val != stem and self.find(stem):
                    return stem
        if self.taxa is None or self.find(val):
            return val


    def parent_key(self, parts=None):
        """Converts a list of parts a key"""
        if parts is None:
            parts = self.segment()
        return '|'.join(['{}-{}'.format(p.rank, p.stem) for p in parts])




class Taxon(_Taxon):
    """Taxon container including methods that require knowledge of the tree"""

    def __init__(self, *args, **kwargs):
        super(Taxon, self).__init__(*args, **kwargs)
        self._kind = None
        self._tree = None
        self._preferred = None


    def __getattr__(self, key):
        if key in ('taxa', '_parents'):
            self.__setattr__(key, LOOKUPS[key])
            return LOOKUPS[key]
        raise AttributeError(key)


    def kind(self):
        """Returns the type of material (rock, mineral, etc.)"""
        if self._kind is not None:
            return self._kind
        tree = [rec.name() for rec in self.tree()]
        kinds = ['Meteorite', 'Minerals', 'Rocks and Sediments']
        for kind in kinds:
            if kind in tree:
                break
        else:
            kind = self.rank()
        self._kind = kind if kind is None else kind.split(' ')[0].rstrip('s').lower()
        return self._kind


    def official(self):
        """Returns the nearest officially recognized taxon"""
        rec = self
        while rec is not None and not rec.is_official():
            rec = self.parent()
        return rec


    def parent(self):
        """Returns the parent of this taxon"""
        irn = self('RanParentRef', 'irn')
        if irn:
            return self.taxa[irn]


    def preferred(self):
        """Returns the preferred taxon"""
        if self._preferred is not None:
            return self._preferred
        rec = self
        while rec.is_accepted():
            irn = rec('ClaCurrentNameRef', 'irn')
            if not irn or irn == rec('irn'):
                break
            rec = self.taxa[irn]
        self._preferred = rec
        return rec


    def tree(self):
        """Returns an ordered list of higher taxonomic levels"""
        if self._tree is not None:
            return self._tree
        tree = []
        rec = self.preferred()
        while rec is not None:
            tree.append(rec)
            parent = self.parent()
            if rec == parent:
                break
            rec = parent
        self._tree = tree[::-1]
        return self._tree


    def classify(self):
        """Classifies the parts of a taxon"""
        parts = self.segment()
        # If there's only one part, there's no need for this
        if len(parts) == 1:
            return None
        # Check if any part does not resolve to a taxon
        stems = [p.stem for p in parts]
        if None in stems:
            return None
        return [self.taxa[p.stem] for p in parts]


    def autoparent(self):
        """Guesses parent for current record"""
        # Always return the defined parent for defined species
        if self.is_defined():
            return self.parent()
        parts = self.segment()[:-1]
        if not parts:
            return None
        while parts:
            key = self.parent_key(parts)
            try:
                rec = self._parents[key]
            except KeyError:
                pass
            else:
                #print 'Assigned {} to {}'.format(self.name(), rec.name())
                return rec
            parts.pop()
        raise KeyError('Could not assign parent for "{}"'.format(self.name()))


    def autosynonym(self):
        """Guesses preferred synonym for current record"""
        # Always return the defined synonym for defined species
        if self.is_defined():
            return self.taxa[self('ClaCurrentNameRef', 'irn')]
        # Standardize the name
        parts = self.segment()
        for part in parts:
            try:
                preferred = self.taxa[part].preferred().name()
            except KeyError:
                print preferred, None
            else:
                print part, preferred




def select_best_taxon(*recs):
    """Selects the preferred record from a list of duplicates"""
    recs = list(recs)
    recs.sort(key=lambda rec: int(rec('irn')))
    cited = [rec for rec in recs if rec('CitSpecimenRef_nesttab')]
    official = [rec for rec in recs if rec.is_official()]
    defined = [rec for rec in recs if rec.is_defined()]
    accepted = [rec for rec in recs if rec.is_accepted()]
    if (cited and official and cited != official
        or cited and defined and cited != defined):
        irns = [rec('irn') for rec in recs]
        raise ValueError('Could not determine best: {}'.format(irns))
    for param in (cited, official, defined, accepted):
        if param:
            return param[0]
    # If all else fails, select the lowest irn
    return recs[0]


try:
    LOOKUPS = {key: {k: Taxon(v) for k, v in val.iteritems()} for key, val
               in json.load(open(JSONPATH, 'rb')).iteritems()}
except (IOError, ValueError):
    LOOKUPS = {}
