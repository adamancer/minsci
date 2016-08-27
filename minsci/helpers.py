# -*- coding: utf-8 -*-

# Standard imports
import collections
import os
import re
import string
import sys
from copy import copy
from itertools import groupby
from operator import itemgetter
from pprint import pprint
from textwrap import fill

# Third-party imports
import inflect
import pyodbc
from nameparser import HumanName




def __init__(self):
    digs = string.digits + string.lowercase
    boundary = '-' * 60
    # Regular expressions for use with catalog number functions
    p_acr = '((USNM|NMNH)\s)?'
    p_pre = '([A-Z]{1,4})?'
    p_num = '([0-9]{2,6})'
    p_suf = '(-[0-9]{1,4}|-[A-Z][0-9]{1,2}|[c,][0-9]{1,2}|\.[0-9]+)?'
    regex = re.compile('\\b' + p_acr + p_pre + p_num + p_suf + '\\b')
    debug = False




def base2int(x, base):
    """Converts integer in specified base to base 10"""
    return int(x, base)




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
    """
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
        where = ''
    else:
        where = u' WHERE {}'.format(where.replace('"', "'"))
    # Assemble query
    q = u'SELECT {} FROM {}{}'.format(','.join(cols), tbl, where)
    # Execute query
    try:
        cursor.execute(q)
    except:
        print q
        raise
    records = {}
    result = cursor.fetchmany()
    error = ''
    n = 0  # count of records to comparse to length of dict
    while result:
        for row in result:
            for fld in row.cursor_description:
                if not bool(error) and fld[1] != str and tbl.endswith('$]'):
                    error = fill('Warning: Non-string data type '
                                 'found. Convert the input sheet '
                                 'to text to prevent data loss.')
            row = [s if bool(s) else '' for s in row]
            row = [s.decode(encoding) if isinstance(s, str) else s for s in row]
            rec = dict(zip(cols, row))
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
            n += 1
        result = cursor.fetchmany()
    if bool(error):
        print error
    if len(records) < n:
        cprint('Warning: Duplicate keys. Some data not included in dict.')
    return records




def int2base(x, base):
    """Converts base 10 integer to specified base"""
    if x < 0: sign = -1
    elif x==0: return '0'
    else: sign = 1
    x *= sign
    digits = []
    while x:
        digits.append(digs[x % base])
        x /= base
    if sign < 0:
        digits.append('-')
    digits.reverse()
    return ''.join(digits).upper()




def sort_by_reference(lst, order):
    """Reorder list to match order of reference list"""
    return sorted(sorted(lst), key=lambda x: _sorter(x, order))




def _sorter(key, order):
    """Returns index in order that starts with key.

    Returns -1 if key not found.
    """
    try:
        x = [x for x in xrange(0, len(order))
             if key.startswith(order[x])][0]
    except:
        print 'Ordering error: ' + key + ' does not exist in order list'
        x = -1
    return x




def oxford_comma(lst, lowercase=True):
    """Formats list as comma-delimited string

    @param list
    @param boolean
    @return string
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




def singular(s):
    inflected = inflect.engine().singular_noun(s)
    if inflected:
        return inflected
    return s




def plural(s):
    return inflect.engine().plural(singular(s))




def dedupe(lst, lower=True):
    """Dedupes list while maintaining order and case"""
    orig = copy(lst)
    if lower:
        lst = [val.lower() for val in lst]
    keep = [i for i in xrange(len(lst)) if not lst[i] in lst[:i]]
    return [orig[i] for i in keep]




def parse_names(name_string, last_name_first=False):
    """Parses name stirngs into components using nameparser"""
    # Normalize periods
    name_string = name_string\
                  .replace('. ','.')\
                  .replace('.','. ')\
                  .replace(' & ',' and ')
    # Problem titles
    problem_words = [
        'Count',
        'Countess'
        ]
    # Suffixes
    suffixes = [
        'Jr',
        'Sr',
        'II',
        'III',
        'IV',
        'Esq'
        ]
    suffixes = '|'.join(['\s' + suf for suf in suffixes])
    # Split names on semicolon, ampersand, or and
    r = re.compile(' and |&|;', re.I)
    names = [s.strip() for s in r.split(name_string) if bool(s)]
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
        for word in sorted(problem_words, key=lambda s:len(s))[::-1]:
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


def prompt(prompt, validator, confirm=False,
           helptext='No help text provided', errortext='Invalid response!'):
    """Prompts user and validates response based on validator

    @param string
    @param regex, list, or dict
    @param boolean
    @param string
    @param string
    """
    # Prepare string
    prompt = u'{} '.format(prompt.rstrip())
    # Prepare validator
    if isinstance(validator, (str, unicode)):
        validator = re.compile(validator, re.U)
    elif isinstance(validator, dict) and sorted(validator.keys()) == ['n', 'y']:
        prompt = u'{}({}) '.format(prompt, '/'.join(validator.keys()))
    elif isinstance(validator, dict):
        keys = validator.keys()
        keys.sort(key=lambda s:s.zfill(100))
        options = [u'{}. {}'.format(key, validator[key]) for key in keys]
    elif isinstance(validator, list):
        options = [u'{}. {}'.format(x + 1, validator[x])
                   for x in xrange(0, len(validator))]
    else:
        raw_input(fill('Error in minsci.helpers.prompt: '
                       'Validator must be dict, list, or str.'))
        raise
    # Validate response
    loop = True
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
        a = raw_input(prompt).decode(sys.stdin.encoding)
        if a.lower() == 'q':
            print 'User exited prompt'
            sys.exit()
        elif a.lower() == '?':
            print fill(helptext)
            loop = False
        elif isinstance(validator, list):
            try:
                i = int(a) - 1
                result = validator[i]
            except:
                pass
            else:
                if i >= 0:
                    loop = False
        elif isinstance(validator, dict):
            try:
                result = validator[a]
            except:
                pass
            else:
                loop = False
        else:
            try:
                validator.search(a).group()
            except:
                pass
            else:
                result = a
                loop = False
        # Confirm value, if required
        if confirm and not loop:
            try:
                result = unicode(result)
            except:
                result = str(result)
            loop = prompt('Is this value correct: "{}"?'.format(result),
                          {'y' : False, 'n' : True}, confirm=False)
        elif loop:
            print fill(errortext)
    # Return value as unicode
    return result




def utflatten(s):
    """Converts diacritcs in string to their to an ascii equivalents"""
    d = {
        u'\xe0' : 'a',    # à
        u'\xc0' : 'A',    # À
        u'\xe1' : 'a',    # á
        u'\xc1' : 'A',    # Á
        u'\xe2' : 'a',    # â
        u'\xc2' : 'A',    # Â
        u'\xe3' : 'a',    # ã
        u'\xc3' : 'A',    # Ã
        u'\xe4' : 'a',    # ä
        u'\xc4' : 'A',    # Ä
        u'\xe5' : 'a',    # å
        u'\xc5' : 'A',    # Å
        u'\xe7' : 'c',    # ç
        u'\xc7' : 'C',    # Ç
        u'\xe8' : 'e',    # è
        u'\xc8' : 'E',    # È
        u'\xe9' : 'e',    # é
        u'\xc9' : 'E',    # É
        u'\xea' : 'e',    # ê
        u'\xca' : 'E',    # Ê
        u'\xeb' : 'e',    # ë
        u'\xcb' : 'E',    # Ë
        u'\xed' : 'i',    # í
        u'\xcd' : 'I',    # Í
        u'\xef' : 'i',    # ï
        u'\xcf' : 'I',    # Ï
        u'\xf1' : 'n',    # ñ
        u'\xd1' : 'N',    # Ñ
        u'\xf3' : 'o',    # ó
        u'\xd3' : 'O',    # Ó
        u'\xf4' : 'o',    # ô
        u'\xd4' : 'O',    # Ô
        u'\xf6' : 'o',    # ö
        u'\xd6' : 'O',    # Ö
        u'\xf8' : 'o',    # ø
        u'\xd8' : 'O',    # Ø
        u'\xfc' : 'u',    # ü
        u'\xdc' : 'U',    # Ü
        u'\xfd' : 'y',    # ý
        u'\xdd' : 'Y',    # Ý
        u'\u0107' : 'c',  # ć
        u'\u0106' : 'C',  # Ć
        u'\u010d' : 'c',  # č
        u'\u010c' : 'C',  # Č
        u'\u0115' : 'e',  # ĕ
        u'\u0114' : 'E',  # Ĕ
        u'\u011b' : 'e',  # ě
        u'\u011a' : 'E',  # Ě
        u'\u0144' : 'n',  # ń
        u'\u0143' : 'N',  # Ń
        u'\u0148' : 'n',  # ň
        u'\u0147' : 'N',  # Ň
        u'\u0151' : 'o',  # ő
        u'\u0150' : 'O',  # Ő
        u'\u0159' : 'r',  # ř
        u'\u0158' : 'R',  # Ř
        u'\u0161' : 's',  # š
        u'\u0160' : 'S',  # Š
        u'\u0163' : 't',  # ţ
        u'\u0162' : 'T',  # Ţ
        u'\u017c' : 'z',  # ż
        u'\u017b' : 'Z',  # Ż
        u'\u017e' : 'z',  # ž
        u'\u017d' : 'Z',  # Ž
        u'\u0301' : "'",  # ́
        u'\u03b2' : 'b',  # β
        u'\u0392' : 'B',  # Β
        u'\u2019' : "'",  # ’
        u'\u03b1' : 'a',  # α
        u'\u0391' : 'A',  # Α
        u'\u03b3' : 'g',  # γ
        u'\u0393' : 'G',  # Γ
        u'\u25a1' : '',  # □
        }
    # Flatten string
    s = ''.join([d[c] if c in d else c for c in s])
    # Check for non-ascii characters in flattened string
    nonascii = []
    for c in s:
        if ord(c) > 128:
            nonascii += utfmap(c)
    if len(nonascii):
        print 'Warning: Unhandled non-ascii characters in "' + s + '"'
        print '\n'.join(nonascii)
        raw_input()
    # Return flattened string
    return s




def utfmap(s):
    out = []
    for c in s.lower(): out.append(repr(c) + " : '',  # " + s.lower())
    if s.lower() != s.upper():
        for c in s.upper(): out.append(repr(c) + " : '',  # " + s.upper())
    return out




def parse_catnum(s, attrs={}, default_suffix=False, strip_suffix=False):
    """Find and parse catalog numbers in a string

    Args:
        s (str): string containingcatalog number(s) or range
        attrs (dict): additional parameters keyed to EMu field
        default_suffix (bool): add suffix -00 for minerals if True
        strip_suffx (bool): strip leading zeroes from suffix if True

    Returns:
        List of dicts containing catalog numbers parsed into prefix, number,
        and suffix: {'CatPrefix': 'G', 'CatNumber': '3551', 'CatSuffix': 00}.
        Pass to format_catnums to convert to strings.
    """

    # Regular expressions for use with catalog number functions
    p_acr = '((USNM|NMNH)\s)?'
    p_pre = '([A-Z]{3,4} ?|[BCGMR]-?)?'
    p_num = '([0-9]{1,6})'  # this will pick up ANY number
    p_suf = '\s?(-[0-9]{1,4}|-[A-Z][0-9]{1,2}|[c,][0-9]{1,2}|\.[0-9]+)?'
    regex = re.compile('\\b(' + p_acr + p_pre + p_num + p_suf + ')\\b')

    results = []
    for s in re.split('\s(and|&)\s', s, flags=re.I):
        try:
            cps = regex.findall(s)
        except:
            return []
        else:
            keys = ('CatMuseumAcronym', 'CatPrefix', 'CatNumber', 'CatSuffix')
            temp = []
            for cp in cps:
                match = cp[0]
                d = dict(zip(keys, cp[2:]))
                # Handle acronym
                if d['CatMuseumAcronym'] == 'USNM':
                    d['CatDivision'] = 'Meteorites'
                del d['CatMuseumAcronym']
                # Handle meteorite numbers
                if ',' in d['CatSuffix'] or 3 <= len(d['CatPrefix']) <= 4:
                    # Check for four-letter prefix (ex. ALHA)
                    try:
                        int(match[3])
                    except:
                        d['MetMeteoriteName'] = match
                    else:
                        d['MetMeteoriteName'] = match[0:3] + ' ' + match[3:]
                    for key in keys:
                        try:
                            del d[key]
                        except KeyError:
                            pass
                # Handle catalog numbers
                else:
                    d['CatNumber'] = int(d['CatNumber'])
                    # Handle petrology suffix format (.0001)
                    if d['CatSuffix'].startswith('.'):
                        d['CatSuffix'] = d['CatSuffix'].lstrip('.0')
                    else:
                        d['CatSuffix'] = d['CatSuffix'].strip('-,.')
                temp.append(d)
        cps = temp
        # Check for ranges misidentified as suffixes
        if len(cps) == 1:
            d = cps[0]
            try:
                suffix = int(d['CatSuffix'])
            except:
                pass
            else:
                # Suffix appears to be a second catalog number
                if suffix > d['CatNumber']:
                    cps = [
                        dict(zip(keys,
                                 ['', d['CatPrefix'], d['CatNumber'], ''])),
                        dict(zip(keys,
                                 ['', d['CatPrefix'], int(d['CatSuffix']), '']))
                        ]
        # Check for ranges
        try:
            is_range = (
                len(cps) == 2
                and len([cp for cp in cps if 'CatNumber' in cp]) == 2
                and s.count('-') and s.count('-') != 2
                and cps[0]['CatPrefix'] == cps[1]['CatPrefix']
                and cps[1]['CatNumber'] > cps[0]['CatNumber']
            )
        except:
            pass
            #print cps
            #raise
        if is_range:
            # Fill range
            print '{} appears to contain a range'.format(s)
            cps = [{'CatPrefix' : cps[0]['CatPrefix'], 'CatNumber' : x}
                   for x in xrange(cps[0]['CatNumber'],
                                   cps[1]['CatNumber'] + 1)]
        # Special handling for suffixes
        temp =[]
        for cp in cps:
            try:
                cp['CatSuffix']
            except:
                if default_suffix != False:
                    cp['CatSuffix'] = default_suffix
            else:
                if not bool(cp['CatSuffix']):
                    if default_suffix != False:
                        cp['CatSuffix'] = default_suffix
                    else:
                        del cp['CatSuffix']
            try:
                cp['CatSuffix']
            except:
                pass
            else:
                if strip_suffix:
                    cp['CatSuffix'] = cp['CatSuffix'].lstrip('0')
                    if not bool(cp['CatSuffix']):
                        del cp['CatSuffix']
            temp.append(cp)
        cps = temp
        # Force values to strings and blanks to None and add
        # additional attributes
        temp =[]
        for cp in cps:
            for key in cp:
                if bool(cp[key]):
                    cp[key] = str(cp[key])
                else:
                    cp[key] = None
            for key in attrs:
                cp[key] = str(attrs[key])
            temp.append(cp)
        cps = temp
        # Require unprefixed numeric catalog numbers integers to meet a
        # minimum length. This reduces false positives at the expense of
        # excluding records with low catalog numbers.
        temp = []
        for cp in cps:
            try:
                pre = cp['CatPrefix']
            except KeyError:
                pre = None
            try:
                num = cp['CatNumber']
            except KeyError:
                # This is a meteorite number
                temp.append(cp)
            else:
                if num is None:
                    print s
                    raw_input(cps)
                if not (pre is None and len(num) < 4):
                    temp.append(cp)
        results.extend(cps)
    # Return parsed catalog numbers
    return results




def parse_catnums(catnums, attrs={}, default_suffix=False):
    """Parse list of catalog numbers."""
    # Return list of parsed catalog numbers
    arr = []
    for catnum in catnums:
        arr += parse_catnum(catnum)
    return arr




def format_catnum(d, code=True, div=False):
    """Formats parsed catalog number to a string

    Args:
        d (dict): parsed catalog number
        code (bool): include museum code in catnum if True
        div (bool): include div abbreviation in catnum if True

    Returns:
        Catalog number formatted as a string: 'G3551-00'. Use
        format_catnums to process a list of parsed catalog numbers.
    """
    try:
        return d['MetMeteoriteName']
    except KeyError:
        pass
    try:
        d['CatNumber']
    except KeyError:
        return ''
    keys = ('CatMuseumAcronym', 'CatDivision', 'CatPrefix', 'CatSuffix')
    for key in keys:
        try:
            if not d[key]:
                d[key] = ''
        except:
            d[key] = ''
        else:
            d[key] = d[key].strip('-')
    # Set museum code
    if code:
        d['CatMuseumAcronym'] = 'NMNH'
        if d['CatDivision'] == 'Meteorites':
            d['CatMuseumAcronym'] = 'USNM'
    if not d['CatPrefix']:
        d['CatPrefix'] = ''
    d['CatPrefix'] = d['CatPrefix'].upper()
    # Format catalog number
    catnum = (
        '{CatMuseumAcronym} {CatPrefix}{CatNumber}-{CatSuffix}'
        .format(**d)
        .rstrip('-')
        .strip()
        )
    # Add division if necessary
    if bool(catnum) and div:
        catnum += u' ({})'.format(d['CatDivision'][:3].upper())
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
    for d in parsed:
        catnums.append(format_catnum(d, code, div))
    return catnums




def sort_catnums(catnums):
    """Sort a list of catalog numbers"""
    catnums = handle_catnums(catnums)
    arr = []
    for d in catnums:
        sort = []
        for key in ('CatPrefix','CatNumber','CatSuffix'):
            if not key in d or not d[key] or not bool(d[key]):
                val = '-'
            else:
                val = d[key]
            if len(val) > 20:
                raw_input('Error: Length ' + str(len(val)))
            sort.append('0' * (20 - len(val)) + val)
        arr.append((d, '|'.join(sort)))
    return combine_catnums([cn[0] for cn
                                 in sorted(arr, key=lambda cn:cn[1])])




def handle_catnums(val):
    """Return list of parsed catalog numbers"""
    if isinstance(val, str) or isinstance(val, unicode):
        return parse_catnum(find_catnums(val))
    elif isinstance(val, list):
        if len(val) and isinstance(val[0], dict) and 'CatNumber' in val[0]:
            return val
        elif len(val):
            arr = []
            for s in val:
                arr += parse_catnum(s)
            return arr
        else:
            return val
    elif isinstance(val, dict):
        return [val]
    else:
        print 'Error: Could not handle ' + val




def fxrange(start, stop, step):
    """xrange for floats. From http://stackoverflow.com/questions/477486/"""
    r = start
    while r < stop:
        yield r
        r += step




def cprint(s, show=True, encoding='cp1252'):
    """Conditional print"""
    if not isinstance(s, basestring) and show:
        pprint(s)
    elif bool(s) and show:
        print fill(s, subsequent_indent='  ')



def rprint(s):
    cprint(s)
    raw_input('Paused. Press any key to continue.')


def read_file(path, success, error=None):
    try:
        with open(path, 'rb') as f:
            return success(f)
    except IOError:
        if error is None:
            raise
        else:
            return error(path)
