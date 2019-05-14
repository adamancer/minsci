"""Defines methods to map administrative divisions to synonyms or codes"""

import logging
logger = logging.getLogger(__name__)

import json
import os
from collections import namedtuple

from unidecode import unidecode
from requests.structures import CaseInsensitiveDict

from .helpers import FILES
from ....standardizer import LocStandardizer


AdminDiv = namedtuple('AdminDiv', ['name', 'code', 'level'])


def _read_countries():
    """Reads ISO country codes from file

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    code_to_name = CaseInsensitiveDict()
    name_to_code = CaseInsensitiveDict()
    with open(os.path.join(FILES, 'countries.txt'), 'r') as f:
        for line in f:
            row = line.split('\t')
            country = unidecode(row[4])
            code = row[0]
            if code and country:
                code_to_name[code] = country
                name_to_code[country] = code
    return code_to_name, name_to_code


def _read_states():
    """Reads U.S. state abbreviations from file

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(FILES, 'states.txt'), 'r') as f:
        for line in f:
            row = line.split('\t')
            state = row[0]
            abbr = row[3]
            abbr_to_name[abbr] = state
            name_to_abbr[state] = abbr
    return abbr_to_name, name_to_abbr


def _read_admin_divs(standardize=False):
    """Reads and if necessary formats the list of admin codes"""
    print('Loading admin codes...')
    fp = os.path.join(FILES, 'admin_codes_std.json')
    std = LocStandardizer()
    # Standardize keys
    if standardize:
        orig = os.path.join(FILES, 'admin_codes.json')
        admin_codes = json.load(open(orig, 'r', encoding='utf-8'))
        print('Standardizing keys...')
        for country, levels in admin_codes.items():
            print('Processing {}...'.format(country))
            for level, names in levels.items():
                for key, code in list(names.items()):
                    if std(key) != key:
                        names[std(key)] = code
                        del names[key]
        json.dump(admin_codes,
                  open(fp, 'w', encoding='utf-8'),
                  indent=2,
                  sort_keys=True)
    else:
        admin_codes = json.load(open(fp, 'r', encoding='utf-8'))
    print('Loaded codes!')
    return admin_codes


def _read_current():
    """Reads and if necessary formats the admin div lookup"""
    print('Loading current...')
    fp = os.path.join(FILES, 'current.json')
    try:
        current = json.load(open(fp, 'r', encoding='utf-8'))
    except IOError:
        current = {}
    print('Loaded current!')
    return current


def _save_current(current):
    """Updates the current names lookup"""
    fp = os.path.join(FILES, 'current.json')
    json.dump(current,
              open(fp, 'w', encoding='utf-8'),
              indent=2,
              sort_keys=True)




class AdminParser(object):
    """Defines methods for determining administrative divisions and codes"""
    _std = LocStandardizer()
    _admin_divs = None
    _current = None
    _to_country_name = _read_countries()[0]
    _to_country_code = _read_countries()[1]
    _to_state_name = _read_states()[0]
    _to_state_abbr = _read_states()[1]


    def get_country(self, country_code):
        """Gets the name of the country corresponding to a country code"""
        return self._to_country_name[country_code]


    def get_country_code(self, country):
        """Gets the ISO country code corresponding to a country name"""
        return self._to_country_code[unidecode(country)]


    def get_us_state_abbr(self, state):
        """Gets the abbreviation of a U.S. state"""
        return self._to_state_abbr[state]


    def get_us_state_name(self, abbr):
        """Gets the name of a U.S. state for an abbreviation"""
        return self._to_state_name[abbr]


    def get_admin_div(self, term, level, country,
                      search_name=None, suffixes='HD'):
        """Gets the name and code of the given administrative division"""
        # Load the admin codes reference the first time it's needed
        if self._admin_divs is None:
            try:
                self.__class__._admin_divs = _read_admin_divs()
            except IOError:
                self.__class__._admin_divs = _read_admin_divs(standardize=True)
        term_ = self._std(term)
        try:
            country_code = self.get_country_code(country)
        except IndexError as e:
            logger.error('Unrecognized country', exc_info=True)
            raise
        try:
            val = self._admin_divs[country_code][level][term_]
        except KeyError:
            for level in [level + s for s in suffixes]:
                try:
                    val = self._admin_divs[country_code][level][term_]
                except KeyError:
                    pass
                else:
                    break
            else:
                level = level.rstrip(suffixes)
                raise ValueError('Unknown {}:'
                                 ' {}, {}'.format(level, term, country))
        # If searching a name, look up the official name as well
        if len(val) < len(term) or val.isnumeric() or search_name:
            try:
                name = self._admin_divs[country_code][level][self._std(val)]
            except KeyError:
                level = level.rstrip(suffixes)
                raise ValueError('Unknown {}:'
                                 ' {}, {}'.format(level, val, country))
            return AdminDiv(name, val, level)
        return AdminDiv(val, term, level)


    def get_admin_name(self, *args, **kwargs):
        """Gets the name of the given administrative division"""
        kwargs['search_name'] = True
        return self.get_admin_div(*args, **kwargs)


    def get_admin_code(self, *args, **kwargs):
        """Gets the code for the given administrative division"""
        kwargs['search_name'] = False
        return self.get_admin_div(*args, **kwargs)


    def map_archaic(self, val, keys, callback, *args, **kwargs):
        """Maps archaic names to their current equivalents"""
        if not val:
            raise ValueError('map_archaic() requires val')
        # Convert args to string for error
        ergs = list(args) + ['{}={}'.format(k, v) for k, v in kwargs.items()]
        # Load the current names reference the first time it's needed
        if self._current is None:
            self.__class__._current = _read_current()
        # Get the lookup for the current term
        lookup = self._current
        for key in keys:
            key = self._std(key)
            try:
                lookup = lookup[key]
            except KeyError:
                lookup[key] = {}
                lookup = lookup[key]
        # Map archaic to current terms
        try:
            current = lookup.get(self._std(val), val)
            code = callback(current, *args, **kwargs) if current else None
        except ValueError:
            try:
                lookup[self._std.strip_word(self._std(val), 'ca')]
            except KeyError:
                if val.endswith('Ca.'):
                    current = val[:-3].rstrip()
                else:
                    current = ''
                    #loc = '{}, {}'.format(val, ', '.join(keys[1:])).rstrip(', ')
                    #current = input('Map {}: '.format(loc))
                # Verify that current value is valid if not empty
                if current:
                    try:
                        code = callback(current, *args, **kwargs)
                    except ValueError as e:
                        logger.error(str(e), exc_info=True)
                        raise ValueError('Unknown #1 {}: {}'.format(ergs, val))
                lookup[self._std(val)] = current
                _save_current(self._current)
                if not current:
                    raise ValueError('Unknown #2 {}: {}'.format(ergs, val))
                logger.debug('Mapped "{}" to {}'.format(val, code))
                return current, code
            else:
                raise ValueError('Unknown #3 {}: {}'.format(ergs, val))
        else:
            if not current:
                raise ValueError('Unknown #4 {}: {}'.format(ergs, val))
            logger.debug('Mapped "{}" to {}'.format(val, code))
            return current, code
