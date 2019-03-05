"""Populates an ebibliography record based on RIS data in NotNotes"""
from __future__ import print_function
from __future__ import unicode_literals

import logging
import pprint as pp
import re
from collections import namedtuple
from itertools import chain

import requests
import requests_cache
from dateparser import parse

from .bibbot import BibBot
from ....helpers import parse_names
from ....xmu import XMu, BiblioRecord




# List of keys that can contain multiple values
LISTS = [
    'AU',
    'A1',
    'A2',
    'A3',
    'A4',
    'ED',
    'KW',
    'N1',
    'SN',
    'UR'
]

# Dict mapping pub type to prefix. Only for cass where the prefix does not
# equal the first three letters of the pub type.
PREFIXES = {
    'Book Series': 'Bos'
}

ROLES = {
    'AU': u'Author',
    'A1': u'First author',
    'A2': u'Secondary author',
    'A3': u'Tertiary author',
    'A4': u'Subsidiary author',
    'ED': u'Editor'
}


Contributor = namedtuple('Contributor', ['name', 'role'])
Source = namedtuple('Source', ['type', 'parent_type'])

bot = BibBot()


class FillFromRIS(XMu):
    """Fill out skeleton bibliography records that have RIS data in notes"""

    def __init__(self, *args, **kwargs):
        parsers = kwargs.pop('parsers', {})
        if parsers is None:
            parsers = {}
        super(FillFromRIS, self).__init__(*args, **kwargs)
        self.records = []
        self.errors = []
        self.parsers = {'default': ['CY', 'DB', 'N1', 'UR']}
        for key, handler in parsers.items():
            self.parsers[key] = handler


    def iterate(self, element):
        """Pulls reference information from BibTex based on RIS in EMu record"""
        rec = self.parse(element)
        ris = rec('NotNotes').strip()
        # Check for urls in notes field
        if 'http' in ris and not 'TY' in ris:
            ris = get_ris(ris).strip()
        # Check for RIS data
        if 'TY' in ris:
            irn = rec('irn')
            try:
                formatted = emuize(ris , self.parsers)
            except (KeyError, ValueError) as e:
                self.errors.append(e)
                logging.exception('ris')
                return True
            if len(formatted) == 1:
                for rec in formatted:
                    if irn:
                        rec['irn'] = irn
                        if ris == rec('NotNotes'):
                            del rec['NotNotes']
                self.records.extend(formatted)




def ris2emu(fp, parsers=None):
    """Parses RIS data in the notes field of an ebibliography export"""
    bib = FillFromRIS(fp, container=BiblioRecord, parsers=parsers)
    bib.fast_iter(report=10)
    return bib.records


def split_records(ris):
    """Splits a RIS document into records"""
    records = []
    lines = []
    pattern = re.compile(r'[A-Z][A-Z0-9] {1,2}-')
    for line in ris.split('\n'):
        line = line.strip()
        # Not required for Python 2/3
        #if isinstance(line, str):
        #    try:
        #        line = line.decode('utf-8')
        #    except UnicodeDecodeError:
        #        line = line.decode('latin1')
        if pattern.match(line):
            lines.append(line)
            if line.startswith('ER'):
                records.append(lines)
                lines = []
    return records


def emuize(ris, parsers=None):
    """Converts RIS record to EMu ebibliography format"""
    records = split_records(ris)
    bibs = []
    for ris in records:
        rec = ris2dict(ris)
        # Anything with a DOI should be handled using doi.py
        #if rec.get('DO'):
        #    continue
        # Look for customizers based on UR
        parser = None
        for key, func in parsers.items():
            if [url for url in rec.get('UR', []) if key in url]:
                parser = func
                break
        else:
            parser = parsers['default']
        try:
            rec = parser(rec)
        except TypeError:
            rec = generic(rec, parser)
        source = get_type(rec)
        if source.parent_type is not None:
            parent_prefix = PREFIXES.get(source.parent_type, source.parent_type[:3])
        else:
            parent_prefix = None
        # Create a bibliography record
        bib = {}
        bib['BibRecordType'] = source.type
        bib['{}PublicationLanguage'] = rec.pop('LA', None)
        bib['{}Title'] = get_title(rec)
        bib['{}Volume'] = rec.pop('VL', None)
        bib['{}Pages'] = get_pages(rec)
        # Issue
        issue = rec.pop('IS', None)
        if source.type == 'Book' and not bib['{}Volume']:
            bib['{}Volume'] = issue
        else:
            bib['{}Issue'] = issue
        # Source title
        source_title = get_source(rec)
        if source_title is not None:
            bib['{}ParentRef'] = {
                'BibRecordType': source.parent_type,
                '{}Title'.format(parent_prefix): source_title
                }
            # Check for issn
            issns = rec.pop('SN', [])
            if len(issns) > 1:
                raise ValueError('Too many ISSNs!')
            if issns:
                issn = issns[0]
                if re.match('^\d{4}-\d{3}[\dX]$', issn, re.I):
                    bib['{}ParentRef']['{}ISSN'.format(parent_prefix)] = issn
                else:
                    raise ValueError('Not an ISSN: {}'.format(issn))
        # Contributors
        contributors = get_contributors(rec)
        blank = {'NamPartyType': 'Person'}
        parties = [p for p in contributors if p.name != blank]
        if len(parties) != len(contributors):
            bib['{}AuthorsEtAl'] = 'Yes'
        # Special handling for authors of theses/dissertations
        if bib.get('BibRecordType') == 'Thesis':
            bib['{}AuthorsRef'] = [p.name for p in parties][0]
        else:
            bib['{}AuthorsRef_tab'] = [p.name for p in parties]
            bib['{}Role_tab'] = [p.role for p in parties]
        # Publication date
        pub_date = get_date(rec)
        if pub_date is not None:
            bib['{}PublicationDates'] = pub_date
            bib['{}PublicationDate'] = pub_date
        # DOI
        doi = rec.pop('DO', None)
        if doi is not None:
            bib['AdmGUIDType_tab'] = ['DOI']
            bib['AdmGUIDIsPreferred_tab'] = ['Yes']
            bib['AdmGUIDValue_tab'] = [doi]
        # Store the original RIS file as a note
        bib['NotNotes'] = '\n'.join(ris)
        if len(ris) > 50:
            raise ValueError('RIS file is too long to fit in EMu notes field')
        # Add publisher info (books only)
        publisher = rec.pop('PB', None)
        if publisher is not None:
            if source.type == 'Book' and source_title is not None:
                bib['{}ParentRef']['BosPublishedByRef'] = {
                    'NamPartyType': 'Organization',
                    'NamOrganisation': publisher
                    }
                bib['{}ParentRef']['BosPublicationCity'] = rec.pop('CY', None)
            elif source.type == 'Book':
                bib['BooPublishedByRef'] = {
                    'NamPartyType': 'Organization',
                    'NamOrganisation': publisher
                    }
                bib['BooPublicationCity'] = rec.pop('CY', None)
        # Apply prefix
        prefix = PREFIXES.get(bib['BibRecordType'], bib['BibRecordType'][:3])
        bib = {key.format(prefix): val for key, val in bib.items() if val}
        try:
            bibs.append(BiblioRecord(bib).expand())
        except:
            BiblioRecord(bib).pprint(True)
            raise
        u1 = rec.pop('U1', None)
        if u1:
            print('Info: {}'.format(u1))
        rec = remove_duplicate_fields(rec, ris2dict(ris))
        if rec:
            pp.pprint(ris2dict(ris))
            raise KeyError('Found unhandled keys: {}'.format(list(rec.keys())))
    return bibs


def remove_duplicate_fields(rec, orig):
    """Removes fields holding duplicate data"""
    orig = {key: val for key, val in orig.items() if not key in rec}
    for key in list(rec.keys()):
        val = rec[key]
        if val in list(orig.values()):
            del rec[key]
    return rec


def ris2dict(ris):
    """Converts a RIS record to a dictionary"""
    rec = {}
    for line in ris:
        key, val = [s.strip(' -') for s in line.split('-', 1)]
        if key in LISTS:
            rec.setdefault(key, []).append(val)
        else:
            if rec.get(key):
                raise ValueError('{} is not listable'.format(key))
            rec[key] = val
    return {key: val for key, val in rec.items() if any(val)}


def get_type(rec):
    """Determines the kind of publication based on TY"""
    bib_type = rec.pop('TY')
    # Classify publication by type. Keys with a leading underscore are
    # assigned by customizer functions and are not official RIS types.
    types = {
        'ABST': Source('Article', 'Journal'),
        'BOOK': Source('Book', 'Book Series'),
        'CHAP': Source('Chapter', 'Book'),
        'CPAPER': Source('Article', 'Journal'),
        'JOUR': Source('Article', 'Journal'),
        'RPRT': Source('Article', 'Journal'),
        'THES': Source('Thesis', None),
        '_MONOGRAPH': Source('Book', 'Book Series')
    }
    # Handle M3
    work_type = rec.pop('M3', None)
    if work_type is not None:
        work_types = {
            'ABST': ['Abstract'],
            'BOOK': ['Proceedings'],
            'CHAP': ['Book', 'Report'],
            'CPAPER': ['Paper'],
            'JOUR': ['Journal article', 'Paper', 'Report'],
            'RPRT': ['Report']
        }
        if not work_type in work_types.get(bib_type, []):
            raise ValueError('Work type {} (bib_type={})'.format(work_type, bib_type))
    return types[bib_type]


def get_title(rec):
    """Returns publication title"""
    keys = ['TI', 'T1']
    vals = [val for val in [rec.pop(key, None) for key in keys] if val]
    if not vals:
        raise ValueError('No publication title provided')
    return vals[0]


def get_date(rec):
    """Returns publication date"""
    year = rec.pop('PY', None)
    date = rec.pop('Y1', None)
    if date:
        parsed = parse(date)
        if year is not None and int(year) != parsed.year:
            raise ValueError('Inconsistent dates: {}'.format(rec))
        return parsed.strftime(r'%Y-%m-%d')
    return year


def get_source(rec):
    """Returns source title (journal, book, etc.)"""
    keys = ['JF', 'T2', 'J1', 'T3']
    vals = [val for val in [rec.pop(key, None) for key in keys] if val]
    if vals:
        return vals[0]


def get_pages(rec):
    """Returns page range"""
    keys = ('SP', 'EP', 'LP')
    vals = [val for val in [rec.pop(key, None) for key in keys] if val]
    if len(set(vals)) == 1:
        return vals[0]
    return '-'.join(vals)


def get_contributors(rec):
    """Returns parsed list of contributors"""
    contributors = []
    for key, role in ROLES.items():
        names = rec.pop(key, [])
        if names:
            if not isinstance(names, list):
                names = [names]
            parties = [parse_names(name, True) for name in names]
            contributors.extend([Contributor(name, role)
                                 for name in chain(*parties)])
    return contributors


def get_ris(url):
    """Retrieves RIS from a url"""
    if 'pubs.er.usgs.gov' in url or 'pubs.usgs.gov' in url:
        url = url.replace('pubs.usgs.gov', 'pubs.er.usgs.gov')
        return bot.download(url.rstrip('/? \n\r') + '?mimetype=ris')
    print('Failed to retrieve {}'.format(url))
    return url


def generic(ris, keys):
    """Parses generic RIS records, excluding keys"""
    for key in keys:
        ris.pop(key, None)
    return ris
