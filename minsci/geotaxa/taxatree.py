from __future__ import print_function
from __future__ import unicode_literals
from builtins import str
import pprint as pp
import re
from collections import MutableMapping

from unidecode import unidecode

from ..xmu import write
from .taxalist import TaxaList
from .taxaparser import TaxaParser
from .taxon import Taxon




class TaxaIndex(MutableMapping):

    def __init__(self, *args, **kwargs):
        self.obj = dict(*args, **kwargs)
        self.new = {}


    def __getattr__(self, attr):
        try:
            return super(TaxaIndex, self).__getattr__(attr)
        except AttributeError:
            try:
                return self[attr]
            except KeyError:
                return AttributeError(attr)


    def __getitem__(self, key):
        try:
            return self.obj[self.key(key)]
        except KeyError:
            return self.new[self.key(key)]


    def __setitem__(self, key, val):
        if type(val) == dict:
            val = Taxon(val)
        self.obj[self.key(key)] = val


    def __delitem__(self, key):
        del self.obj[self.key(key)]


    def __iter__(self):
        return iter(self.obj)


    def __len__(self):
        return len(self.obj)


    def __str__(self):
        return pp.pformat(self.obj)


    def __repr__(self):
        return repr(self.obj)


    def key(self, key):
        """Returns a standardized form of the name"""
        if not isinstance(key, str):
            key = str(key)
        return str(re.sub(r'[^A-Za-z0-9]', u'', unidecode(key)).lower())


    def one(self, key):
        try:
            matches = self[key]
        except KeyError:
            raise KeyError('No matches on "{}"'.format(self.key(key)))
        # Result is a taxon record
        if isinstance(matches, dict):
            return matches
        # Result is a list of matching records
        if len(matches) == 1:
            return matches[0]
        elif not matches:
            raise KeyError('No matches on "{}"'.format(self.key(key)))
        else:
            raise KeyError('Multiple matches on "{}"'.format(self.key(key)))




class TaxaTree(TaxaIndex):
    name_index = None
    stem_index = None

    def __init__(self, *args, **kwargs):
        super(TaxaTree, self).__init__()
        if args:
            self.update(*args, **kwargs)
        self.indexers = {
            'name_index': self.create_name_index,
            'stem_index': self.create_stem_index
        }


    def write_new(self, fp='import.xml'):
        if self.new:
            taxa = [self.new[k] for k in sorted(self.new.keys())]
            write(fp, [t.to_emu() for t in taxa], 'etaxonomy')


    def create_name_index(self):
        index = self.__class__()
        for key, taxon in self.items():
            index.setdefault(taxon.sci_name, []).append(taxon.irn)
            if taxon.sci_name != taxon.name:
                index.setdefault(taxon.name, []).append(taxon.irn)
        index = self.__class__({k: sorted(list(set(v))) for k, v in index.items()})
        #duped = {k: v for k, v in index.iteritems() if len(v) > 1}
        #if duped:
        #    print duped
        #    raise ValueError('Duplicates found: {}'.format(duped.keys()))

        return index


    def create_stem_index(self):
        index = self.__class__()
        for key, taxon in self.items():
            index.setdefault(taxon.indexed(), []).append(taxon)
        return index


    def find(self, val, index='name_index'):
        if index is None:
            return self[val]
        else:
            return [self[irn] for irn in self.get_index(index)[val]]


    def find_one(self, val, index='name_index'):
        matches = self.find(val, index)
        if isinstance(matches, list):
            return TaxaList(matches).best_match(val)


    def place(self, name):
        """Places a name in the taxonomic hierarchy, adding it if needed"""
        assert name.strip()
        qualifier = u'uncertain' if name.endswith('?') else u''
        name = name.rstrip('?')
        try:
            taxon = self.find_one(name)
        except KeyError:
            parsed = TaxaParser(name)
            try:
                taxon = self.find_one(parsed.name)
            except KeyError:
                taxon = Taxon(name)
                taxon['irn'] = self.key(name)
                self.new[self.key(name)] = taxon
            # Create a copy and add the parsed name
            taxon = Taxon({k: v for k, v in taxon.items()})
            taxon[u'parsed'] = parsed
        taxon[u'qualifier'] = qualifier
        return taxon


    def group(self, taxa):
        return TaxaList(taxa).group()


    def get_index(self, name):
        """Retrieves the index, creating it if it does not exist"""
        index = getattr(self, name)
        if index is None:
            print('Creating {}...'.format(name))
            setattr(self, name, self.indexers[name]())
            index = getattr(self, name)
            print('Done!')
        return index


    def _assign_synonyms(self):
        for key, taxon in self.items():
            if not taxon.is_current:
                try:
                    current = self[taxon.current.irn]
                except (AttributeError, KeyError):
                    # Records with unknown current name end up here
                    pass
                else:
                    current.setdefault('synonyms', TaxaList()).append({
                        'irn': taxon.irn,
                        'sci_name': taxon.sci_name
                    })


    def _assign_similar(self):
        similar = {}
        for key, taxon in self.items():
            if taxon.gen_name:
                similar.setdefault(tuple(taxon.gen_name), []).append({
                    'irn': taxon.irn,
                    'sci_name': taxon.sci_name
                })
        for key, taxa in similar.items():
            if len(taxa) > 1:
                for taxon in taxa:
                    matches = [t for t in taxa if t['irn'] != taxon['irn']]
                    taxon = self[taxon['irn']]
                    taxon.setdefault('similar', TaxaList()).extend(matches)


    def _assign_official(self):
        for key, taxon in self.items():
            if not taxon.is_official:
                parent = taxon
                while parent.parent:
                    parent = self[parent.parent.irn]
                    if parent.is_official:
                        taxon['official'] = {
                            'irn': parent.irn,
                            'rank': parent.rank,
                            'sci_name': parent.sci_name
                        }
                        break