from __future__ import unicode_literals
import os
import pprint as pp
import re
from itertools import izip_longest as zip

from unidecode import unidecode

from ..xmu import XMuRecord
from .taxaparser import TaxaParser
from .taxalist import TaxaList




class Taxon(dict):
    tree = None

    def __init__(self, data):
        super(Taxon, self).__init__()
        if not data:
            pass
        elif isinstance(data, basestring):
            self.from_name(data)
        elif 'ClaScientificName' in data:
            self.from_emu(data)
        elif 'sci_name' in data:
            self.update(data)
        else:
            raise ValueError(repr(data) + ' is not a Taxon')


    def __getitem__(self, key):
        # Preferred is not stored if this taxon is the preferred name
        if key == 'current' and self.is_current:
            return self.__class__({
                'irn': self.irn,
                'sci_name': self.sci_name
            })
        # Same with official
        #if key == 'official' and self.is_official:
        #    return self.__class__({
        #        'irn': self.irn,
        #        'sci_name': self.sci_name
        #    })
        # Convert to Taxon if dict
        val = super(Taxon, self).__getitem__(key)
        if isinstance(val, dict) and not isinstance(val, self.__class__):
            self[key] = val
            val = self[key]
        return val


    def __setitem__(self, key, val):
        # Coerce dictionaries to Taxon
        if isinstance(val, dict):
            val = self.__class__(val)
        super(Taxon, self).__setitem__(key, val)


    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            pass
        try:
            return super(Taxon, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(attr)


    def __str__(self):
        try:
            return self.name
        except AttributeError:
            return self.sci_name


    def pprint(self, wait=False):
        pp.pprint(self)
        if wait:
            raw_input('Press ENTER to continue')


    def key(self, key):
        """Returns a standardized form of the name"""
        if not isinstance(key, unicode):
            key = unicode(key)
        return unicode(re.sub(r'[^A-Za-z0-9]', u'', unidecode(key)).lower())


    def get_index(self, name):
        """Retrieves the index, creating it if it does not exist"""
        return self.tree.get_index(name)


    def keys(self):
        keys = [self.name, self.sci_name] + [a['code'] for a in self.authorities]
        return sorted(list(set(keys)))


    def facet(self, include_synonyms=True):
        """Facet a taxon for matching"""
        # Add common endings for groups, series, etc.
        variants = [
            self.get('name'),
            self.get('sci_name'),
            self.get('official'),
            self.get('preferred')
        ]
        if include_synonyms:
            variants.extend(self.get('synonyms', []))
        variants = [s['sci_name'] if isinstance(s, dict) else s for s in variants]
        endings = (u' series', u' group', u' (general term)')
        faceted = []
        for term in [s.lower() for s in variants if s]:
            term = term.lower()
            for ending in endings:
                if term.endswith(ending):
                    term = term[:-len(ending)].strip()
                    break
            for val in (term, unidecode(term)):
                faceted.append(val)
                faceted.extend([val + ending for ending in endings])
        return [sp for i, sp in enumerate(faceted) if not sp in faceted[:i]]


    def from_name(self, name):
        try:
            self.update(self._find_one(name))
        except KeyError:
            # Set defaults for an unknown taxon
            self['is_current'] = True
            self['is_official'] = False
            self['authorities'] = []
            parsed = TaxaParser(name)
            name = self.tree.capped(parsed.name)
            self['name'] = name
            self['sci_name'] = name
            self['parent'] = self.autoclassify()
            try:
                self['rank'] = self['parent']['rank']
            except TypeError:
                self['parent'] = self.__class__({
                    'irn': '1014715',
                    'sci_name': 'Unknown'
                })
                self['rank'] = 'unknown'
            self['irn'] = None
            self['gen_name'] = sorted(list(parsed.keywords))


    def to_emu(self):
        rec = XMuRecord({
            'ClaScientificName': self.sci_name,
            'ClaOtherValue_tab': [self.name],
            'ClaOtherRank_tab': [self.rank],
            'RanParentRef': self.parent.irn,
            'ClaCurrentlyAccepted': 'Yes'
        })
        if self.irn is not None:
            rec['irn'] = self.irn
        else:
            rec['NotNotes'] = 'Record created automatically'
        rec.module = 'etaxonomy'
        return rec.expand()


    def from_emu(self, rec):
        try:
            assert len(rec('ClaOtherValue_tab')) == 1
            assert len(rec('ClaOtherRank_tab')) == 1
            assert not rec('ClaSpecies')
        except AssertionError:
            raise AssertionError(rec('irn'))

        self['irn'] = int(rec('irn'))
        self['sci_name'] = rec('ClaScientificName')
        self['rank'] = rec('ClaOtherRank_tab')[0]
        # Get the base name. For some records, this will be the same as the
        # scientific name.
        name = rec('ClaOtherValue_tab')[0]
        if name.count(',') == 1:
            name = ' '.join([s.strip() for s in name.split(',')][::-1])
            if self.key(name) == self.key(self['sci_name']):
                name = self['sci_name']
        self['name'] = name
        # Set parent
        self['parent'] = None
        if rec('RanParentRef', 'irn'):
            self['parent'] = {
                'irn': int(rec('RanParentRef', 'irn')),
                'sci_name': rec('RanParentRef', 'ClaScientificName')
            }
        # Set current
        self['is_current'] = rec('ClaCurrentlyAccepted') == 'Yes'
        if not self['is_current']:
            if rec('ClaCurrentNameRef', 'irn'):
                self['current'] = {
                    'irn': int(rec('ClaCurrentNameRef', 'irn')),
                    'sci_name': rec('ClaCurrentNameRef', 'ClaScientificName')
                }
            else:
                self['current'] = None
        # Set official
        self['is_official'] = (rec('TaxValidityStatus') == 'Valid'
                               and rec('ClaCurrentlyAccepted') == 'Yes')
        # Set authorities
        self['authorities'] = []
        for kind, val in zip(rec('DesLabel0'), rec('DesDescription0')):
            self.authorities.append({'kind': kind, 'val': val})
        '''
        for src, code, ref in zip(rec('TaxValidityComment_tab'),
                                  rec('TaxValidityReason_tab'),
                                  rec('TaxValidityBiblioRef_tab')):
            refs = {
                '10054849': 'Le Maitre et al. (2002)',
                '10062893': 'Le Bas and Streckeisen (1991)'
            }
            src = src if src else ''
            code = code if code else ''
            ref = refs.get(ref['irn'], '') if ref else ''
            self['authorities'].append({'source': src, 'code': code, 'ref': ref})
        '''
        # Set similar
        parsed = TaxaParser(self.sci_name)
        self['gen_name'] = sorted(list(parsed.keywords))


    def preferred(self):
        preferred = self
        i = 0
        while not preferred.is_current:
            preferred = self.tree[preferred.current.irn]
            self.parent = preferred.parent
            i += 1
            if i > 100:
                raise ValueError('Infinite loop: %s', self.name)
        return preferred


    def official(self, full_records=False):
        taxon = self.preferred()
        if not taxon.is_official:
            for parent in taxon.parents(full_records=True)[::-1]:
                if parent.is_official:
                    return parent
        return taxon


    def parents(self, include_self=False, full_records=False):
        parents = []
        taxon = self.preferred()
        while taxon.parent:
            parents.insert(0, taxon.parent)
            taxon = self.tree[taxon.parent.irn]
        if include_self:
            parents.append(Taxon({'irn': self.irn, 'sci_name': self.sci_name}))
        if full_records:
            parents = [self.tree[p.irn] for p in parents if p.irn is not None]
        return TaxaList(parents)


    def codes(self, name=None):
        return [a['code'] for a in self.authorities
                if name is None or name.lower() in a['source'].lower()]


    def kinds(self):
        parsed = TaxaParser(self.sci_name)
        kinds = []
        for part in parsed.parts:
            try:
                matches = self.get_index('stem_index')[part.stem]
            except KeyError:
                return []
            else:
                exact = [m.rank for m in matches if parsed.key(m.sci_name) == part.word]
                if exact:
                    kinds.append(exact[0])
                else:
                    return []
        return kinds


    def verify(self):
        parsed = TaxaParser(self.sci_name)
        unverified = []
        for part in parsed.parts:
            keys = [part.word]
            if part.stem is not None:
                keys.extend([part.stem, part.stem + 'e'])
            for key in keys:
                try:
                    matches = self.get_index('name_index')[key]
                except KeyError:
                    pass
                else:
                    break
            else:
                unverified.append(part.word)
        return unverified


    def indexed(self):
        return TaxaParser(self.sci_name).indexed


    def autoname(self, ucfirst=True, use_preferred=True):
        taxon = self if self.is_current or not use_preferred else self.preferred()
        name = taxon.name
        # Filter out codes
        if re.match('\d', name):
            return name
        if taxon.rank == 'variety':
            for parent in taxon.parents(full_records=True):
                if parent.rank == 'mineral':
                    name = u'{} (var. {})'.format(parent.name, taxon.name)
                    break
        if name.count(',') == 1:
            name = ' '.join([s.strip() for s in name.split(',') if s][::-1])
        return self.tree.capped(name, ucfirst=ucfirst)


    def autoclassify(self, force=False):
        preferred = self.preferred()
        parsed = TaxaParser(preferred.sci_name)
        parents = parsed.parents()
        matches = []
        for parent in parents:
            try:
                matches = self.get_index('stem_index')[parent]
            except KeyError:
                pass
            else:
                matches.sort(key=lambda m: parsed.compare_to(m.sci_name),
                             reverse=True)
                break
        #else:
        #    for key, taxa in self.get_index('stem_index').iteritems():
        #        if (key in parsed.indexed
        #            and key != parsed.indexed
        #            and len(key) > 5):
        #            matches.extend(taxa)
        #        matches.sort(key=lambda m:len(m['name']))
        matches = [m for m in matches if m.sci_name != preferred.sci_name]
        match = matches[0] if matches else None
        #if match:
        #    print '"{}" is a child of "{}"'.format(preferred.sci_name, match.sci_name)
        return match


    def is_same_as(self, other):
        return TaxaParser(self).similar_to(other)


    def _find(self, val, index='name_index'):
        return self.tree.find(val, index)


    def _find_one(self, val, index='name_index'):
        return self.tree.find_one(val, index)


TaxaList.itemclass = Taxon
