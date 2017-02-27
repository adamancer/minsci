import pprint as pp
import re

from ..describer import summarize
from ....xmu import XMu, MinSciRecord
from ....helpers import parse_catnum


class Cataloger(XMu):

    def __init__(self, *args, **kwargs):
        kwargs['container'] = MinSciRecord
        super(Cataloger, self).__init__(*args, **kwargs)
        self.catalog = {}
        self.fast_iter()


    def iterate(self, element):
        rec = self.parse(element)
        identifiers = set([rec.get_catnum(include_code=False),
                           rec.get_identifier(include_code=False)])
        for identifier in identifiers:
            dct = self.catalog
            indexed = self.index_identifier(identifier)
            for index in indexed[:-1]:
                dct.setdefault(index, {})
                dct = dct[index]
            dct.setdefault(indexed[-1], []).append(rec)


    def index_identifier(self, identifier):
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



    def get(self, identifier, default=None):
        dct = self.catalog
        for index in self.index_identifier(identifier):
            try:
                dct = dct[index]
            except KeyError:
                return default
        return [summarize(rec) for rec in dct]


    def pprint(self, pause=False):
        pp.pprint(self.catalog)
        if pause:
            raw_input('Paused. Press ENTER to continue.')
