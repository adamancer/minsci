"""Containers with methods to store and analyze geographical data"""

import os
import re
from collections import namedtuple
from pprint import pprint

from requests.structures import CaseInsensitiveDict
from unidecode import unidecode


DIRPATH = os.path.join(os.path.dirname(__file__), 'files')

# Maps state names to abbreviations
ENDINGS = {
    'admin': ['county', 'co', 'department', 'dept', 'departamento-de',
              'district', 'dist', 'municipio-de', 'oblast',
              'prefecture', 'pref', 'province', 'provincia-de',
              'prov', 'region', 'terr', 'territory'],
    'islands': ['atoll', 'atolls', 'ile', 'iles', 'island', 'islands',
                'isle', 'isles', 'islet', 'islets'],
    'mine': ['claim', 'claims', 'deposit', 'deposits', 'mine', 'mines',
             'occurrence', 'pit', 'pits', 'prospect', 'prospects', 'quarry',
             'quarries']
}


Site = namedtuple('Site', ['id', 'source', 'names', 'kind', 'code'])


class GeoList(list):
    """Container with methods to filter locations based on country, etc."""

    def __init__(self, *args, **kwargs):
        self._map_params = deepcopy(kwargs)
        self.country = kwargs.pop('country')
        self.state = kwargs.pop('state')
        self.county = kwargs.pop('county')
        self.matched_on = []
        # Coerce first argument to list
        if not isinstance(args[0], list):
            args = list(args)
            args[0] = [args[0]]
        super(GeoList, self).__init__(*args, **kwargs)


    def filter_matches(self, countries=None, state=None, county=None):
        """Identifies good matches based on political geography

        Args:
            result (dict): a GeoNames result set
            country (mixed): country containing the locality
            state (str): state or equivalent containing the locality
            country (str): county of equivalent containing the locality

        Returns:
            List of best-scored matches
        """
        scored = []
        for match in self:
            scores = {}
            # Country can have multiple values. Keep the first match.
            if isinstance(countries, basestring):
                countries = countries.split('|')
            scores['country'] = 0
            for country in countries if countries is not None else []:
                score = score_match(match.get(self.country), country, 'admin')
                #print match.get(self.country), country, scr
                scores['country'] = score
                if score > 0:
                    break
            scores['state'] = score_match(match.get(self.state), state, 'admin')
            scores['county'] = score_match(match.get(self.county), county, 'admin')
            score = sum(scores.values())
            if score >= 0:
                scored.append([match, score, scores])
        # Get the best matches based on score
        matched_on = []
        if scored:
            high_score = max([score for match, score, scores in scored])
            scored = [m for m in scored if m[1] == high_score]
            matched_on = [k for k, v in scored[0][2].iteritems() if v]
        # Assign matches
        matches = self.__class__([m[0] for m in scored], **self._map_params)
        matches.matched_on = matched_on
        return matches


    def match_name(self, name, kind):
        """Return matches on a name"""
        matches = [m for m in self if self._match_name(name, m, kind)]
        matches = self.__class__(matches, **self._map_params)
        matches.matched_on = self.matched_on
        return matches


    def get_site_data(self):
        """Return site/station data"""
        return [Site(m['geonameId'], 'GeoNames', self.get_names(m),
                     m.get('fcodeName'), m.get('fcode')) for m in self]


    def pprint(self, pause=False):
        """Pretty prints the contents of the list"""
        pprint(self)
        if pause:
            raw_input('Paused. Press any key to continue.')


    def _match_name(self, name, geoname, kind=None):
        """Checks if the given name matches a geoname

        Args:
            name (str): the name of a place
            geoname (str): the name of a place
            kind (None): the type of place

        Returns:
            Boolean indicating if the name is a match
        """
        scored = [score_match(name, nm, kind) for nm in self.get_names(geoname)]
        return bool([s for s in scored if s > 0])


    @staticmethod
    def get_names(match, include_alts=True):
        """Returns variants on a given geoname

        Note that the complete list of synonyms is only retured if the
        GeoNames ID is queried directly.
        """
        names = [match.get('name'),
                 match.get('asciiName'),
                 match.get('toponymName')]
        if include_alts:
            names.extend([alt['name'] for alt
                          in match.get('alternativeNames', {})])
        return sorted(list(set(names)))


def normalize_name(name, kind, for_query=False):
    """Normalizes the format of a name to improve matching"""
    name = format_name(name).strip('-')
    # Normalize common terms in name
    normalize = {
        r'st': 'saint',
        r'ste': 'sainte',
        r'mt': 'mount',
        r'monte': 'mount',
        r'mtn': 'mountain',
        r'mtns': 'mountains',
    }
    for search, repl in normalize.iteritems():
        pattern = re.compile(r'\b(' + search + r')\b')
        name = pattern.sub(repl, name)
    # Strip field-specific endings
    terms = ['ca', 'nr', 'near'] + ENDINGS.get(kind, [])
    if for_query:
        landforms = ['mount', 'mountain', 'region', 'valley']
        landforms.extend([s + 's' for s in landforms])
        terms.extend(landforms)
    terms.extend(['de', 'des', 'du', 'of', 'la', 'le', 'les'])
    for term in terms:
        if re.compile(r'^{0}\b|\b{0}$'.format(term), re.I).search(name):
            if name.startswith(term):
                name = name[len(term):].strip(' -')
            if name.endswith(term):
                name = name[:-len(term)].strip(' -')
    return name


def score_match(name, ref_name, kind=None):
    """Score the similarity of two place names

    Args:
        name (str): a locality name
        ref_name (str): a locality name to compare with name

    Returns:
        Score corresponding to quality of match
    """
    # Do not score if either value is missing
    if not all((name, ref_name)):
        return 0
    #print 'Scoring match...'
    # Format strings
    name, ref_name = [format_name(s) for s in (name, ref_name)]
    #print u' Standardized: {} => {}'.format(name, ref_name)
    if name == ref_name:
        return 3
    # Compare abbreviations for high-level admin divisions
    if kind == 'admin':
        abbr_name = ABBR_TO_NAME.get(name, name)
        abbr_ref_name = ABBR_TO_NAME.get(ref_name, ref_name)
        if abbr_name == abbr_ref_name:
            return 3
    # Strip endings for each string and compare
    name = normalize_name(name, kind)
    ref_name = normalize_name(ref_name, kind)
    #print u' Normalized:   {} => {}'.format(name, ref_name)
    if name and ref_name and name == ref_name:
        return 2
    # Compare sets
    name = set(re.split(r'\W', name))
    ref_name = set(re.split(r'\W', ref_name))
    #print u' Sets:         {} => {}'.format(name, ref_name)
    if name and ref_name and name == ref_name:
        return 1
    # No match could be made. The penalty here should be much larger than
    # the value returned for a good match because we want to exclude any
    # explicit mismatches.
    return -100


def format_name(val):
    """Standardizes the format of a string to improve comparisons

    Args:
        val (str): a string or string-like object to be formatted

    Returns:
        Formatted string
    """
    formatted = re.sub(ur'[\W]+', u'-', unidecode(val)).lower().strip('.-')
    return formatted.decode('ascii')


def _read_countries(fn):
    """Reads ISO country codes from file

    Args:
        fn (str): name of file containing abbreviations

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(DIRPATH, fn), 'rb') as f:
        for line in f:
            row = line.split('\t')
            country = row[4]
            code = row[0]
            if code and country:
                abbr_to_name[code] = country
                name_to_abbr[country] = code
    return abbr_to_name, name_to_abbr


def _read_states(fn):
    """Reads U.S. state abbreviations from file

    Args:
        fn (str): name of file containing abbreviations

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(DIRPATH, fn), 'rb') as f:
        for line in f:
            row = line.split('\t')
            state = row[0]
            abbr = row[3]
            abbr_to_name[abbr] = state
            name_to_abbr[state] = abbr
    return abbr_to_name, name_to_abbr


ABBR_TO_NAME, NAME_TO_ABBR = _read_states('states.txt')
FROM_COUNTRY_CODE, TO_COUNTRY_CODE = _read_countries('countries.txt')
