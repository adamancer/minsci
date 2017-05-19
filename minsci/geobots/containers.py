"""Containers with methods to store/filter data about geographical features"""

import os
import re
from collections import namedtuple
from copy import deepcopy
from pprint import pprint

from requests.structures import CaseInsensitiveDict
from unidecode import unidecode


DIRPATH = os.path.join(os.path.dirname(__file__), 'files')

# Lists of general terms to trim from place names to improve the odds of
# finding a match. Each list is tailored to a type of place; additional
# places and terms can be added as needed.
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
    """List of GeoNames features with various filtering methods

    Each item in the list is a GeoNames JSON object as a dict.
    """

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
        """Filters matches based on country, state, and county

        Args:
            countries (mixed): the name of a country or countries
            state (str): the name of a state or province
            county (str): the name of a country or district

        Returns:
            A GeoList object containing the highest-scoring localities
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
        """Returns features matching the given name

        Args:
            name (str): the name of the feature to match
            kind (str): the type of feature. Used to trim general terms from
                feature names to improve matching.

        Returns:
            A GeoList object containing the features matching the given name
        """
        matches = [m for m in self if self._match_name(name, m, kind)]
        matches = self.__class__(matches, **self._map_params)
        matches.matched_on = self.matched_on
        return matches


    def get_site_data(self):
        """Returns a summary of site data for each site in this list"""
        return [Site(m['geonameId'], 'GeoNames', self.get_names(m),
                     m.get('fcodeName'), m.get('fcode')) for m in self]


    def pprint(self, pause=False):
        """Pretty prints the contents of the list

        Args:
            pause (bool): specifies whether to pause script after printing
        """
        pprint(self)
        if pause:
            raw_input('Paused. Press any key to continue.')


    def _match_name(self, name, feature, kind=None):
        """Checks if a feature name matches the given GeoNames feature

        Args:
            name (str): the name of a place
            feature (dict): a GeoName JSON object as a dict
            kind (str): the type of feature. Used to trim general terms from
                feature names to improve matching.

        Returns:
            Boolean indicating if the name is a match
        """
        scored = [score_match(name, nm, kind) for nm in self.get_names(feature)]
        return bool([s for s in scored if s > 0])


    @staticmethod
    def get_names(feature, include_alts=True):
        """Returns variants on the name of a give feature

        The complete list of alternative names is only returned if the
        GeoNames ID is queried directly; other requests return only a subset
        of all possible names.

        Args:
            feature (dict): the GeoName JSON object as a dict
            include_alts (bool): specifies whether to include alternative
                names (synonyms, other languages, etc.)

        Returns:
            List of the various names for this feature
        """
        names = [feature.get('name'),
                 feature.get('asciiName'),
                 feature.get('toponymName')]
        if include_alts:
            names.extend([alt['name'] for alt
                          in feature.get('alternativeNames', {})])
        return sorted(list(set(names)))


def normalize_name(name, kind, for_query=False):
    """Normalizes the format of a name to improve matching

    Args:
        name (str): the name of the feature
        kind (str): the type of feature. Used to trim general terms from
            feature names to improve matching.
        for_query (bool): specifies whether the name is being normalized to
            create a query for the GeoNames webservice (as opposed to filtering
            a set of matches).

    Returns:
        String with the normalized name
    """
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
        name (str): a feature name
        ref_name (str): a feature name to compare against name
        kind (str): the type of feature. Used to trim general terms from
            feature names to improve matching.

    Returns:
        Score corresponding to quality of match
    """
    # Check that kind is valid
    if kind is not None and ENDINGS.get(kind) is None:
        kinds = sorted(ENDINGS.keys())
        raise AssertionError('kind must be one of {}'.format(kinds))
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
        val (str): the string to be formatted

    Returns:
        Formatted string
    """
    formatted = re.sub(ur'[\W]+', u'-', unidecode(val)).lower().strip('.-')
    return formatted.decode('ascii')


def _read_countries(fn):
    """Reads ISO country codes from file

    Args:
        fn (str): name of the file containing the country abbreviations

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
        fn (str): the name of the file containing U. S. state abbreviations

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
