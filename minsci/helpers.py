# -*- coding: utf-8 -*-
"""Helper functions used throughout the minsci module"""

import os
import re
import string
import sys
from copy import copy, deepcopy
from itertools import izip_longest
from pprint import pprint
from textwrap import fill

import inflect
import pyodbc
from nameparser import HumanName
from unidecode import unidecode


CATKEYS = (
    'FullNumber',
    'MetPrefix',
    'CatMuseumAcronym',
    'CatPrefix',
    'CatNumber',
    'CatSuffix'
    )


def base2int(i, base):
    """Converts integer in specified base to base 10"""
    return int(i, base)


def int2base(i, base):
    """Converts base 10 integer to specified base"""
    digs = string.digits + string.letters
    if i < 0:
        sign = -1
    elif i == 0:
        return '0'
    else:
        sign = 1
    i *= sign
    digits = []
    while i:
        digits.append(digs[x % base])
        i /= base
    if sign < 0:
        digits.append('-')
    digits.reverse()
    return ''.join(digits).upper()


def init_odbc(fn):
    """Opens ODBC connection based on database type

    Args:
        fn (string): filename (or path)

    Returns:
        pyodbc.Connection object
    """
    # Use file extenstion to find the appropriate driver
    drivers = [
        '{Microsoft Access Driver (*.mdb, *.accdb)}',
        '{Microsoft Excel Driver (*.xls, *.xlsx, *.xlsm, *.xlsb)}'
    ]
    ext = '*' + os.path.splitext(fn)[1].lower()
    for driver in drivers:
        if ext in driver:
            break
    else:
        raise Exception('No suitable driver found for {}'.format(ext))
    # Excel does not support transactions, so set autocommit for that driver
    autocommit = False
    if driver.startswith('{Microsoft Excel'):
        autocommit = True
    # ODBC connection string requires a full path
    fp = os.path.abspath(fn)
    dsn = 'DRIVER={};DBQ={};CHARSET=LATIN-1'.format(driver, fp)
    return pyodbc.connect(dsn, autocommit=autocommit)


def dict_from_odbc(cursor, tbl, row_id=None, cols=None, where=None,
                   encoding='cp1252'):
    """Creates a
    Args:
        cursor (pyodbc.Cursor)
        tbl (str): name of table to query. For Excel, table name must be
            formatted as [tbl$].
        row_id (list): name of field(s) to use as key for dictionary
        col (list): list of columns to return. If None, will return all.
        where (str): formatted where clause
        encoding (str): encoding of source file

    Returns:
        Dictionary keyed to row_id
    """
    for arg in [row_id, cols]:
        if arg is not None and not isinstance(arg, list):
            raise Exception('Bad argument')
    # Get list of columns
    if cols is None:
        cols = [row.column_name for row in cursor.columns(tbl.strip('[]'))]
    else:
        cols = [s.strip('`') for s in cols]
    # Prepare where clause
    if where is None:
        where = u''
    else:
        where = u' WHERE {}'.format(where.replace('"', "'"))
    # Assemble query
    query = u'SELECT {} FROM {}{}'.format(','.join(cols), tbl, where)
    # Execute query
    try:
        cursor.execute(query)
    except KeyError:
        raise Exception('Cound not execute query "{}"'.format(query))
    records = {}
    result = cursor.fetchmany()
    error = u''
    records_in_source = 0  # count of records to compare to length of dict
    while result:
        for row in result:
            for fld in row.cursor_description:
                if not bool(error) and fld[1] != str and tbl.endswith('$]'):
                    error = fill('Warning: Non-string data type '
                                 'found. Convert the input sheet '
                                 'to text to prevent data loss.')
            row = [s if bool(s) else '' for s in row]
            row = [s.decode(encoding) if isinstance(s, str) else s for s in row]
            rec = dict(izip_longest(cols, row))
            if row_id is not None:
                key = '-'.join([u'{}'.format(rec[key]) for key in row_id])
            else:
                key = len(records)
            try:
                records[key]
            except KeyError:
                records[key] = rec
            else:
                pass#cprint('Warning: Multiple rows have key "{}"'.format(key))
            records_in_source += 1
        result = cursor.fetchmany()
    if error:
        print error
    if len(records) < records_in_source:
        cprint('Warning: Duplicate keys. Some data not included in dict.')
    return records


def sort_by_reference(lst, order):
    """Reorder list to match order of another list"""
    return sorted(sorted(lst), key=lambda x: _sorter(x, order))


def _sorter(key, order):
    """Returns index in order that starts with key.

    Returns -1 if key not found.
    """
    try:
        return [x for x in xrange(0, len(order))
                if key.startswith(order[x])][0]
    except KeyError:
        print 'Ordering error: {} does not exist in order list'.format(key)
        return -1


def oxford_comma(lst, lowercase=False):
    """Formats list as comma-delimited string

    Args:
        lst (list): list of strings
        lowercase (bool): if true, convert the first letter in each value
            in the list to lowercase

    Returns:
        Comma-delimited string
    """
    lst = copy(lst)
    if lowercase:
        lst = [s[0].lower() + s[1:] for s in lst]
    if len(lst) <= 1:
        return ''.join(lst)
    elif len(lst) == 2:
        return ' and '.join(lst)
    else:
        last = lst.pop()
        return ', '.join(lst) + ', and ' + last


def singular(val):
    """Converts string to singular

    Args:
        s (str): a string

    Returns:
        The singular form of the original string
    """
    inflected = inflect.engine().singular_noun(val)
    if inflected:
        return inflected
    return val




def plural(val):
    """Converts string to plural

    Args:
        s (str): a string

    Returns:
        The plural form of the original string
    """
    return inflect.engine().plural(singular(val))




def dedupe(lst, lower=True):
    """Dedupes a list while maintaining order and case

    Args:
        list (list): a list of strings

    Returns:
        Deduplicated copy of the original list
    """
    if lower:
        lst = [val.lower() for val in lst]
    return [val for i, val in enumerate(lst) if not val in lst[:i]]




def parse_names(name_string, last_name_first=False):
    """Parses name strings into components using nameparser"""
    # Normalize periods
    name_string = name_string\
                  .replace('. ', '.')\
                  .replace('.', '. ')\
                  .replace(' & ', ' and ')
    # Problem titles
    problem_words = ['Count', 'Countess']
    # Suffixes
    suffixes = ['Jr', 'Sr', 'II', 'III', 'IV', 'Esq']
    #suffixes = '|'.join([r'\s' + suf for suf in suffixes])
    # Split names on semicolon, ampersand, or and
    pattern = re.compile(' and |&|;', re.I)
    names = [s.strip() for s in pattern.split(name_string) if bool(s)]
    for name in copy(names):
        if len(name.split(' ')) == 1:
            names = [name_string]
            break
    # Reorder names if needed
    if last_name_first:
        names = [' '.join(name.rsplit(',', 1)[::-1])
                 if ',' in name
                 and not name.rsplit(',', 1)[1].strip() in suffixes
                 else name for name in names]
    # Parse names using nameparser
    results = []
    for unparsed in names:
        # Handle words that nameparser bobbles
        overwrite = {}
        for word in sorted(problem_words, key=len)[::-1]:
            if unparsed.startswith(word):
                unparsed = unparsed.split(word)[1].strip()
                overwrite['NamTitle'] = word
                break
        name = HumanName(unparsed)
        d = {
            'NamPartyType' : 'Person',
            'NamTitle' : name.title,
            'NamFirst' : name.first,
            'NamMiddle' : name.middle,
            'NamLast' : name.last,
            'NamSuffix' : name.suffix
            }
        for key in overwrite:
            d[key] = overwrite[key]
        for key in d.keys():
            if not bool(d[key]):
                del d[key]
        results.append(d)
    return results


def prompt(text, validator, confirm=False,
           helptext='No help text provided', errortext='Invalid response!'):
    """Prompts for and validates user input

    Args:
        text (str): the prompt to present to the user
        validator (mixed): the dict, list, or string used to validate the
            repsonse
        confirm (bool): if true, user will be prompted to confirm value
        helptext (str): text to show if user response is "?"
        errortext (str): text to return if user response does not validate

    Return:
        Validated response to prompt
    """
    # Prepare string
    text = u'{} '.format(text.rstrip())
    # Prepare validator
    if isinstance(validator, (str, unicode)):
        validator = re.compile(validator, re.U)
    elif isinstance(validator, dict) and sorted(validator.keys()) == ['n', 'y']:
        text = u'{}({}) '.format(text, '/'.join(validator.keys()))
    elif isinstance(validator, dict):
        keys = validator.keys()
        keys.sort(key=lambda s: s.zfill(100))
        options = [u'{}. {}'.format(key, validator[key]) for key in keys]
    elif isinstance(validator, list):
        options = [u'{}. {}'.format(i + 1, val) for
                   i, val in enumerate(validator)]
    else:
        raise ValueError('Validator must be dict, list, or str.')
    # Validate response
    loop = True
    num_loops = 0
    while loop:
        # Print options
        try:
            options
        except UnboundLocalError:
            pass
        else:
            print '-' * 60 + '\nOPTIONS\n-------'
            for option in options:
                cprint(option)
            print '-' * 60
        # Prompt for value
        val = raw_input(text).decode(sys.stdin.encoding)
        if val.lower() == 'q':
            print 'User exited prompt'
            sys.exit()
        elif val.lower() == '?':
            print fill(helptext)
            loop = False
        elif isinstance(validator, list):
            try:
                result = validator[int(val) - 1]
            except IndexError:
                pass
            else:
                if num_loops >= 0:
                    loop = False
        elif isinstance(validator, dict):
            try:
                result = validator[val]
            except KeyError:
                pass
            else:
                loop = False
        else:
            try:
                validator.search(val).group()
            except AttributeError:
                pass
            else:
                result = val
                loop = False
        # Confirm value, if required
        if confirm and not loop:
            try:
                result = unicode(result)
            except UnicodeEncodeError:
                result = str(result)
            loop = prompt('Is this value correct: "{}"?'.format(result),
                          {'y' : False, 'n' : True}, confirm=False)
        elif loop:
            print fill(errortext)
        num_loops += 1
    # Return value as unicode
    return result


def utflatten(val):
    """Converts diacritcs in string to their to an ascii equivalents

    Modified to use the unidecode module, but kept alias so older scripts will
    still work.
    """
    return unidecode(val)


def parse_catnum(val, attrs=None, default_suffix='', min_suffix_length=0,
                 strip_suffix=False, prefixed_only=False):
    """Find and parse catalog numbers in a string

    Args:
        s (str): string containing catalog numbers or range
        attrs (dict): additional parameters keyed to EMu field
        default_suffix (str): default suffix to add if none present
        strip_suffx (bool): strip leading zeroes from suffix if True
        prefixed_only (bool): find only those catalog numbers that are
            prefixed by a valid museum code (NMNH or USNM)

    Returns:
        List of dicts containing catalog numbers parsed into prefix, number,
        and suffix: {'CatPrefix': 'G', 'CatNumber': '3551', 'CatSuffix': 00}.
        Pass to format_catnums to convert to strings.
    """
    if attrs is None:
        attrs = {}
    # Catch code using the old syntax
    if not isinstance(default_suffix, basestring):
        raise Exception('Default suffix must be a string')
    # Regular expressions for use with catalog number functions
    p_pre = r'(?:([A-Z]{3} |[A-Z]{4}) ?|(?:(USNM|NMNH)\s)?([BCGMRS])-?)?'
    p_num = r'([0-9]{1,6})'  # this will pick up ANY number
    p_suf = r'\s?(-[0-9]{1,4}|-[A-Z][0-9]{1,2}|[c,][0-9]{1,2}|\.[0-9]+)?'
    # Force regex to require a prefix if a USNM/NMNH catalog number
    if prefixed_only:
        p_pre = p_pre.replace(r'?:(USNM|NMNH)\s)?)', r'(?:(USNM|NMNH)\s)')
    regex = re.compile(r'\b(' + p_pre + p_num + p_suf + r')\b')
    all_id_nums = []
    for substring in re.split(r'\s(and|&)\s', val, flags=re.I):
        id_nums = _parse_matches(regex.findall(substring))
        id_nums = _fix_misidentified_suffixes(id_nums)
        id_nums = _fill_range(id_nums, substring)
        id_nums = _clean_suffixes(id_nums, attrs, default_suffix,
                                  min_suffix_length, strip_suffix)
        # Require unprefixed numeric catalog numbers integers to meet a
        # minimum length. This reduces false positives at the expense of
        # excluding records with low catalog numbers.
        id_nums = [id_num for id_num in id_nums
                   if id_num.get('CatPrefix')
                   or id_num.get('CatNumber', 0) > 999]
        # Format results as tuple
        all_id_nums.extend(id_nums)
    # Return parsed catalog numbers
    return all_id_nums


def parse_catnums(strings, *args, **kwargs):
    """Parse a list of strings containing catalog numbers

    See parse_catnums() for a description of the available arguments.

    Returns:
        A list of parsed catnums
    """
    # Return list of parsed catalog numbers
    catnums = []
    for s in strings:
        catnums.extend(parse_catnum(s, **kwargs))
    return catnums




def format_catnum(parsed, code=True, div=False):
    """Formats parsed catalog number to a string

    Args:
        parsed (dict): parsed catalog number
        code (bool): include museum code in catnum if True
        div (bool): include div abbreviation in catnum if True

    Returns:
        Catalog number formatted as a string, like 'G3551-00'. Use
        format_catnums to process a list of parsed catalog numbers.
    """
    try:
        return parsed['MetMeteoriteName']
    except KeyError:
        pass
    try:
        parsed['CatNumber']
    except KeyError:
        return ''
    keys = ('CatMuseumAcronym', 'CatDivision', 'CatPrefix', 'CatSuffix')
    for key in keys:
        parsed.setdefault(key, '')
        parsed[key] = parsed[key].strip()
    # Set museum code
    if code:
        parsed['CatMuseumAcronym'] = 'NMNH'
        if parsed['CatDivision'] == 'Meteorites':
            parsed['CatMuseumAcronym'] = 'USNM'
    if not parsed['CatPrefix']:
        parsed['CatPrefix'] = u''
    parsed['CatPrefix'] = parsed['CatPrefix'].upper()
    # Format catalog number
    catnum = (
        '{CatMuseumAcronym} {CatPrefix}{CatNumber}-{CatSuffix}'
        .format(**parsed)
        .rstrip('-')
        .strip()
        )
    # Add division if necessary
    if bool(catnum) and div:
        catnum += u' ({})'.format(parsed['CatDivision'][:3].upper())
        #catnum = u'{} {}'.format(d['CatDivision'][:3].upper(), catnum)
    return catnum




def format_catnums(parsed, code=True, div=False):
    """Converts a list of parsed catalog numbers into strings

    Args:
        parsed (list): list of dicts containing parsed catnums
        code (bool): include museum code in catnum if True
        div (bool): include div abbreviation in catnum if True

    Returns:
        List of catalog numbers formatted as strings: ['G3551-00']
    """
    if not isinstance(parsed, list):
        parsed = [parsed]
    catnums = []
    for catnum in parsed:
        catnums.append(format_catnum(catnum, code, div))
    return catnums


def sort_catnums(catnums):
    """Sort a list of catalog numbers

    Args:
        catnums (list): list of catalog numbers, either as strings or parsed
            into dicts

    Return:
        Sorted list of catalog numebrs. Catalog numbers are formatted in
        the same way as they were in the original list.
    """
    try:
        catnums = parse_catnums(catnums)
    except IndexError:
        # Catalog numbers were given as dicts, so return them that way
        return sorted(catnums, key=_catnum_keyer)
    else:
        # Catalog numbers are strings, so format them before returning them
        return format_catnums(sorted(catnums, key=_catnum_keyer))


def _catnum_keyer(catnum):
    """Create sortable key for a catalog number by zero-padding each component

    Args:
        catnum (str or dict): the catalog number to key

    Returns:
        Sortable catalog number
    """
    print catnum, type(catnum)
    if isinstance(catnum, basestring):
        try:
            catnum = parse_catnum(catnum)[0]
        except IndexError:
            print 'Sort error: ' + catnum
            return 'Z' * 63
    keys = ('CatPrefix', 'CatNumber', 'CatSuffix')
    return '|'.join([catnum.get(key, '').zfill(20) for key in keys])


def fxrange(start, stop, step):
    """Mimics functionality of xrange for floats

    From http://stackoverflow.com/questions/477486/

    Args:
        start (int or float): first value in range (inclusive)
        stop (int or float): last value in range (exclusive)
        step (float): value by which to increment start
    """
    rng = start
    while rng < stop:
        yield rng
        rng += step


def cprint(obj, show=True):
    """Conditionally pretty print an object

    Args:
        obj (mixed): the object to print
        show (bool): print the object if true
    """
    if not isinstance(obj, basestring) and show:
        pprint(obj)
    elif obj and show:
        print fill(obj, subsequent_indent='  ')


def rprint(obj, show=True):
    """Pretty print object, then pause execution

    Args:
        obj (mixed): the object to print
        show (bool): print the object if true
    """
    if show:
        cprint(obj)
        raw_input('Paused. Press any key to continue.')


def read_file(path, success, error=None):
    """Process file at given path using success callback"""
    try:
        with open(path, 'rb') as f:
            return success(f)
    except IOError:
        if error is None:
            raise
        else:
            return error(path)


def ucfirst(val):
    """Capitalize first letter of string while leaving the rest alone

    Args:
        val (str): string to capitalize

    Returns:
        Capitalized string
    """
    if not val:
        return val
    try:
        return val[0].upper() + val[1:]
    except IndexError:
        return val[0].upper()


def lcfirst(val):
    """Lowercase first letter of string while leaving the rest alone

    Args:
        val (str): string to capitalize

    Returns:
        Capitalized string
    """
    try:
        return val[0].lower() + val[1:]
    except IndexError:
        return val[0].lower()


def add_article(val):
    """Prepend the appropriate indefinite article to a string

    Args:
        val (str): string to which to add a/an

    Returns:
        String with indefinite article prepended
    """
    if val.startswith('a', 'e', 'i', 'o', 'u'):
        return u'an {}'.format(val)
    return u'an {}'.format(val)


def _parse_matches(matches):
    """Format catalog numbers from a parsed list"""
    id_nums = []
    for match in matches:
        id_num = dict(zip(CATKEYS, [val.rstrip('-,') for val in match]))
        # Handle meteorites
        if id_num['MetPrefix'] or id_num['CatMuseumAcronym'] == 'USNM':
            if id_num['MetPrefix']:
                return [{'MetMeteoriteName': id_num['FullNumber']}]
        # Handle catalog numbers from other departments
        else:
            id_num['CatNumber'] = int(id_num['CatNumber'])
            # Handle petrology suffix format (.0001)
            if id_num['CatSuffix'].startswith('.'):
                id_num['CatSuffix'] = id_num['CatSuffix'].lstrip('.0')
            else:
                id_num['CatSuffix'] = id_num['CatSuffix'].strip('-,.')
        id_nums.append(id_num)
    return id_nums


def _clean_suffixes(id_nums, attrs, default_suffix,
                    min_suffix_length, strip_suffix):
    """Clean the identification numbers based on passed arguments"""
    for i, id_num in enumerate(id_nums):
        # Clean suffixes
        if min_suffix_length:
            suffix = id_num['CatSuffix']
            id_nums[i]['CatSuffix'] = suffix.zfill(min_suffix_length)
        if strip_suffix:
            id_nums[i]['CatSuffix'] = u''
        elif not id_num['CatSuffix']:
            id_nums[i]['CatSuffix'] = default_suffix
        # Add additional attributes passed to the function
        id_nums[i].update(attrs)
        # Remove keys that do not correspond to EMu fields
        for key in ('FullNumber', 'MetPrefix'):
            del id_nums[i][key]
    return id_nums


def _fix_misidentified_suffixes(id_nums):
    """Check for ranges that have been misidentified as suffixes"""
    if len(id_nums) == 1:
        id_num = id_nums[0]
        try:
            suffix = int(id_num['CatSuffix'])
        except ValueError:
            pass
        else:
            if suffix > id_num['CatNumber']:
                first_num = id_num
                first_num['CatSuffix'] = u''
                last_num = {key: '' for key in CATKEYS}
                last_num['CatNumber'] = suffix
                for key in ('CatPrefix', 'CatMuseum'):
                    last_num[key] = first_num[key]
                id_nums = [first_num, last_num]
    return id_nums


def _fill_range(id_nums, substring):
    """Checks if a pair of catalog numbers appears to be a range"""
    try:
        first_num, last_num = id_nums
    except ValueError:
        pass
    else:
        is_range = (
            substring.count('-') > 0
            and substring.count('-') != 2
            and first_num['CatPrefix'] == last_num['CatPrefix']
            and last_num['CatNumber'] > first_num['CatNumber']
            and first_num['CatNumber'] > 10
            )
        # Fill range
        if is_range:
            id_nums = []
            for i in xrange(first_num['CatNumber'], last_num['CatNumber'] + 1):
                id_num = deepcopy(first_num)
                id_num['CatNumber'] = i
                id_nums.append(id_num)
    return id_nums
