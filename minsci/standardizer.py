"""Standardizes strings for comparison"""
import re

from unidecode import unidecode


class Standardizer(object):
    _terms = None
    _collations = {
        'ae': 'a',
        'oe': 'o',
        'ue': 'u'
    }

    def __init__(self, terms=None, force_lower=True, force_ascii=True,
                 remove_chars=' !"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\'\t\n',
                 remove_collations=False, minlen=3, delim='-', dedelimit=False):
        self.terms = None
        self.update_terms(terms)
        self.force_lower = force_lower
        self.force_ascii = force_ascii
        self.remove_chars = remove_chars
        self.remove_collations = remove_collations
        self.minlen = 2
        self.delim = '-'
        self.dedelimit = dedelimit


    def __call__(self, *args, **kwargs):
        return self.std(*args, **kwargs)


    def std(self, val, pre=None, post=None, minlen=None):
        """Standardizes value in preparation for matching"""
        if isinstance(val, list):
            return [self.std(s) for s in val]
        if val is None:
            return ''
        orig = val
        # Force value to string and coerce based on classwide attributes
        val = str(val)
        # Run pre functions
        if pre is not None:
            for func in pre:
                val = func(val)
        # Run basic formatting functions
        if self.force_lower:
            val = val.lower()
        if self.force_ascii:
            val = unidecode(val)
        if self.remove_collations:
            for search, repl in self._collations.items():
                val = val.replace(search, repl)
        # Special handling for apostrophes to catch spellings like Hawai'i
        val = re.sub(r"([a-z])'([a-z])", r'\1\2', val)
        # Remove specical characters
        for char in self.remove_chars:
            val = val.replace(char, self.delim)
        # Replace abbreviations, etc. from keyword dict with standard value
        for search, repl in sorted(self.terms.items(),
                                   key=lambda kv: -len(kv[0])):
            val = re.sub(r'(\b)' + search + r'(\b)',
                         r'\1' + repl + r'\2',
                         val)
        val = val.strip(self.delim)
        # Run post functions
        if post is not None:
            for func in post:
                val = func(val)
        # Reduce multiple hyphens in a row to a single hyphen
        val = re.sub('-+', self.delim, val).strip(self.delim)
        # Limit to terms >= minimum length. This should always be done after
        # substitutions.
        if minlen is None:
            minlen = self.minlen
        if minlen and len(val) > self.minlen:
            val = self.delim.join([s for s in val.split(self.delim)
                            if s.isnumeric() or len(s) >= self.minlen])
        if self.dedelimit:
            val = val.replace(self.delim, '')
        return val


    def strip_words(self, val, words, before=True, after=True):
        for word in words:
            val = self.strip_word(val, word, before, after)
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
        'i': '',
        'isla': '',
        'island': '',
        'islands': '',
        'monte': 'mt',
        'mount': 'mt',
        'mtn': 'mountain',
        'mtns': 'mountains',
        'penin': 'peninsula',
        'pref': 'prefecture',
        'prov': 'province',
        'pt': 'point',
        'r': 'river',
        'reg': 'region',
        'st': 'saint',
        'ste': 'saint',
        'the': '',
        'twp': 'township'
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('minlen', 3)
        super(LocStandardizer, self).__init__(*args, **kwargs)


    def std(self, *args, **kwargs):
        kwargs.setdefault('pre', []).append(self.standardize_directions)
        kwargs.setdefault('pre', []).append(self.strip_parentheticals)
        kwargs.setdefault('post', []).append(self.standardize_features)
        kwargs.setdefault('post', []).append(self.remove_admin_terms)
        return super(LocStandardizer, self).std(*args, **kwargs)


    def sitify(self, val, patterns=None):
        """Converts a description approximating a site to that site's name"""
        if patterns is None:
            patterns = [
                r'\bnear( the)?\b',
                r'\barea$',
                r'^center of\b',
                r'^just [nsew] of\b',
                r'^middle of\b',
                r'^summit of\b',
                r'\bsummit$'
            ]
        for pattern in patterns:
            val = re.sub(pattern, '', val, flags=re.I).strip()
        return val


    def strip_parentheticals(self, val):
        """Removes explanatory parentheicals"""
        terms = [
            'mtn?s?',
            'spring',
            'valley'
        ]
        for term in sorted(terms, key=len, reverse=True):
            val = re.sub(r'\({}\.?\)'.format(term), '', val, flags=re.I).strip()
        return val


    def standardize_directions(self, val, lower=False):
        """Standardizes cardinal directions"""
        orig = val
        # Standardize N. to N
        def callback(m):
            return m.group(1).upper()
        val = re.sub(r'\b([NSEW])\.', callback, val, flags=re.I)
        # Standardize N.W. or N. W. to NW
        def callback(m):
            return (m.group(1) + m.group(2)).upper()
        val = re.sub(r'\b([NS])[ -]([EW])\b', callback, val, flags=re.I)
        # Standardize patterns close to N60W, etc.
        pattern = r'(\b[NS])[ -]?(\d+)[ -]?([EW]\b.)'
        def callback(m):
            return (m.group(1) + m.group(2) + m.group(3)).upper().rstrip('.')
        val = re.sub(pattern, callback, val, flags=re.I)
        if lower:
            return val.lower()
        return val


    def standardize_features(self, val):
        """Standardizes feature name so that type occurs at beginning

        For example, mount and lake will always occur at the beginning of the
        string if this function is applied. This accounts for inversions
        between EMu and GeoNames (e.g., Mount Green vs. Green Mountain).
        """
        words = val.split(self.delim)
        for word in ['bay', 'cape', 'mount', 'lake']:
            if words[-1] == word:
                words.insert(0, word)
                del words[-1]
        return self.delim.join(words)


    def remove_admin_terms(self, val):
        """Removes names of administrative divisions"""
        terms = [
            'county',
            'department',
            'district',
            'oblast',
            'prefecture',
            'province',
            'township'
        ]
        for term in sorted(terms, key=len, reverse=True):
            val = re.sub(r'\b{}\b'.format(term), '', val)
        return val


if __name__ == '__main__':
    vals = [
        'St. Francois Co.',
        'Himalaya Mtns',
        'Sierra de Cordoba (Mtn.)',
        'Bock Mtns. (Sw Of)'
    ]
    std = LocStandardizer(minlen=0)
    for val in vals:
        print(val, '=>', std(val))
