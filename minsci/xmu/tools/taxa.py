import os
import shutil

from ..xmu import XMu
from ..containers.taxonrecord import Taxon, _Taxon, select_best_taxon, JSONPATH


class ReadTaxaExport(XMu):

    def __init__(self, *args, **kwargs):
        kwargs['container'] = _Taxon
        super(ReadTaxaExport, self).__init__(*args, **kwargs)
        self.taxa = {}
        self.stemmed = []
        self._parents = {}
        self.keep = ['taxa', '_parents']
        try:
            self.load()
        except (IOError, OSError):
            # Set up and refine the basic taxonomic hierarchy
            self.fast_iter(self.set_basic_lookups, report=10000)
            for key, recs in self.taxa.iteritems():
                try:
                    self.taxa[key] = select_best_taxon(*recs)
                except:
                    print key, recs
                    raise
            # Set up and refine the parent lookup
            self.fast_iter(self.set_advanced_lookups, report=10000)
            for key, recs in self._parents.iteritems():
                keys = [rec.key() for rec in recs]
                if len(set(keys)) == 1:
                    rec = recs[0]
                else:
                    official = [rec for rec in recs if rec.is_defined()]
                    varieties = [rec for rec in recs if 'var.' in rec.key()]
                    elements = [rec for rec in recs if rec.key().endswith('ium')]
                    ends_in_e = [rec for rec in recs if rec.key().endswith('e')]
                    for subset in (official, varieties, elements, ends_in_e):
                        if len(subset) == 1:
                            rec = subset[0]
                            break
                    else:
                        rec = recs[0]
                self._parents[key] = rec
            self.save()


    def set_basic_lookups(self, element):
        rec = self.parse(element)
        rec.taxa = None
        val = rec.value()
        if val.count(',') == 1:
            val = ' '.join([s.strip() for s in val.split(',')][::-1])
        keys = [rec('irn'), rec.key(), rec.key(val)]
        keys.extend([rec.stem(key) for key in set(keys)])
        for key in set([key for key in keys if key]):
            self.taxa.setdefault(key, []).append(rec)


    def set_advanced_lookups(self, element):
        rec = self.parse(element)
        rec.taxa = self.taxa
        self._parents.setdefault(rec.parent_key(), []).append(rec)


def read_taxa():
    """Returns the taxa lookup"""
    return Taxon().taxa


def update_json(fp):
    print 'Updating taxonomy file...'
    try:
        os.remove(JSONPATH)
    except OSError:
        pass
    xmlpath = JSONPATH.rsplit('.', 1)[0] + '.xml'
    shutil.copy2(fp, xmlpath)
    ReadTaxaExport(xmlpath)
    os.remove(xmlpath)
    raise Exception('JSON file created. Re-run script to use the new lookups.')
