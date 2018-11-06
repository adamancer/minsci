from __future__ import print_function
from __future__ import unicode_literals
from .site import Site
from ..xmu import XMu


class Situate(XMu):

    def __init__(self, *args, **kwargs):
        super(Situate, self).__init__(*args, **kwargs)
        self.autoiterate(['sites'], report=5000)


    def iterate(self, element):
        rec = self.parse(element)
        site = Site(rec)
        print(site)


def get_sites(src=None):
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