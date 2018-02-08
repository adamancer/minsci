import os
import shutil

from ..xmu import XMu
from ..xmu.containers import MinSciRecord
from .taxanamer import TaxaNamer
from .taxon import Taxon




class TaXMu(XMu):

    def __init__(self, *args, **kwargs):
        super(TaXMu, self).__init__(*args, **kwargs)
        # The tree contains the primary records for each taxon
        self.tree = TaxaNamer()
        self.autoiterate(['tree'], report=5000)
        # Convert the tree to a TaxaTree
        self.tree = TaxaNamer(self.tree)
        Taxon.tree = self.tree
        MinSciRecord.geotree = self.tree


    def __getattr__(self, attr):
        try:
            return getattr(self.tree, attr)
        except AttributeError:
            try:
                return super(TaxMu, self).__getattr__(attr)
            except AttributeError:
                raise AttributeError(attr)


    def iterate(self, element):
        rec = self.parse(element)
        self.tree[rec('irn')] = Taxon(rec)


    def finalize(self):
        print 'Assigning synonyms...'
        self.tree._assign_synonyms()
        print 'Assigning similar...'
        self.tree._assign_similar()
        print 'Assigning official...'
        self.tree._assign_official()




def get_tree(src=None):
    """Retrieves the taxonomic tree, updating from src if given"""
    assert src is None or src.endswith(('.json', '.xml'))
    fn = 'xmldata{}'.format(os.path.splitext(src)[1]) if src else 'xmldata.xml'
    dst = os.path.join(os.path.dirname(__file__), 'files', fn)
    if src is not None:
        try:
            os.remove(dst)
        except OSError:
            pass
        shutil.copy2(src, dst)
    return TaXMu(dst).tree
