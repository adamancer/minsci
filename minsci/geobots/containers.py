"""Containers with methods to store and analyze geographical data"""

import os
from copy import deepcopy
from pprint import pprint

from unidecode import unidecode


DIRPATH = os.path.join(os.path.dirname(__file__), 'files')

# Maps state names to abbreviations
ABBR_TO_NAME, NAME_TO_ABBR = _read_abbreviations('abbreviations.txt')
TERMS = ('county', 'co', 'department', 'dept', 'province', 'prov')


class GeoList(list):
    """Container with methods to filter locations"""

    def __init__(self, *args, **kwargs):
        self._params = deepcopy(kwargs)
        self.country = kwargs.pop('country')
        self.state = kwargs.pop('state')
        self.county = kwargs.pop('county')
        super(GeoList, self).__init__(*args, **kwargs)


    def filter_matches(self, country=None, state=None, county=None):
        """Identifies good matches based on political geography

        Args:
            result (dict): a GeoNames result set
            country (str): country containing the locality
            state (str): state or equivalent containing the locality
            country (str): county of equivalent containing the locality

        Returns:
            List of best-scored matches
        """
        scored = []
        for match in self:
            score = 0
            score += score_match(match.get(self.country), country)
            score += score_match(match.get(self.state), state)
            score += score_match(match.get(self.county), county)
            if score >= 0:
                scored.append([match, score])
        # Get the best matches based on score
        if scored:
            high_score = max([score for match, score in scored])
            scored = [match for match, score in scored if score == high_score]
        # Assign matches
        self = self.__class__(scored, **self._params)
        return self


    def pprint(self):
        """Pretty prints the contents of the list"""
        pprint(self)



def score_match(loc, ref_loc):
    """Score the similarity of two place names

    Args:
        loc (str): a locality name
        ref_loc (str): a locality name to match against s1

    Returns:
        Score corresponding to quality of match
    """
    # Do not score if either value is missing
    if not all((loc, ref_loc)):
        return 0
    # Format strings
    s1, s2 = [format_string(s) for s in (loc, ref_loc)]
    # Compare for identical values
    if s1 == s2 or ABBR_TO_NAME.get(s1, s1) == ABBR_TO_NAME.get(s2, s2):
        return 2
    # Strip endings for each string and compare
    for term in TERMS:
        n = len(term)
        if s1.startswith(term):
            s1 = s1[n:].strip()
        if s1.endswith(term):
            s1 = s1[:-n].strip()
        if s2.startswith(term):
            s2 = s2[n:].strip()
        if s2.endswith(term):
            s2 = s2[:-n].strip()
    if s1 and s2 and s1 == s2:
        return 1
    # No match could be made. The penalty here should be much larger than
    # the value returned for a good match because we want to exclude any
    # explicit mismatches.
    return -10


def format_string(s):
    """Standardizes the format of a string to improve comparisons

    Args:
        s (str): a string or string-like object to be formatted

    Returns:
        Formatted string
    """
    return unidecode(s).lower().strip('.')


def _read_abbreviations(fn):
    """Reads U.S. state abbreviations from file

    Args:
        fn (str): name of file containing abbreviations

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = {}
    name_to_abbr = {}
    with open(os.path.join(DIRPATH, fn), 'rb') as f:
        for line in f:
            row = line.split('\t')
            state = row[0]
            abbr = row[3]
            abbr_to_name[abbr] = state
            name_to_abbr[state] = abbr
    return abbr_to_name, name_to_abbr
