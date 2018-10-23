from __future__ import unicode_literals
from builtins import str
import os
import re

from yaml import load

from .taxalist import TaxaList
from .taxatree import TaxaTree




class TaxaNamer(TaxaTree):
    config = load(open(os.path.join(os.path.dirname(__file__), 'files', 'config.yaml'), 'r'))
    _capex = [str(s) if isinstance(s, int) else s for s in config['capex']]

    def __init__(self, *args, **kwargs):
        super(TaxaNamer, self).__init__(*args, **kwargs)


    def capped(self, name=None, ucfirst=True):
        if name is None:
            name = self.sci_name
        # Filter out codes
        if re.match('\d', name):
            return name
        name = name.lower()
        for word in self._capex:
            pattern = re.compile(r'\b{}\b'.format(word), flags=re.I)
            matches = pattern.findall(name)
            if matches and word.isupper():
                name = pattern.sub(matches[0][0].upper(), name)
            else:
                name = pattern.sub(word, name)
        return name[0].upper() + name[1:] if name and ucfirst else name


    def join(self, names, maxtaxa=3, conj=u'and'):
        conj = u' {} '.format(conj.strip())
        if maxtaxa is not None and len(names) > maxtaxa:
            names = names[:maxtaxa]
        if len(names) <= 2:
            return conj.join(names)
        elif conj.strip() in ['with']:
            first = names.pop(0)
            return u'{} with {}'.format(first, self.join(names, None, u'and'))
        else:
            last = names.pop()
            return u'{},{}{}'.format(', '.join(names), conj, last)


    def name_item(self, taxa, setting=None):
        taxalist = TaxaList()
        for taxon in [t for t in taxa if t]:
            matches = self.place(taxon)  # place always returns one
            taxalist.append(TaxaList([matches]).best_match(taxon, True))
        taxalist = taxalist.unique()
        if setting:
            name = u'{} {}'.format(self.join(taxalist.names()[:2]), setting)
        elif len(taxa) == 1 or len(set(taxalist.names())) == 1:
            name = taxalist[0].sci_name
        else:
            name = self.join(taxalist.names(), conj=u'with')
        return self.capped(name, ucfirst=True)


    def name_group(self, taxa, ucfirst=False):
        return self.join(TaxaList(taxa).names()).lower()
