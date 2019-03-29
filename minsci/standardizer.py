"""Standardizes strings for comparison"""
import re

from unidecode import unidecode


class Standardizer(object):
    _terms = None
    _collations = {
        'oe': 'o'
    }

    def __init__(self, terms=None, force_lower=True, force_ascii=True,
                 remove_chars=' !"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\'\t\n',
                 remove_collations=False):
        self.terms = None
        self.update_terms(terms)
        self.force_lower = force_lower
        self.force_ascii = force_ascii
        self.remove_chars = remove_chars
        self.remove_collations = remove_collations


    def __call__(self, *args, **kwargs):
        return self.std(*args, **kwargs)


    def std(self, val, custom=None):
        """Standardizes value in preparation for matching"""
        if isinstance(val, list):
            return [self.std(s) for s in val]
        if val is None:
            return ''
        orig = val
        # Force value to string and coerce based on classwide attributes
        val = str(val)
        if self.force_lower:
            val = val.lower()
        if self.force_ascii:
            val = unidecode(val)
        if self.remove_collations:
            for search, repl in self._collations.items():
                val = val.replace(search, repl)
        for char in self.remove_chars:
            val = val.replace(char, '-')
        # Replace abbreviations, etc. from keyword dict with standard value
        for search, repl in sorted(self.terms.items(),
                                   key=lambda kv: -len(kv[0])):
            val = re.sub(r'(\b)' + search + r'(\b)',
                         r'\1' + repl + r'\2',
                         val)
        if custom is not None:
            for func in custom:
                val = func(val)
        # Reduce multiple hyphens in a row to a single hyphen
        val = re.sub('-+', '-', val).strip('-')
        #print('{} => {}'.format(orig, val))
        return val


    def strip_word(self, val, word, before=True, after=True):
        val = self.std(val)
        word = self.std(word)
        if before and val.startswith(word):
            val = val[len(word):]
        if after and val.endswith(word):
            val = val[:-len(word)]
        return val.strip('- ')


    def update_terms(self, terms):
        """Updates the dictionary used for keyword replacement"""
        if self.terms is None and terms is None:
            terms = self._terms if self._terms is not None else {}
        self.terms = terms
        return self




class LocStandardizer(Standardizer):
    _terms = {
        'co': 'county',
        'dept': 'department',
        'dist': 'district',
        'historical': '',
        'island': '',
        'islands': '',
        'mt': 'mount',
        'mtn': 'mountain',
        'mtns': 'mountains',
        'prov': 'province',
        'st': 'saint',
        'ste': 'saint',
        'twp': 'township'
    }

    def __init__(self, *args, **kwargs):
        super(LocStandardizer, self).__init__(*args, **kwargs)


    def std(self, *args, **kwargs):
        kwargs.setdefault('custom', []).append(self.standardize_features)
        kwargs.setdefault('custom', []).append(self.remove_admin_terms)
        return super(LocStandardizer, self).std(*args, **kwargs)


    def standardize_features(self, val):
        """Standardizes feature name so that type occurs at beginning

        For example, mount and lake will always occur at the beginning of the
        string if this function is applied. This accounts for inversions
        between EMu and GeoNames (e.g., Mount Green vs. Green Mountain).
        """
        words = val.split('-')
        for word in ['mount', 'lake']:
            if words[-1] == word:
                words.insert(0, word)
                del words[-1]
        return '-'.join(words)


    def remove_admin_terms(self, val):
        """Removes names of administrative divisions"""
        terms = [
            'county',
            'department',
            'district',
            'province',
            'township'
        ]
        for term in sorted(terms, key=len, reverse=True):
            val = re.sub(r'(\b)' + term + r'(\b)', r'\1\2', val)
        return val


if __name__ == '__main__':
    vals = [
        'St. Francois Co.',
        'Himalaya Mtns'
    ]
    std = LocStandardizer()
    for val in vals:
        print(val, '=>', std(val))
