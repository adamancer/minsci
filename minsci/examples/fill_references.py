"""Fills references based on DOI or RIS data stored in a bibliography record

Checks two fields for data:
+ Checks for DOI in AdmGUIDValue_tab with AdmGUIDType_tab=DOI
+ Checks for RIS data in NotNotes

If the record already contains information, the script checks the author and
year to verify that the publication is correct. Be careful when overwriting
existing records!
"""
from __future__ import print_function
from __future__ import unicode_literals

import glob
import os
import re

from minsci import xmu
from minsci.xmu.tools.biblio.bibcheck import BibCheck, compare_citations
from minsci.xmu.tools.biblio.doi import doi2emu
from minsci.xmu.tools.biblio.ris import ris2emu


def usgs(ris):
    """Parses RIS records from the USGS"""
    full_titles = {
        'Annual Report': 'U. S. Geological Survey Annual Report',
        'Bulletin': 'U. S. Geological Survey Bulletin',
        'Monograph': 'U. S. Geological Survey Monograph',
        'Professional Paper': 'U. S. Geological Survey Professional Paper'
    }
    # Remove keys containing info we don't want/need
    keys = ['A3', 'CY', 'DB', 'ET', 'M3', 'N1', 'SN', 'UR']
    for key in keys:
        ris.pop(key, None)
    ris['T2'] = full_titles.get(ris['T2'], ris['T2'])
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


def hathi(ris):
    """Parses RIS records from the Hathi Trust"""
    keys = ['ID', 'KW', 'M1', 'N1', 'TP', 'UR']
    for key in keys:
        ris.pop(key, None)
    # Check for countries in author list
    if ris['AU'][-1].endswith('.'):
        ris['AU'].pop()
    return ris


# Define custom RIS parsers
parsers = {
    # Custom parsers used to handle data from certain publishers
    'catalog.hathitrust.org': hathi,
    'pubs.er.usgs.gov': usgs,
     # Generic parsers strip unneeded keys
    'books.google.com': ['N1', 'UR'],
    'canmin.org': ['JO', 'N1', 'N2', 'UR'],
    'geoscienceworld.org': ['N1', 'N2', 'UR'],
    'jstor.org': ['AB', 'C1', 'N1', 'PB', 'SN', 'UR'],
    'ncbi.nlm.nih.gov/pmc': ['N1', 'UR']
}

# Get existing data
fp = os.path.join('reports', 'ebibliography.xml')
bibcheck = BibCheck(fp, container=xmu.BiblioRecord)
bibcheck.fast_iter()

# Get data from DOI stored in GUID table
print('Populating references...')
doi = doi2emu(fp)
ris = ris2emu(fp, parsers=parsers)

# Compare IRNs from both methods to ensure there are no record was run twice
doi_irns = set([rec('irn') for rec in doi])
ris_irns = set([rec('irn') for rec in ris])
dupes = doi_irns & ris_irns
if dupes:
    raise ValueError('Duplicates IRNs found: {}'.format(dupes))

# Some records contain
verified = []
for rec in doi + ris:
    rec.fields = xmu.FIELDS
    authors = bibcheck.get_authors(rec)
    pub_date = bibcheck.get_pub_date(rec)
    existing = bibcheck.records[rec('irn')]
    if compare_citations(authors, pub_date, existing):
        verified.append(rec)

print('{:,}/{:,} records verified!'.format(len(verified), len(doi + ris)))
xmu.write('update.xml', verified, 'ebibliography')