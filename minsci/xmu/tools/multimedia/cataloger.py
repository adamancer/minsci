"""Summarizes and generates metadata for the objects in an ecatalogue export"""

import pprint as pp

from ..describer import summarize, Description
from ....xmu import XMu, MinSciRecord
from ....helpers import parse_catnum


class Cataloger(XMu):
    """Contains methods to generate metadata for a set of catalog objects"""

    def __init__(self, *args, **kwargs):
        self.summarize = kwargs.pop('summarize', False)
        kwargs['container'] = MinSciRecord
        super(Cataloger, self).__init__(*args, **kwargs)
        self.catalog = {}
        self.media = {}
        self.keep = ['catalog', 'media']
        try:
            self.load()
        except OSError:
            self.fast_iter(report=25000, callback=self.save)


    def iterate(self, element):
        """Indexes the objects in an EMu export file"""
        rec = self.parse(element)
        data = summarize(rec) if self.summarize else rec
        # Add record to catalog index
        identifiers = [rec.get_catnum(include_code=False),
                       rec.get_identifier(include_code=False)]
        for identifier in set([id_ for id_ in identifiers if id_]):
            dct = self.catalog
            indexed = self.index_identifier(identifier)
            if indexed:
                for index in indexed[:-1]:
                    dct.setdefault(index, {})
                    dct = dct[index]
                dct.setdefault(indexed[-1], []).append(data)
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
        func = summarify if not self.summarize else descriptify
        return [func(rec) for rec in dct]


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
        if not parsed:
            #print 'Could not parse {}'.format(identifier)
            return None
        elif len(parsed) > 1:
            raise ValueError('Tried to index multiple catalog numbers: {}'.format(identifier))
        parsed = parsed[0]
        # Get Antarctic meteorites
        metname = parsed.get('MetMeteoriteName')
        if metname:
            if not ',' in metname:
                return [metname, None]
            return metname.split(',', 1)
        # Get everything else
        keys = ('CatPrefix', 'CatNumber', 'CatSuffix')
        indexed = [parsed.get(key) for key in keys]
        # Force index to string and treat suffixes of 00 and None the same
        indexed = [str(ix) if ix and ix != '00' else 'null' for ix in indexed]
        return indexed


def descriptify(summary):
    """Converts a summary dict to a Description"""
    return Description(*summary)


def summarify(rec):
    return summarize(MinSciRecord(rec))
