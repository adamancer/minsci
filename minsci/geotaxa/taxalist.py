from __future__ import unicode_literals
from builtins import str
from collections import MutableSequence




class TaxaList(MutableSequence):
    itemclass = None

    def __init__(self, *args, **kwargs):
        self.obj = [self.itemclass(taxon) for taxon in list(*args, **kwargs)]


    def __getitem__(self, i):
        return self.obj[i]


    def __setitem__(self, i, val):
        self.obj[i] = self.itemclass(val)


    def __delitem__(self, i):
        del self.obj[i]


    def __len__(self):
        return len(self.obj)


    def enchance(self):
        self.obj = [self.itemclass(taxon) for taxon in taxa]
        return self


    def insert(self, i, val):
        self.obj.insert(i, self.itemclass(val))


    def __contains__(self, val):
        return val in self.irns() or val in self.sci_names() or val in list(self)


    def __str__(self):
        return str(self.sci_names())


    def __repr__(self):
        return repr(self.obj)


    def irns(self):
        return [t.irn for t in self.obj]


    def names(self):
        return [t.name for t in self.obj]


    def sci_names(self):
        return [t.sci_name for t in self.obj]


    def best_match(self, name=None, force_match=True):
        """Finds the best match for a given name in this list"""
        # Finds taxa with same scientific name
        matches = [i for i, t in enumerate(self) if t]
        # Finds taxa with similar scientific name
        if not matches:
            matches = [i for i, t in enumerate(self) if t.is_same_as(name)]
        # Finds taxa with same short name
        if not matches:
            matches = [i for i, t in enumerate(self)
                      if t.key(name) == t.key(t.name)]
        # Finds official
        if len(matches) > 1:
            official = [i for i, t in enumerate(self) if t.is_official]
            overlap = set(official).intersection(matches)
            if overlap:
                matches = list(overlap)
        unique = self.unique()
        # Finds official... again
        if len(unique) > 1:
            matches = [t for t in unique if t.is_official]
            if matches:
                unique = matches
        # Finds exact matches to the original name
        if len(unique) > 1:
            unique = [t for t in unique if t.sci_name.lower() == name.lower()]
        if len(unique) > 1:
            unique = [t for t in unique if t.key(t.sci_name) == t.key(name)]
        if len(unique) == 1:
            return unique[0]

        if force_match and unique:
            return unique[0]
        if force_match:
            return self[0]
        raise ValueError('{}: {}'.format(name, self.irns()))


    def copy(self):
        return self.__class__(self[:])


    def unique(self):
        """Remove duplicate taxa, including less specific names"""
        all_parents = [t.parents(True, True) for t in self]
        taxa = self.copy()
        for i, parents in enumerate(all_parents):
            parents = TaxaList(parents)
            specific = parents.pop()
            for parent in parents:
                if parent.name != specific.name:
                    while parent.name in taxa.names()[:i]:
                        j = taxa.names().index(parent.name)
                        taxa[j] = specific
        unique = [t for i, t in enumerate(taxa) if t not in taxa[:i]]
        return self.__class__(unique)


    def group(self):
        all_parents = [t.parents(True, True) for t in self]
        for parents in all_parents:
            # Expand parents
            parents = [p.tree[p.irn] for p in parents]
            names = TaxaList(parents).names()
        return self.names()