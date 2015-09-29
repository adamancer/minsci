# -*- coding: utf-8 -*-

# Standard imports
import os
import re
import string
import sys
from copy import copy
from operator import itemgetter
from itertools import groupby
from textwrap import fill

# Third-party imports
from nameparser import HumanName
import pyodbc


"""
Includes convenience functions used by various local scripts. Do
not import any other local scripts into this program!
"""

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



def init_odbc(fp, kind='access'):
    """Opens ODBC connection based on database type"""
    dbs = {
        'access' : 'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=',
        'excel' : ('DRIVER={Microsoft Excel Driver'
                    ' (*.xls, *.xlsx, *.xlsm, *.xlsb)};DBQ=')
        }
    db = pyodbc.connect(dbs[kind] + fp)
    return db






def dict_from_odbc(cursor, tbl, col='*', where='',
               rec_id='ID', encoding='cp1252'):
    # Get list of columns
    if col == '*':
        col = [row.column_name for row in cursor.columns(tbl.strip('[]'))]
    elif not ',' in col:
        rec_id = col.strip('`')
        col = [col]
    # Prepare where clause
    if bool(where):
        where = ' WHERE {}'.format(where.replace('"', "'"))
    # Assemble query
    q = 'SELECT {} FROM {}{}'.format(','.join(col), tbl, where)
    print q
    # Execute query
    cursor.execute(q)
    records = {}
    result = cursor.fetchmany()
    error = ''
    while result:
        for row in result:
            for fld in row.cursor_description:
                if not bool(error) and fld[1] != str and tbl.endswith('$]'):
                    error = fill('Warning: Non-string data type '
                                 'found. Convert the input sheet '
                                 'to text to prevent data loss.')
            row = [s if bool(s) else '' for s in row]
            row = [s.decode(encoding) if isinstance(s, str)
                   else s for s in row]
            rec = dict(zip(col, row))
            if rec_id:
                records[rec[rec_id]] = rec
            else:
                records[len(records)] = rec
        result = cursor.fetchmany()
    if bool(error):
        print error
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
    """Formats string as comma-delimited string

    @param list
    @param boolean
    @return string
    """
    if lowercase:
        lst = [s[0].lower() + s[1:] for s in lst]
    if len(lst) <= 1:
        return ''.join(lst)
    elif len(lst) == 2:
        return ' and '.join(lst)
    else:
        last = lst.pop()
        return ', '.join(lst) + ', and ' + last


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
    elif isinstance(validator, dict):
        prompt = '{}({}) '.format(prompt, '/'.join(validator.keys()))
    elif isinstance(validator, list):
        options = ['{}. {}'.format(x + 1, validator[x])
                   for x in xrange(0, len(validator))]
    else:
        raw_input(fill('Error in minsci.helpers.prompt: '
                       'Validator must be dict, list, or str.'))
        raise
    # Validate response
    loop = True
    while loop:
        # Print options
        if isinstance(validator, list):
            print '{}\n{}'.format('\n'.join(options), '-' * 60)
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




def parse_catnum(catnum, attrs={}, default_suffix=False):
    """Parse catalog numbers into a dictionary


    Keyword arguments:
    s:               str. Catalog number as string.
    identifier:      str. Unique identifier.
    attrs:           dict. Additional parameters keyed to EMu field.
    default_suffix:  bool. If true, assume suffix of 00 for minerals
    """

    try:
        cps = regex.findall(catnum)
    except:
        return []
    else:
        keys = ('CatMuseumAcronym', 'CatPrefix', 'CatNumber', 'CatSuffix')
        temp = []
        for cp in cps:
            d = dict(zip(keys, cp[1:]))
            # Handle acronym
            if d['CatMuseumAcronym'] == 'USNM':
                d['CatDivision'] = 'Meteorites'
            del d['CatMuseumAcronym']
            # Handle meteorite numbers
            if ',' in d['CatSuffix'] or len(d['CatPrefix']) > 1:
                # Check for four-letter prefix (ex. ALHA)
                s = catnum
                try:
                    float(s[3])
                except:
                    d['MetMeteoriteNumber'] = s
                else:
                    d['MetMeteoriteNumber'] = s[0:3] + ' ' + s[3:]
                for key in keys:
                    try:
                        del d[key]
                    except:
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
                             [d['CatPrefix'],d['CatNumber'], ''])),
                    dict(zip(keys,
                             [d['CatPrefix'], int(d['CatSuffix']), '']))
                    ]
    # Check for ranges
    if len(cps) == 2\
       and '-' in cps\
       and catnum.count('-') != len(cps)\
       and cps[0]['CatPrefix'] == cps[1]['CatPrefix']\
       and cps[1]['CatNumber'] > cps[0]['CatNumber']:
        # Fill range
        print catnum + ' id\'d as a range'
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
        temp.append(cp)
    cps = temp
    # Force values to strings and add additional attributes
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
    # Return
    return cps




def parse_catnums(catnums, attrs={}, default_suffix=False):
    """Parse list of catalog numbers."""
    # Return list of parsed catalog numbers
    arr = []
    for catnum in catnums:
        arr += parse_catnum(catnum)
    return arr




def format_catnum(d, code=True, div=False):
    try:
        d['CatNumber']
    except:
        return ''
    keys = ('CatMuseumAcronym', 'CatDivision', 'CatPrefix', 'CatSuffix')
    for key in keys:
        try:
            if not d[key]:
                d[key] = ''
        except:
            d[key] = ''
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
        catnum += ' ({})'.format(d['CatDivision'][:3].upper())
    # Return formatted catalog number
    return catnum




def format_catnums(catnums):
    """Combine each entry in a list of parsed catalog numbers"""
    catnums = handle_catnums(catnums)
    return [format_catnum(d) for d in catnums]




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
