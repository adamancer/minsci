import json
import os
from collections import namedtuple

from bs4 import BeautifulSoup

from ...helpers import std




AuthorityTaxon = namedtuple('AuthorityTaxon', ['code', 'name', 'parent'])

class Authority(dict):
    """Dict modified with methods to trace lineage"""

    def __init__(self, *args, **kwargs):
        super(AuthorityDict, self).__init__(*args, **kwargs)
        self._species = {std(val[1]): key for key, val in self.iteritems() if val}
        for key, val in self.iteritems():
            self[key] = AuthorityTaxon(*val)


    def __getattr__(self, key):
        if key in ('_species'):
            val ={std(val): key for key, val in self.iteritems()}
            self.__setattr__(key, val)
            return val
        raise AttributeError(key)


    def get_name(self, name):
        return self[self._species[std(name)]]


    def get_parents(self, code):
        # Convert species to code
        if not code[0].isdigit():
            code = self._species[std(code)]
        parents = []
        while '.' in code:
            code = get_webmin_parent(code)
            parents.append(code)
        return parents


    @staticmethod
    def get_webmin_parent(code):
        return get_webmin_parent(code)



def read_webminerals(url):
    """Parses classification tree from WebMinerals"""
    fn = os.path.basename(url).rsplit('.', 1)[0] + '.json'
    fp = os.path.join(os.path.dirname(__file__), '..', 'files', 'taxa', fn)
    try:
        codes = json.load(open(fp, 'rb'))
    except (IOError, OSError):
        print 'Reading classification tree from {}...'.format(url)
        soup = BeautifulSoup(requests.get(url).text, 'html5lib')
        codes = {}
        # Get class codes and names
        for tag in ('h2', 'h3', 'h4'):
            for node in soup(tag):
                try:
                    code, name = re.split('\s+', node.text, 1)
                except ValueError:
                    code = node.text.strip()
                    name = None
                parent = get_webmin_parent(code)
                codes[code] = AuthorityTaxon(code, name.lstrip(' -'), parent)
        # Get species codes and names
        for node in soup('dd'):
            try:
                code = node.text.split(' ')[0]
                name = node.find('a').text
                parent = get_webmin_parent(code)
            except AttributeError:
                pass
            else:
                codes[code] = AuthorityTaxon(code, name, parent)
        # Fill in missing parents
        for autaxon in codes.values():
            # Proceed only if the code has no children
            children = [c for c in codes if c.startswith(autaxon.code)]
            if len(children) > 1:
                try:
                    codes[autaxon.parent]
                except KeyError:
                    print 'Adding {}...'.format(autaxon.parent)
                    code = autaxon.parent
                    name = u''
                    parent = get_webmin_parent(code)
                    codes[code] = AuthorityTaxon(code, name, parent)
        json.dump(codes, open(fp, 'wb'))
    return AuthorityDict(codes)


def read_bgs():
    """Parses BGS classification tree mirrored on Smithsonian site"""
    print 'Reading BGS data...'
    url = 'http://mineralsciences.si.edu/_files/data/bgs.txt'
    fn = os.path.basename(url).rsplit('.', 1)[0] + '.json'
    fp = os.path.join(os.path.dirname(__file__), '..', 'files', 'taxa', fn)
    try:
        codes = json.load(open(fp, 'rb'))
    except (IOError, OSError):
        print 'Reading classification tree from {}...'.format(url)
        f = requests.get(url).iter_lines()
        rows = csv.reader(f)
        keys = next(rows)
        codes = {}
        for row in rows:
            data = dict(zip(keys, [s.decode('utf-8') for s in row]))
            if data:
                code = data['Code']
                name = data['Translation']
                parent = data['Parent Code']
                codes[code] = AuthorityTaxon(code, name, parent)
        json.dump(codes, open(fp, 'wb'))
    return AuthorityDict(codes)


def get_webmin_parent(code):
    if (code[-1].isalpha()
        and code[-2].isdigit()
        and code[-1] == code[-1].lower()):
            return code[:-1]
    return code.rsplit('.', 1)[0]


def select_best_taxon(*recs):
    """Selects the preferred record from a list of duplicates"""
    recs = list(recs)
    recs.sort(key=lambda rec: int(rec('irn')))
    cited = [rec for rec in recs if rec('CitSpecimenRef_nesttab')]
    official = [rec for rec in recs if rec.is_official()]
    defined = [rec for rec in recs if rec.is_defined()]
    accepted = [rec for rec in recs if rec.is_accepted()]
    if (cited and official and cited != official
        or cited and defined and cited != defined):
        irns = [rec('irn') for rec in recs]
        raise ValueError('Could not determine best: {}'.format(irns))
    for param in (cited, official, defined, accepted):
        if param:
            return param[0]
    # If all else fails, select the lowest irn
    return recs[0]
