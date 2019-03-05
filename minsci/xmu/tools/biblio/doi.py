# -*- coding: utf-8 -*-
"""Populates ebibliography records based on BibTeX records pulled using DOI"""
from __future__ import print_function
from __future__ import unicode_literals

import csv
import io
import logging
import os
import pprint as pp
import re
from datetime import datetime

import requests
import requests_cache
from dateparser import parse
from nameparser import HumanName

from .bibbot import BibBot
from .ris import split_records, ris2dict
from ....xmu.constants import FIELDS
from ....xmu import XMu, BiblioRecord, write


MODULE = 'ebibliography'

PUB_TYPES = {
    'article': 'Art',
    'book': 'Boo',
    'incollection': 'Art',
    'misc': 'Art',
    'techreport': 'Art',
    'thes': 'The'
}

SOURCES = {
    'Book': 'booktitle',
    'Journal': 'journal'
}

# List of entities from BibTeX
ENTITIES = {
    r'$\mathsemicolon$': u';',
    r'{\{AE}}': u'Æ',
    r'({IUCr})': u'(IUCr)',
    r'{\textdegree}': u'°' ,
    r'{\textquotesingle}': u"'",
    r'\textemdash': u'—',
    r'\textendash': u'–',
    r'St\u0e23\u0e16ffler': u'Stoffler',
    r'{\'{a}}': 'a'
}


bot = BibBot()


class FillFromDOI(XMu):
    """Fill out skeleton bibliography records that have DOIs"""

    def __init__(self, *args, **kwargs):
        super(FillFromDOI, self).__init__(*args, **kwargs)
        self.records = []
        self.errors = []


    def iterate(self, element):
        """Pulls reference information from BibTeX based on DOI in EMu record"""
        rec = self.parse(element)
        doi = rec.get_guid('DOI')
        # Check for DOIs in the notes field if not found in the GUID table
        note = rec('NotNotes')
        ris = None
        #if not doi and 'DO' in note:
        #    print 'this?'
        #    ris = ris2dict(split_records(note)[0])
        #    doi = ris.get('DO')
        #    if doi:
        #        rec['AdmGUIDType_tab'] = 'DOI'
        #        rec['AdmGUIDValue_tab'] = clean_doi(doi)
        if doi:
            if 'bhl.title' in doi:
                raise ValueError('BHL DOIs are forbidden: {}'.format(doi))
            elif '/PANGAEA.' in doi:
                raise ValueError('PANGAEA DOIs are forbidden: {}'.format(doi))
            elif '/10.4095/' in doi:
                raise ValueError('FastLink DOIS are forbidden: {}'.format(doi))
            try:
                bibtex = doi2bib(doi)
            except ValueError as e:
                logging.exception('doi')
                bibtex = None
            if bibtex is not None:
                try:
                    formatted = emuize(parse_bibtex(bibtex))
                except ValueError as e:
                    logging.exception('doi')
                    self.errors.append(e)
                formatted['irn'] = rec('irn')
                # Remove DOIs, since these already exist in the source
                # record and the existing values are already cased properly.
                # DOIs found in the notes field are excepted.
                if ris is None:
                    del formatted['AdmGUIDType_tab']
                    del formatted['AdmGUIDValue_tab']
                formatted['NotNotes'] = bibtex
                self.records.append(formatted)


def doi2emu(fp):
    """Parses BibTeX data for a DOI found in an ebibliography export"""
    bib = FillFromDOI(fp, container=BiblioRecord)
    bib.fast_iter(report=10)
    return bib.records


def doi2bib(doi):
    """Returns a bibTeX string of metadata for a given DOI.

    Source: https://gist.github.com/jrsmith3/5513926

    Args:
        doi (str): a valid DOI corresponding to a publication

    Returns:
        BibTeX record as a string
    """
    url = requests.compat.urljoin('https://doi.org/', doi)
    print('Checking {}...'.format(url))
    headers = {'accept': 'application/x-bibtex'}
    response = bot.get(url, headers=headers)
    if response.text.startswith('@'):
        return response.text
    else:
        raise ValueError('  ERROR: Could not resolve {}'.format(doi))
    return None


def parse_bibtex(bib):
    """Parses the BibTeX returned by the DOI resolver

    Args:
        bib (str): a BibTeX record

    Returns:
        Dict containing reference data
    """
    for entity, repl in ENTITIES.items():
        bib = bib.replace(entity, repl)
    # Parse BibTeX using the handy dandy bibtexparser module
    import bibtexparser
    from bibtexparser.bparser import BibTexParser
    from bibtexparser.customization import convert_to_unicode
    parser = BibTexParser()
    parser.customization = convert_to_unicode
    parsed = bibtexparser.loads(bib, parser=parser).entries[0]
    # Miscellaneous clean up
    braces = re.compile(r'\{([A-z_ \-]+|[\u0020-\uD7FF])\}', re.U)
    for key, val in parsed.items():
        val = braces.sub(r'\1', val)
        if '{' in val:
            raise Exception('Unhandled LaTeX: {}'.format(val.encode('cp1252')))
        parsed[key] = val
    parsed['pages'] = parsed.get('pages', '').replace('--', '-')
    if parsed.get('publisher', '').endswith(')'):
        parsed['publisher'] = parsed['publisher'].rsplit('(', 1)[0].rstrip()
    #pp.pprint(parsed)
    return parsed


def parse_authors(author_string, parse_names=True):
    """Parse a list of authors into components used by EMu

    Args:
        author_string (str): a string with one or more authors
        parse (bool): if True, parse names into components

    Returns:
        A list of the parsed authors
    """
    authors = re.split(r',| & | and ', author_string)
    parsed = []
    for author in authors:
        author = author.replace('.', '. ').replace('  ', ' ')
        if parse_names:
            fn = HumanName(author)
            parsed.append(clone({
                'NamTitle': fn.title,
                'NamFirst': fn.first,
                'NamMiddle': fn.middle,
                'NamLast': fn.last,
                'NamSuffix': fn.suffix,
                'SecRecordStatus': 'Unlisted'
            }))
        else:
            parsed.append(author)
    return parsed


def emuize(data):
    """Convert a BibTex record into an EMu record

    Args:
        data (dict): a parsed BibTeXt record

    Returns:
        A DeepDict object formatted for EMu
    """
    rec = clone()
    kind = data.pop('ENTRYTYPE')
    try:
        prefix = PUB_TYPES[kind]
    except KeyError:
        pp.pprint(data)
        raise Exception('Unrecognized publication type: {}'.format(kind))
    # Authors
    try:
        authors = parse_authors(data.pop('author'))
    except KeyError:
        pass
    else:
        # Special handling for authors of theses/dissertations
        if prefix == 'The':
            rec[prefix + 'AuthorsRef'] = authors[0]
        else:
            rec[prefix + 'AuthorsRef_tab'] = authors
            rec[prefix + 'Role_tab'] = ['Author'] * len(authors)
    # Editors
    try:
        editors = parse_authors(data.pop('editor'))
    except KeyError:
        pass
    else:
        rec[prefix + 'AuthorsRef_tab'] = editors
        rec[prefix + 'Role_tab'] = ['Editor'] * len(editors)
    # Article title
    try:
        rec[prefix + 'Title'] = data.pop('title')
    except KeyError:
        rec[prefix + 'Title'] = '[MISSING TITLE]'
    # Periodical information
    try:
        rec[prefix + 'Volume'] = data.pop('volume')
    except KeyError:
        pass
    try:
        rec[prefix + 'Issue'] = data.pop('number')
    except KeyError:
        pass
    try:
        pages = data.pop('pages')
    except KeyError:
        pass
    else:
        pages = '-'.join([s for s in pages.split('-') if s])
        rec[prefix + 'Pages'] = pages
        rec[prefix + 'IssuePages'] = pages
    # Publication date
    century = None
    try:
        year = data.pop('year')
    except KeyError:
        year = u''
    else:
        # HACK: Part 1 of fix for dates before 1900
        if int(year[:2]) < 19:
            century = year[:2]
            year = '19' + year[2:]
    try:
        month = data.pop('month')
    except KeyError:
        month = u''
    date = parse(' '.join([month, year]))
    if date is not None:
        if month:
            nominal_date = actual_date = date.strftime('%b %Y')
            #actual_date = date.strftime('%m-%Y')
        else:
            nominal_date = actual_date = year
        # HACK: Part 2 of fix for dates before 1900
        if century is not None:
            nominal_date = nominal_date.replace('19', century, 1)
            actual_date = actual_date.replace('19', century, 1)
        rec[prefix + 'PublicationDates'] = nominal_date
        rec[prefix + 'PublicationDate'] = actual_date
    # DOI
    try:
        doi = clean_doi(data.pop('doi'))
    except KeyError:
        pass
    else:
        rec['AdmGUIDValue_tab'] = [doi]
        rec['AdmGUIDType_tab'] = ['DOI']
    # Source
    parent = clone()
    for source in ('Book', 'Journal'):
        try:
            source_title = data.pop(SOURCES[source])
        except KeyError:
            pass
        else:
            source_kind = source[:3]
            parent['BibRecordType'] = source
            parent[source_kind + 'Title'] = source_title
            try:
                publisher = data.pop('publisher')
            except KeyError:
                pass
            else:
                parent[source_kind + 'PublishedByRef'] = clone({
                    'NamPartyType' : 'Organization',
                    'NamInstitution': '',
                    'NamOrganisation' : publisher
                })
            rec[prefix + 'ParentRef'] = parent.expand()
            break
    else:
        pp.pprint(data)
        raise Exception('Unrecognized parent publication')
    # Notes
    try:
        url = data.pop('url')
    except KeyError:
        pass
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        rec['NotNotes'] = u'Data retrieved from {} on {}'.format(url, today)
    # Fields we're not interested in at present
    data.pop('link', None)
    # Multimedia
    fp = os.path.abspath(os.path.join('files', data.pop('ID') + '.pdf'))
    try:
        open(fp, 'rb')
    except IOError:
        pass
    else:
        multimedia = clone({
            'Multimedia': fp,
            'MulTitle': rec[prefix + 'Title'],
            'MulCreator_tab': ['Adam Mansr'],#fullnames,
            'DetResourceType': u'Publication/Manuscript',
            'DetCollectionName_tab': ['Documents and data (Mineral Sciences)'],
            'DetPublisher': publisher,
            'AdmPublishWebNoPassword': 'No',
            'AdmPublishWebPassword': 'No',
            'AdmGUIDType_tab': rec['AdmGUIDType_tab'],
            'AdmGUIDValue_tab': rec['AdmGUIDValue_tab']
        })
        rec['MulMultiMediaRef_tab'] = [multimedia.expand()]
    rec.expand()
    # Look for keys that haven't been cross-walked to EMu schema
    if data:
        pp.pprint(data)
        raise Exception('Unhandled keys: {}'.format(sorted(data.keys())))
    #rec.pprint()
    return rec


def clone(*args):
    """Creates new record with key attributes copied from global scope"""
    container = BiblioRecord(*args)
    container.fields = FIELDS
    container.module = MODULE
    return container


def clean_doi(doi):
    prefix = '10.'
    if not doi.startswith(prefix):
        print('WARNING: DOI looks funny: {}'.format(doi))
        doi = '{}{}'.format(prefix, doi.split(prefix)[0])
    return doi


def process_file(fp):
    """Create an EMu import file from a list of DOIs

    Args:
        fp (str): the path to the list of DOIs
    """
    records = []
    updated = []
    rename = []
    with io.open(fp, 'r', encoding='utf16') as f:
        rows = csv.DictReader(f, delimiter=',', quotechar='"')
        for ref in rows:
            bib = parse_bibtex(doi2bib(ref['DOI']))
            rec = emuize(bib.copy())
            if rec is not None:
                records.append(rec)
                # Update filename to match the id from the BibTeX record
                fn = ref['Filename']
                if fn:
                    ext = os.path.splitext(fn)[1]
                    ref['Filename'] = bib['ID'] + ext
                    src = os.path.join('files', fn)
                    dst = os.path.join('files', ref['Filename'])
                    if src != dst:
                        rename.append((src, dst))
            updated.append(ref)
    for src, dst in rename:
        os.rename(src, dst)
    write('import.xml', records, 'ebibliography')
    # Update the DOI file
    keys = ['DOI', 'Filename', 'IRN']
    with open('doi.txt', 'w') as f:
        writer = csv.writer(f, delimiter=',', quotechar='"')
        writer.writerow([s.encode('utf-8') for s in keys])
        for ref in updated:
            writer.writerow([ref[key].encode('utf-8') for key in keys])
    # Re-encode the DOI file to UTF-16-LE
    with open('doi.txt', 'r') as f:
        data = f.read().decode('utf-8')
    with io.open('doi.txt', 'w', encoding='utf-16', newline='\n') as f:
        f.write(data)
