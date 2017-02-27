# -*- coding: utf-8 -*-
"""Creates ebibliography records based on BibTex records pulled using DOI"""

import csv
import io
import os
import pprint as pp
import re
from datetime import datetime

import requests
from dateparser import parse
from nameparser import HumanName

from ....xmu import XMu, MinSciRecord, write, FIELDS


MODULE = 'ebibliography'

PREFIXES = {
    'article': 'Art',
    'book': 'Boo',
    'incollection': 'Art'
}

SOURCES = {
    'Book': 'booktitle',
    'Journal': 'journal'
}

# List of entities from BibTex
ENTITIES = {
    r'$\mathsemicolon$': ';',
    r'{\{AE}}': u'Æ',
    r'({IUCr})': '(IUCr)'
}


class FillFromDOI(XMu):
    """Fill out skeleton bibliography records that have DOIs"""

    def __init__(self, *args, **kwargs):
        super(FillFromDOI, self).__init__(*args, **kwargs)
        self.records = []


    def iterate(self, element):
        """Pulls reference information from BibTex based on DOI in EMu record"""
        rec = self.parse(element)
        doi = rec.get_guid('DOI')
        if doi:
            bibtex = doi2bib(doi)
            if bibtex is not None:
                formatted = emuize(parse_bibtex(bibtex))
                formatted['irn'] = rec('irn')
                # Remove DOIs, since these already exist in the source
                # record and the existing values are more likely to be
                # cased properly
                del formatted['AdmGUIDType_tab']
                del formatted['AdmGUIDValue_tab']
                formatted['NotNotes'] = bibtex
                self.records.append(formatted)


def doi2emu(fp):
    bib = FillFromDOI(fp, container=MinSciRecord)
    bib.fast_iter(report=5)
    return bib.records


def doi2bib(doi):
    """Returns a bibTeX string of metadata for a given DOI.

    Source: https://gist.github.com/jrsmith3/5513926

    Args:
        doi (str): a valid DOI corresponding to a publication

    Returns:
        BibTex record as a string
    """
    url = 'http://dx.doi.org/' + doi
    headers = {'accept': 'application/x-bibtex'}
    response = requests.get(url, headers=headers)
    if response.text.startswith('@'):
        return response.text
    return None


def parse_bibtex(bib):
    """Parses the BibTex returned by the DOI resolver

    Args:
        bib (str): a BibTex record

    Returns:
        Dict containing reference data
    """
    for entity, repl in ENTITIES.iteritems():
        bib = bib.replace(entity, repl)
    # Parse BibTex using the handy dandy bibtexparser module
    import bibtexparser
    from bibtexparser.bparser import BibTexParser
    from bibtexparser.customization import convert_to_unicode
    parser = BibTexParser()
    parser.customization = convert_to_unicode
    parsed = bibtexparser.loads(bib, parser=parser).entries[0]
    # Miscellaneous clean up
    braces = re.compile(u'\{([A-Z_ \-]+|[\u0020-\uD7FF])\}', re.U)
    for key, val in parsed.iteritems():
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
    authors = re.split(',| & | and ', author_string)
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
            }))
        else:
            parsed.append(author)
    return parsed


def emuize(data):
    """Convert a BibText record into an EMu record

    Args:
        data (dict): a parsed BibText record

    Returns:
        A DeepDict object formatted for EMu
    """
    rec = clone()
    kind = data.pop('ENTRYTYPE')
    try:
        prefix = PREFIXES[kind]
    except KeyError:
        pp.pprint(data)
        raise Exception('Unrecognized publication type: {}'.format(kind))
    # Authors
    try:
        authors = parse_authors(data.pop('author'))
    except KeyError:
        pass
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
        rec['AdmGUIDValue_tab'] = [data.pop('doi')]
    except KeyError:
        pass
    else:
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
            'MulCreator_tab': ['Adam Mansur'],#fullnames,
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
    """Creates new MinSciRecord with key attributes copied from global scope"""
    container = MinSciRecord(*args)
    container.fields = FIELDS
    container.module = MODULE
    return container


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
                # Update filename to match the id from the BibTex record
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
    with open('doi.txt', 'wb') as f:
        writer = csv.writer(f, delimiter=',', quotechar='"')
        writer.writerow([s.encode('utf-8') for s in keys])
        for ref in updated:
            writer.writerow([ref[key].encode('utf-8') for key in keys])
    # Re-encode the DOI file to UTF-16-LE
    with open('doi.txt', 'rb') as f:
        data = f.read().decode('utf-8')
    with io.open('doi.txt', 'w', encoding='utf-16', newline='\n') as f:
        f.write(data)
