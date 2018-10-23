from __future__ import unicode_literals
from __future__ import division
from builtins import str
from builtins import range
from builtins import object
from past.utils import old_div
import os
import re
from collections import namedtuple
from pprint import pformat

from unidecode import unidecode
from yaml import load



Part = namedtuple('Part', ['word', 'stem', 'rank', 'pos'])

class TaxaParser(object):
    """Analyzes and segments a rock name"""
    config = load(open(os.path.join(os.path.dirname(__file__), 'files', 'config.yaml'), 'r'))
    _colors = sorted(config['colors'], key=len, reverse=True)
    _modifiers = sorted(config['modifiers'], key=len, reverse=True)
    _textures = sorted(config['textures'], key=len, reverse=True)
    _stopwords = config['stopwords']
    _endings = sorted(config['endings'], key=len, reverse=True)


    def __init__(self, name):
        if not isinstance(name, str):
            name = str(name)
        if not name:
            name = u'Unidentified'
        self.verbatim = name.strip()
        self.name = self.verbatim
        self.host = None
        self.textures = []
        self.colors = []
        self.parts = []
        self.keywords = []
        self.indexed = None
        self.parse()


    def __str__(self):
        return pformat({
            u'verbatim': self.verbatim,
            u'name': self.name,
            u'host': self.host,
            u'textures': self.textures,
            u'colors': self.colors,
            u'parts': self.parts,
            u'keywords': self.keywords,
            u'indexed': self.indexed
        })


    def __repr__(self):
        return str(self)


    def key(self, key=None):
        """Returns a standardized form of the name"""
        if key is None:
            key = self.name
        if not key:
            return u''
        if not isinstance(key, str):
            key = str(key)
        key = key.replace(' ', '-')
        return str(re.sub(r'[^A-Za-z0-9\-]', u'', unidecode(key)).lower())


    def patternize(self, val):
        """Constructs a regex pattern including modifiers"""
        modifiers = '|'.join(self._modifiers)
        pattern = r'\b((({})[ \-]){{0,4}}{})\b'.format(modifiers, val)
        return re.compile(pattern)


    def _parse_textures(self):
        """Parses texturural terms from a rock name"""
        for texture in self._textures:
            pattern = self.patternize(texture)
            matches = pattern.search(self.name)
            if matches is not None:
                self.name = pattern.sub('', self.name)
                self.textures.append(matches.group())
        self.textures.sort()
        return self


    def _parse_colors(self):
        """Parses color terms from a rock name"""
        colors = '|'.join(self._colors)
        val = u'({0})(([ \-]and[ \-]|-)({0}))?'.format(colors)
        pattern = self.patternize(val)
        matches = pattern.search(self.name)
        if matches is not None:
            self.name = pattern.sub('', self.name)
            self.colors.append(matches.group())
        self.colors.sort()
        return self


    def _parse_stopwords(self):
        """Tries to strip stopwords from a rock name"""
        # Check for stopwords
        self.name = self.name.strip()
        for stopword in self._stopwords:
            if self.name.startswith('{} '.format(stopword)):
                #print 'Starts with "{}"'.format(stopword)
                self.name = self.name[len(stopword):].strip()
            if self.name.endswith(' {}'.format(stopword)):
                #print 'Ends with "{}"'.format(stopword)
                self.name = self.name[:-len(stopword)].strip()
            pattern = re.compile(r'\b{}\b'.format(stopword))
            if pattern.search(self.name) is not None:
                msg = u'Stopword found: {}'.format(self.name)
                #print msg
        # Check for host rock
        pattern = re.compile(r'^([a-z]+)-hosted\b')
        matches = pattern.search(self.name)
        if matches is not None:
            self.name = pattern.sub('', self.name)
            self.host = matches.group(1)
        if 'hosted' in self.name:
            msg = u'Stopword found: {}'.format(self.name)
            #print msg
        return self


    def _parse_keywords(self):
        keywords = []
        if [p for p in self.parts if p.stem is None]:
            self.keywords = []
            return self
        for part in self.parts:
            keywords.extend([self.stem(kw) for kw in self.kw_split(part.stem)])
        self.keywords = [kw for kw in keywords if kw]
        return self


    def _clean(self, name):
        while '  ' in self.name:
            self.name = self.name.replace('  ', ' ')
        self.name = self.name.strip()
        if not self.name:
            self.name = u'Unidentified'
        return self.name


    def parse(self):
        """Parses physical descriptors from a rock name"""
        self.name = self.verbatim.lower()
        self._parse_colors()
        self._parse_textures()
        self._parse_stopwords()
        self.segment()
        self._parse_keywords()
        self.name = self._clean(self.name)
        self.indexed = self.name
        if self.keywords and any(self.keywords):
            primary = self.keywords[0]
            associated = self.keywords[1:] if len(self.keywords) > 1 else []
            self.indexed = u'{} {}'.format('-'.join(associated), primary).strip()
        self.index = self.key(self.indexed)


    def segment(self):
        """Splits a name into segments"""
        name = self.key().rstrip(') ')
        if '(var' in name:
            main = name.split('(var')[1].strip(' .)')
            stem = self.stem(main)
            pos = 'noun' if main.rstrip('e') == stem else 'adj'
            return [Part(main, self.stem(main), 0, pos)]
        # FIXME: Handle Mineral-(Y) and Mineral-(AbCDe)
        # Split into parts, checking for hyphenates
        delim = ' ' if ' ' in name else '-'
        try:
            mod, main = name.rsplit(delim, 1)
        except ValueError:
            mod = ''
            main = name
        stem = self.stem(main)
        pos = 'noun' if main.rstrip('e') == stem else 'adj'
        parts = [Part(main, stem, 0, pos)]
        exclude = ['', 'var'] + self._modifiers + self._textures + self._colors
        words = [w for w in re.split('\W', mod) if not self.key(w) in exclude]
        # Filter words ending with -ized, which usually describe alteration
        for i, word in enumerate([w for w in words if not w.endswith('ized')]):
            stem = self.stem(word)
            pos = 'noun' if word == stem else 'adj'
            parts.append(Part(word, stem, i + 1, pos))
        self.parts = parts
        return parts


    def kw_split(self, val):
        prefixes = ['meta']
        for prefix in prefixes:
            if val.startswith(prefix) and val != prefix:
                val = u'{}-{}'.format(prefix, val[len(prefix):])
        return val.split('-')


    def stem(self, val):
        """Stems a value"""
        # Exclude numerics (e.g., Dana groups)
        if val and val[0].isdigit():
            return None
        endings = self._endings[:]
        endings.append('')
        for ending in endings:
            if val.endswith(ending):
                stem = val[:-len(ending)] if ending else val
                if val != stem:# and self.find(stem):
                    return stem
        return val
        #if self.taxa is None or self.find(val):
        #    return val


    def compare_to(self, other):
        """Scores the similarity to another name"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        self_words = [p.word for p in self.parts]
        other_words = [p.word for p in other.parts]
        count = float(len(set(re.split('\W', self.key(self.verbatim)) +
                              re.split('\W', other.key(other.verbatim)))))
        score = len((set(self_words).intersection(other_words))) / count
        #print self.verbatim, 'vs.', other.verbatim, '=>', score
        return score


    def is_similar_to(self, other):
        """Tests whether this name is similar to another name"""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return set(self.keywords) == set(other.keywords)


    def is_same_as(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return self.key(self.verbatim) == self.key(other.verbatim)


    def parents(self, parts=None):
        if parts is None:
            parts = self.parts
        parents = []
        parts = [p.stem for p in parts]
        if None in parts:
            return parents
        total = len(re.split('\W', self.key(self.verbatim)))
        i_max = -1 if  total == len(parts) else None
        for i in range(len(parts[1:i_max])):
            modifiers = '-'.join(parts[1:i + 2])
            parents.append(u'{} {}'.format(modifiers, parts[0]).strip())
        if total > 1:
            parents.append(parts[0])
        parents = [self.key(p) for p in parents]
        parents.sort(key=len, reverse=True)
        return parents


    def parent_key(self, parts=None):
        """Converts a list of parts a key"""
        if parts is None:
            parts = self.segment()
        return '|'.join([u'{}-{}'.format(p.rank, p.stem) for p in parts])
