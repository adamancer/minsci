import re
from itertools import chain

from ....helpers import parse_names
from ....xmu import XMu, BiblioRecord, MinSciRecord


RIS_TYPES = {
    'JOUR': 'Article',
    'RPRT': 'Article'
}

USGS = {
    'Annual Report': 'U. S. Annual Report',
    'Bulletin': 'U. S. Geological Survey Bulletin',
    'Monograph': 'U. S. Geological Survey Monograph',
    'Professional Paper': 'U. S. Geological Survey Professional Paper'
}

LISTS = ['AU', 'A2', 'A3', 'A4', 'ED']


class FillFromRIS(XMu):
    """Fill out skeleton bibliography records that have DOIs"""

    def __init__(self, *args, **kwargs):
        super(FillFromRIS, self).__init__(*args, **kwargs)
        self.records = []


    def iterate(self, element):
        """Pulls reference information from BibTex based on DOI in EMu record"""
        rec = self.parse(element)
        ris = rec('NotNotes')
        if 'TY' in ris:
            irn = rec('irn')
            formatted = emuize(ris)
            if len(formatted) == 1:
                for rec in formatted:
                    rec['irn'] = irn
                    del rec['NotNotes']
                self.records.extend(formatted)




def ris2emu(fp):
    bib = FillFromRIS(fp, container=MinSciRecord)
    bib.fast_iter(report=5)
    return bib.records


def emuize(ris, customizer=None):
    records = []
    rec = []
    pattern = re.compile(ur'[A-Z][A-Z0-9] -')
    for line in ris.split('\n'):
        line = line.strip().decode('utf-8')
        if pattern.match(line):
            rec.append(line)
            if line.startswith('ER'):
                records.append(rec)
                rec = []
    bibs = []
    for ris in records:
        rec = ris2dict(ris)
        customizer = usgs
        if customizer is not None:
            rec = customizer(rec)
        # Create a bibliography record
        bib = {}
        bib['BibRecordType'] = RIS_TYPES[rec.pop('TY')]
        bib['{}PublicationLanguage'] = rec.pop('LA', None)
        bib['{}Title'] = rec.pop('TI')
        bib['{}Volume'] = rec.pop('VL', None)
        bib['{}Issue'] = rec.pop('IS', None)
        bib['{}Pages'] = rec.pop('SP', None)
        bib['{}ParentRef'] = {
            'BibRecordType': 'Journal',
            'JouTitle': rec.pop('T2')
            }
        # Contributors
        contributors = rec.pop('AU', [])
        blank =  {'NamPartyType': 'Person'}
        parties = [p for p in contributors if p.name != blank]
        if len(parties) != len(contributors):
            bib['{}AuthorsEtAl'] = 'Yes'
        bib['{}AuthorsRef_tab'] = [p.name for p in parties]
        bib['{}Role_tab'] = [p.role for p in parties]
        # Publication date
        pub_date = rec.pop('PY', None)
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
        # Apply prefix
        prefix = bib['BibRecordType'][:3]
        bib = {key.format(prefix): val for key, val in bib.iteritems() if val}
        bibs.append(BiblioRecord(bib).expand())
        if rec:
            print rec.keys()
    return bibs


def ris2dict(ris):
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


def usgs(ris):
    # Remove keys containing info we don't want/need
    keys = ['A3', 'CY', 'DB', 'ET', 'M3', 'UR']
    for key in keys:
        ris.pop(key, None)
    ris['T2'] = USGS.get(ris['T2'], ris['T2'])
    if ris.get('SN') and ris.get('TY') == 'RPRT':
        if ris.get('VL'):
            raise ValueError('Both VL and SN populated for USGS report')
        ris['VL'] = ris.pop('SN')
    # Handle contributors
    from collections import namedtuple
    Contributor = namedtuple('Contributor', ['name', 'role'])
    roles = {
        'AU': u'Author',
        'A1': u'First author',
        'A2': u'Secondary author',
        'A3': u'Tertiary author',
        'A4': u'Subsidiary author',
        'ED': u'Editor'
    }
    def keep(name):
        name = name.lower()
        for key in ('govt', 'government', 'survey'):
            if key in name:
                return False
        return True
    for key in ('AU', 'ED'):
        parties = ris.pop(key, [])
        if not isinstance(parties, list):
            parties = []
        parties = [parse_names(name, True) for name in parties if keep(name)]
        if parties:
            contributors = [Contributor(name, roles[key]) for name in chain(*parties)]
            ris.setdefault('AU', []).extend(contributors)
    return ris
