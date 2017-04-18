"""Populates an ebibliography record based on RIS data in NotNotes"""

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


USGS = {
    'Annual Report': 'U. S. Geological Survey Annual Report',
    'Bulletin': 'U. S. Geological Survey Bulletin',
    'Monograph': 'U. S. Geological Survey Monograph',
    'Professional Paper': 'U. S. Geological Survey Professional Paper'
}

LISTS = ['AU', 'A2', 'A3', 'A4', 'ED', 'KW', 'N1', 'SN', 'UR']

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
        super(FillFromRIS, self).__init__(*args, **kwargs)
        self.records = []


    def iterate(self, element):
        """Pulls reference information from BibTex based on DOI in EMu record"""
        rec = self.parse(element)
        ris = rec('NotNotes').strip()
        # Check for urls in notes field
        if 'http' in ris and not 'TY' in ris:
            ris = get_ris(ris).strip()
        # Check for RIS data
        if 'TY' in ris:
            irn = rec('irn')
            formatted = emuize(ris)
            if len(formatted) == 1:
                for rec in formatted:
                    if irn:
                        rec['irn'] = irn
                        if ris == rec('NotNotes'):
                            del rec['NotNotes']
                self.records.extend(formatted)




def ris2emu(fp):
    """Parses RIS data in the notes field of an ebibliography export"""
    bib = FillFromRIS(fp, container=BiblioRecord)
    bib.fast_iter(report=25)
    return bib.records


def split_records(ris):
    """Splits a RIS document into records"""
    records = []
    lines = []
    pattern = re.compile(ur'[A-Z][A-Z0-9] {1,2}-')
    for line in ris.split('\n'):
        line = line.strip()
        if isinstance(line, str):
            try:
                line = line.decode('utf-8')
            except UnicodeDecodeError:
                line = line.decode('latin1')
        if pattern.match(line):
            lines.append(line)
            if line.startswith('ER'):
                records.append(lines)
                lines = []
    return records


def emuize(ris, customizer=None):
    """Converts RIS record to EMu ebibliography format"""
    records = split_records(ris)
    bibs = []
    for ris in records:
        rec = ris2dict(ris)
        # Anything with a DOI should be handled using doi.py
        if rec.get('DO'):
            continue
        # Look for customizers based on UR
        if customizer is None:
            for key, func in CUSTOMIZERS.iteritems():
                if [url for url in rec.get('UR', []) if key in url]:
                    customizer = func
                    break
        if customizer is not None:
            rec = customizer(rec)
        else:
            pass#pp.pprint(rec)
        source = get_type(rec)
        parent_prefix = PREFIXES.get(source.parent_type, source.parent_type[:3])
        # Create a bibliography record
        bib = {}
        bib['BibRecordType'] = source.type
        bib['{}PublicationLanguage'] = rec.pop('LA', None)
        bib['{}Title'] = get_title(rec)
        bib['{}Volume'] = rec.pop('VL', None)
        bib['{}Issue'] = rec.pop('IS', None)
        bib['{}Pages'] = get_pages(rec)
        source_title = get_source(rec)
        if source_title is not None:
            bib['{}ParentRef'] = {
                'BibRecordType': source.parent_type,
                '{}Title'.format(parent_prefix): source_title
                }
        # Contributors
        contributors = get_contributors(rec)
        blank = {'NamPartyType': 'Person'}
        parties = [p for p in contributors if p.name != blank]
        if len(parties) != len(contributors):
            bib['{}AuthorsEtAl'] = 'Yes'
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
        bib = {key.format(prefix): val for key, val in bib.iteritems() if val}
        try:
            bibs.append(BiblioRecord(bib).expand())
        except:
            BiblioRecord(bib).pprint(True)
            raise
        if rec:
            print sorted(rec.keys())
            pp.pprint(ris2dict(ris))
            raw_input()
    return bibs


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
    return {key: val for key, val in rec.iteritems() if any(val)}


def get_type(rec):
    """Determines the kind of publication based on TY"""
    bib_type = rec.pop('TY')
    # Classify publication by type. Keys with a leading underscore are
    # assigned by customizer functions and are not official RIS types.
    types = {
        'BOOK': Source('Book', 'Book Series'),
        'JOUR': Source('Article', 'Journal'),
        'RPRT': Source('Article', 'Journal'),
        '_MONOGRAPH': Source('Book', 'Book Series')
    }
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
    for key, role in ROLES.iteritems():
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
        print url
        result = bot.download(url.rstrip('/? \n\r') + '?mimetype=ris')
        print result
        return bot.download(url.rstrip('/? \n\r') + '?mimetype=ris')
    print 'Failed to retrieve {}'.format(url)
    return url


def usgs(ris):
    """Formats RIS records from the USGS"""
    # Remove keys containing info we don't want/need
    keys = ['A3', 'CY', 'DB', 'ET', 'M3', 'UR']
    for key in keys:
        ris.pop(key, None)
    ris['T2'] = USGS.get(ris['T2'], ris['T2'])
    if ris.get('SN') and ris.get('TY') == 'RPRT':
        if ris.get('VL'):
            raise ValueError('Both VL and SN populated for USGS report')
        ris['VL'] = ris.pop('SN')[0]
    #if 'cont' in ris['VL']:
    #    ris['VL'] = ris['VL'].split('cont', 1)[0].strip() + ' (cont.)'
    # Identify monographs based on T2
    series = ['U. S. Geological Survey Annual Report']
    if ris.get('T2') in series:
        ris['TY'] = '_MONOGRAPH'
    return ris


def pnas(ris):
    """Formats RIS records from PNAS"""
    keys = ['AN', 'DB', 'SN', 'UR']
    for key in keys:
        ris.pop(key, None)
    return ris


def hathi(ris):
    """Formats RIS records from the Hathi Trust"""
    keys = ['ID', 'KW', 'M1', 'N1', 'TP', 'UR']
    for key in keys:
        ris.pop(key, None)
    # Check for countries in author list
    if ris['AU'][-1].endswith('.'):
        ris['AU'].pop()
    return ris


def jstor(ris):
    """Formats RIS records from JSTOR"""
    keys = ['AB', 'C1', 'PB', 'SN', 'UR']
    for key in keys:
        ris.pop(key, None)
    return ris




CUSTOMIZERS = {
    'catalog.hathitrust.org': hathi,
    'jstor.org': jstor,
    'ncbi.nlm.nih.gov/pmc': pnas,
    'pubs.er.usgs.gov': usgs
}
