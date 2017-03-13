"""Summarizes and generates metadata for the objects in an ecatalogue export"""

import pprint as pp

from ..describer import summarize
from ....xmu import XMu, MinSciRecord
from ....helpers import parse_catnum


class Cataloger(XMu):
    """Contains methods to generate metadata for a set of catalog objects"""

    def __init__(self, *args, **kwargs):
        kwargs['container'] = MinSciRecord
        super(Cataloger, self).__init__(*args, **kwargs)
        self.catalog = {}
        self.media = {}
        self.fast_iter()


    def iterate(self, element):
        """Indexes the objects in an EMu export file"""
        rec = self.parse(element)
        # Add record to catalog index
        identifiers = set([rec.get_catnum(include_code=False),
                           rec.get_identifier(include_code=False)])
        for identifier in identifiers:
            dct = self.catalog
            indexed = self.index_identifier(identifier)
            for index in indexed[:-1]:
                dct.setdefault(index, {})
                dct = dct[index]
            dct.setdefault(indexed[-1], []).append(rec)
        # Add media to media index
        for irn in rec('MulMultiMediaRef_tab', 'irn'):
            self.media.setdefault(irn, []).append(rec('irn'))


    def get(self, identifier, default=None):
        """Retrieves catalog data matching a given identifier"""
        dct = self.catalog
        for index in self.index_identifier(identifier):
            try:
                dct = dct[index]
            except KeyError:
                return default
        return [summarize(rec) for rec in dct]


    def pprint(self, pause=False):
        """Pretty prints the catalog dictionary"""
        pp.pprint(self.catalog)
        if pause:
            raw_input('Paused. Press ENTER to continue.')


    @staticmethod
    def index_identifier(identifier):
        """Indexes identification numbers from a catalog record"""
        if not isinstance(identifier, dict):
            parsed = parse_catnum(identifier)
        else:
            parsed = [identifier]
        if len(parsed) > 1:
            raise ValueError('Tried to index multiple catalog numbers')
        parsed = parsed[0]
        # Get Antarctic meteorites
        metname = parsed.get('MetMeteoriteName')
        if metname:
            return metname.split(',', 1)
        # Get everything else
        keys = ('CatPrefix', 'CatNumber', 'CatSuffix')
        indexed = [parsed.get(key) for key in keys]
        indexed = [index if index else None for index in indexed]
        return indexed
