"""Defines methods to map administrative divisions to synonyms or codes"""

import logging
logger = logging.getLogger(__name__)

import json
import os
import re
import time
from collections import namedtuple

from unidecode import unidecode
from requests.structures import CaseInsensitiveDict

from .helpers import FILES
from ....standardizer import LocStandardizer


AdminDiv = namedtuple('AdminDiv', ['name', 'code', 'level'])

STD_READ = LocStandardizer(minlen=1, sort_terms=False)
STD_WRITE = LocStandardizer(minlen=1, sort_terms=False)


def _read_countries():
    """Reads ISO country codes from file

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    code_to_name = CaseInsensitiveDict()
    name_to_code = CaseInsensitiveDict()
    with open(os.path.join(FILES, 'countries.txt'), 'r', encoding='utf-8') as f:
        for line in f:
            row = line.split('\t')
            country = row[4]
            code = row[0]
            if code and country:
                code_to_name[code] = country
                name_to_code[STD_READ(country)] = code
    return code_to_name, name_to_code


def _read_states():
    """Reads U.S. state abbreviations from file

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(FILES, 'states.txt'), 'r', encoding='utf-8') as f:
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
    # Standardize keys
    if standardize:
        orig = os.path.join(FILES, 'admin_codes.json')
        admin_codes = json.load(open(orig, 'r', encoding='utf-8'))
        print('Standardizing keys...')
        for country, levels in admin_codes.items():
            print('Processing {}...'.format(country))
            for level, names in levels.items():
                for key, code in list(names.items()):
                    if STD_READ(key) != key:
                        names[STD_READ(key)] = code
                        del names[key]
        json.dump(admin_codes,
                  open(fp, 'w', encoding='utf-8'),
                  indent=2,
                  sort_keys=True,
                  ensure_ascii=False)
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
    except json.decoder.JSONDecodeError as e:
        input(str(e))
        raise
    except IOError:
        current = {}
    if current:
        _verify_current(current)
    print('Loaded current!')
    return current


def _save_current(current):
    """Updates the current names lookup"""
    fp = os.path.join(FILES, 'current.json')
    _remove_empty_keys(current, n=2)
    while True:
        try:
            json.dump(current,
                      open(fp, 'w', encoding='utf-8'),
                      indent=2,
                      sort_keys=True,
                      ensure_ascii=False)
        except OSError as e:
            print('Could not save {}. Retrying in 2 seconds...'.format(fp))
            time.sleep(2)
        else:
            break


def _verify_current(current):
    """Verifies that the names in current resolve in GeoNames"""
    parser = AdminParser()
    errors = []
    for key, vals in current['countries'].items():
        if not isinstance(vals, list):
            vals = [vals]
        for val in vals:
            try:
                parser.get_country_code(val)
            except Exception as e:
                errors.append(str(e))
    for name, country in current['states'].items():
        name = name.replace('-', ' ')
        for key, vals in country.items():
            if vals and not isinstance(vals, dict):
                if not isinstance(vals, list):
                    vals = [vals]
                for val in vals:
                    try:
                        parser.get_admin_div(val, 'ADM1', name)
                    except Exception as e:
                        errors.append(str(e))
    for name, country in current['counties'].items():
        name = name.replace('-', ' ')
        for key, state in country.items():
            for key, vals in state.items():
                if vals and not isinstance(vals, dict):
                    if not isinstance(vals, list):
                        vals = [vals]
                    for val in vals:
                        try:
                            parser.get_admin_div(val, 'ADM2', name)
                        except Exception as e:
                            errors.append(str(e))
    if errors:
        print('The following values in current.json do not resolve:')
        input('\n'.join(errors))


def _remove_empty_keys(dct, n=1, remove_blank=False):
    for i in range(n):
        for key in list(dct.keys()):
            if key.endswith('-ca') or key in ['not-stated', 'undetermined']:
                del dct[key]
            elif isinstance(dct[key], dict):
                if not dct[key]:
                    del dct[key]
                else:
                    _remove_empty_keys(dct[key])
            elif remove_blank and not dct[key]:
                del dct[key]
    return dct




class AdminParser(object):
    """Defines methods for determining administrative divisions and codes"""
    _admin_divs = None
    _current = None
    _to_country_name = _read_countries()[0]
    _to_country_code = _read_countries()[1]
    _to_state_name = _read_states()[0]
    _to_state_abbr = _read_states()[1]
    _hints = {}


    def get_country(self, country_code):
        """Gets the name of the country corresponding to a country code"""
        return self._to_country_name[country_code]


    def get_country_code(self, country):
        """Gets the ISO country code corresponding to a country name"""
        return self._to_country_code[STD_READ(country)]


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
        if isinstance(term, list):
            return [self.get_admin_div(t, level, country, search_name, suffixes)
                    for t in term]
        term_ = STD_READ(term)
        # Check hints
        i = '1' if search_name else '0'
        key = '|'.join([term, level, country, i, suffixes])
        try:
            return self._hints[key]
        except KeyError:
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
            has_digit = any([c.isdigit() for c in val])
            is_shorter = len(val) < len(term)
            if has_digit or is_shorter or search_name:
                try:
                    name = self._admin_divs[country_code][level][STD_READ(val)]
                except KeyError:
                    level = level.rstrip(suffixes)
                    raise ValueError('Unknown {}:'
                                     ' {}, {}'.format(level, val, country))
                div = AdminDiv(name, val, level)
            else:
                div = AdminDiv(val, term, level)
            #self._hints[key] = div
            return div


    def get_admin_name(self, *args, **kwargs):
        """Gets the name of the given administrative division"""
        kwargs['search_name'] = True
        div = self.get_admin_div(*args, **kwargs)
        try:
            return div.code
        except AttributeError:
            return [d.code for d in div]


    def get_admin_code(self, *args, **kwargs):
        """Gets the code for the given administrative division"""
        kwargs['search_name'] = False
        div = self.get_admin_div(*args, **kwargs)
        try:
            return div.code
        except AttributeError:
            return [d.code for d in div]


    def map_archaic(self, val, keys, callback, *args, **kwargs):
        """Maps archaic names to their current equivalents"""
        if not val:
            raise ValueError('map_archaic() requires val')
        # Handles lists of values
        if isinstance(val, list):
            currents = []
            codes = []
            for val in val:
                current, code = self.map_archaic(val, keys, callback,
                                                 *args, **kwargs)
                currents.append(current)
                codes.append(code)
            return currents, codes
        # Convert args to string for error
        ergs = list(args) + ['{}={}'.format(k, v) for k, v in kwargs.items()]
        # Load the current names reference the first time it's needed
        if self._current is None:
            self.__class__._current = _read_current()
        # Get the lookup for the current term
        lookup = self._current
        for key in keys:
            key = STD_READ(key)
            try:
                lookup = lookup[key]
            except KeyError:
                lookup[key] = {}
                lookup = lookup[key]
            except TypeError:
                raise ValueError('Multiple values given')
        # Map archaic to current terms
        try:
            current = lookup.get(STD_READ(val), val)
            code = None
            if current and not isinstance(current, dict):
                code = callback(current, *args, **kwargs)
                logger.debug('Mapped "{}" to {}'.format(val, code))
        except ValueError:
            try:
                lookup[STD_READ.strip_word(STD_READ(val), 'ca')]
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
                elif '-' in val or ' and ' in val:
                    # Handle multiple values in an admin div field
                    vals = re.split(r'(?:\band\b|\bor\b|-)', val)
                    vals = [val.strip('- ') for val in vals]
                    return self.map_archaic(vals, keys, callback,
                                            *args, **kwargs)
                lookup[STD_WRITE(val)] = current
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
            return current, code
