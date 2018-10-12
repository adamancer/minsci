"""Tools to parse legacy data from an EMu export"""
from __future__ import print_function
from __future__ import unicode_literals

import csv
import os
import re
from collections import namedtuple
from pprint import pprint

from ..xmu import XMu
from ..containers import MediaRecord
from .groups import write_group


class Legacy(XMu):
    """Methods to parse legacy data from an EMu export"""

    def __init__(self, *args, **kwargs):
        super(Legacy, self).__init__(*args, **kwargs)
        self.function_lookup = {
            'AAAAAAAA': skip,
            'ACCESSION_': skip,
            'ACCESSION NO.': skip,
            'AL2O3': verify_analysis,
            'ANALYST': verify_analysis,
            'ANALYTICAL_KEYWORDS': verify_analysis,
            'ANALYTICAL2': verify_analysis,
            'ASSOCIATED': skip,
            'ASSOCIATED ROCK(S)': skip,
            'AUTHOR': skip,
            'AUTHOR_2': skip,
            'BAO': verify_analysis,
            'C': verify_analysis,
            'CAO': verify_analysis,
            'CASE': skip,
            'CATALOG_NO': skip,
            'CATALOG_NU': skip,
            'CATALOG_SU': skip,
            'CHEMICAL_M': skip,           # chemical modifier of taxon
            'CITY_TOWN': verify_event,
            'CITY/TOWN/TOWNSHIP': verify_event,
            'CL': verify_analysis,
            'CO': verify_analysis,
            'COLKEYCOLLECTION': skip,
            'COLLECTIO0': skip,
            'COLLECTION': skip,
            'COLLECTOR NUMBER': skip,
            'CO2': verify_analysis,
            'COMMODITY/METAL': skip,
            'CONTINENT': verify_event,
            'CONTINENT/COUNTRY/U.S. ST': verify_country,
            'COUNTRY': verify_country,
            'COUNTRY_MO': verify_country,
            'COUNTY/DISTRICT': verify_country,
            'CR2O3': verify_analysis,
            'DATE COLLECTED': verify_event,
            'DEPTH__OFF': verify_event,
            'DEPTH__ON_': verify_event,
            'DESCRIBED': skip,
            'DISTRICT_C': verify_event,           # district/county
            'DIMENSIONS': skip,
            'DONOR': skip,
            'DRAWER': skip,
            'E_W(OFF_BOTTOM)': verify_event,
            'E_W(ON_BOTTOM)': verify_event,
            'E/I': skip,
            'ELEVATION': verify_event,
            'ERUPTION DATE': skip,
            'F': verify_analysis,
            'FE2O3': verify_analysis,
            'FEO': verify_analysis,
            'FES': verify_analysis,
            'FIGURED': skip,
            'FLOW/TEPHRA DATE': skip,
            'GEOGRAPHICAL LOCATION': verify_event,
            'GEOLOGIC FORMATION': verify_event,
            'GEOLOGIC SETTING': verify_event,
            'H2O_': verify_analysis,
            'H2O__TOTAL': verify_analysis,
            'H2O_0': verify_analysis,
            'INV.PAST_LOANS': skip,
            'ISLAND': verify_event,
            'ISLAND_GRO': verify_event,
            'JOURNAL': skip,
            'JOURNAL_2': skip,
            'KEY': skip,
            'LATD(OFF_BOTTOM)': verify_event,
            'LATM(OFF_BOTTOM)': verify_event,
            'LATS(OFF_BOTTOM)': verify_event,
            'LATD(ON_BOTTOM)': verify_event,
            'LATM(ON_BOTTOM)': verify_event,
            'LATS(ON_BOTTOM)': verify_event,
            'LAVA SOURCE': skip,
            'LI2O': verify_analysis,
            'LOCALITY SORT KEY': verify_event,
            'LONGD(OFF_BOTTOM)': verify_event,
            'LONGM(OFF_BOTTOM)': verify_event,
            'LONGS(OFF_BOTTOM)': verify_event,
            'LONGD_ON_B': verify_event,
            'LONGM_ON_B': verify_event,
            'LONGS_ON_B': verify_event,
            'LOSS_ON_IG': skip,
            'MAJOR ISLAND GROUP': verify_event,
            'MICROPROBE': skip,
            'MINE_NAME': verify_mine,
            'MINE_SPECI': skip,
            'MINE/QUARRY': verify_mine,
            'MINERAL_NA': verify_taxon,
            'MINERAL_N1': skip,
            'MINERAL_PETROGRAPHY': skip,
            'MINING DISTRICT': verify_mine,
            'MISSING/ON LOAN': skip,
            'MGO': verify_analysis,
            'MNO': verify_analysis,
            'MODIFIER OF SPECIFIC LOCA': verify_event,
            'MSC LOCATION/FUMIGATION D': skip,
            'NA2O': verify_analysis,
            'NEAREST_NA': verify_event,   # nearest named feature
            'NIO': verify_analysis,
            'N_S_ON_BOT': verify_event,
            'N_S(OFF_BOTTOM)': verify_event,
            'NUMBER_MOD': skip,          # specimen count modifier
            'NUMBER_OF_': skip,
            'OCEAN': verify_ocean,
            'OCEAN/SEA': verify_ocean,
            'PETROGRAPHIC SECTIONS': skip,
            'PUBLICATIO': skip,
            'QUADRANGLE': verify_event,
            'QUANTITY': skip,
            'QUESTIONABLE IDENTIFICATI': skip,
            'REMARKS': skip,
            'R_TYPE': skip,               # object type?
            'S': verify_analysis,
            'SIO2': verify_analysis,
            'SPECIFIC_L': verify_event,    # locality
            'SPECIAL_GE': skip,           # special geo(logy? graphy?)
            'SPECIMEN NAME': skip,        # taxonomic info
            'SPECIMEN_T': skip,           # object type?
            'SO3': verify_analysis,
            'SRO': verify_analysis,
            'STATE_MODI': verify_state,
            'STATE_PROV': verify_state,
            'STATE/PROVINCE': verify_state,
            'STATUS': skip,
            'STORAGE_ID': skip,
            'STRATIGRAPHIC AGE': skip,
            'SUBREGION': verify_event,     # GVP subregion
            'SYNONYMS_V': skip,           # what is the V?
            'SYNTHETIC': skip,
            'TEXTURE_STRUCTURE': skip,
            'TOTAL': verify_analysis,
            'TIO2': verify_analysis,
            'TYPE': skip,
            'USNM#': skip,
            'V2O3': verify_analysis,
            'VNUM': verify_volcano,        # GVP legacy number
            'VOLCANO_NA': verify_volcano,
            'VOLC_NAME': verify_volcano,
            'VOLCANIC GLASS (VG) NUMBE': verify_volcano,
            'VOLCANO NAME': verify_volcano,
            'VOLCANO NUMBER AND SUBREG': verify_volcano,
            'WEIGHT': skip,
            'X_RAYED': skip,
            'YEAR_ACQUI': skip,
            'YEAR_PUBLI': skip,
            'YEAR_PUBLI2': skip,
            'ZRO2': verify_analysis,
            'Accession number': skip,
            'Age': skip,
            'Al2O3': verify_analysis,
            'Associated gems': skip,
            'Associated minerals': skip,
            'Catalog Number': skip,
            'CaO': verify_analysis,
            'Chemical modifier': skip,
            'Coll_Key_ID': skip,
            'Collection': skip,
            'Collection Type': skip,
            'Collection_ID': skip,
            'CollectionID': skip,
            'Color': skip,
            'Country': verify_country,
            'Comments': skip,
            'Condition': skip,
            'Country_Code': verify_country,
            'Cruise': verify_event,
            'Current Wt. (g)': skip,
            'CutRemarks': skip,
            'Date Out': skip,
            'Date out on Loan': skip,
            'Date Due': skip,
            'Depth': verify_event,
            'DescribedBy': skip,
            'DescribedDate': skip,
            'DescribedIn': skip,
            'Description': skip,
            'Discription': skip,
            'Dimensions': skip,
            'Dimensions in cm': skip,
            'Donor': skip,
            'DonorID': skip,
            'Dredge': verify_event,
            'Fashion/Cut': skip,
            'FeO*': verify_analysis,
            'Identifier': skip,
            'In/Out': skip,               # loan status
            'InventoryStat': skip,
            'Group # code': skip,
            'Jewelry type': skip,
            'K2O': verify_analysis,
            'Keywords': skip,
            'Latitude': verify_event,
            'Loan': skip,
            'Locality': verify_event,
            'Location': skip,             # storage location
            'Location_1': skip,           # storage location
            'Location_2': skip,
            'Location_3': skip,
            'Location_4': skip,
            'Longitude': verify_event,
            'LotDescription': skip,
            'Maker': skip,
            'MajorIsID': verify_event,     # island group ID
            'Mine name': verify_mine,
            'MgO': verify_analysis,
            'MnO': verify_analysis,
            'Na2O': verify_analysis,
            'Name': skip,                 # object name
            'Number modifier': skip,
            'Not Migrated - OldRemarks': skip,
            'ObjectOrImage': skip,
            'Ocean': verify_ocean,
            'OceanSeaID': verify_ocean,
            'On Loan': skip,
            'On Loan to': skip,
            'Origional Wt. (g)': skip,
            'OthNumSource': skip,
            'OthNumSource2': skip,
            'OthNumValue': skip,
            'OthNumValue2': skip,
            'P2O5': verify_analysis,
            'Past Loan': skip,
            'Provenance': verify_event,
            'Publication/Figured': skip,
            'Range': skip,
            'Record_No': skip,           # meteorite record number
            'Reference': skip,
            'RefractInd': skip,
            'Remarks': skip,
            'Sample': skip,
            'Samples Distributed A': skip,
            'Samples Distributed (g)': skip,
            'Sampling method': skip,
            'Ship/Dredge': verify_event,
            'ShipName': verify_event,
            'SiO2': verify_analysis,
            'Split': skip,
            'State': verify_state,
            'State_Code': verify_state,
            'Station': verify_event,
            'Special or 1/2': skip,       # for thin sections
            'Species Name': skip,
            'Species_Name_Code': skip,
            'Specific locality': verify_event,
            'Specimens': skip,
            'SpecimenTypeID': skip,
            'Status': skip,
            'Suffix': skip,
            'Sum': skip,
            'Synonym': skip,              # meteorite!
            'Synonyms': skip,
            'Synthetic': skip,
            'Tectonic code': verify_event,
            'TiO2': verify_analysis,
            'Total Wt. (g)': skip,
            'VG Disk #': skip,
            'VG no#': skip,
            'Weight': skip,
            'WeightRemarks': skip,
            'XRayed': skip,
            'Year': skip                  # year of expedition
        }
        # FIXME: What the hell is this?
        self.field_lookup = {}
        for field, func in self.function_lookup.iteritems():
            self.field_lookup.setdefault(func.__name__, []).append(field)
            if func.__name__ in ('verify_country',
                                 'verify_mine',
                                 'verify_ocean',
                                 'verify_state',
                                 'verify_volcano'):
                self.field_lookup.setdefault('verify_event', []).append(field)
        skipped = []
        for field, func in self.function_lookup.iteritems():
            if func == skip:
                skipped.append(field)
        if skipped:
            print('\n'.join(sorted(skipped)))
            raw_input()
        self.missing = []
        # Read legacy data automatically
        self.errors = []
        self.groups = {}
        self.fast_iter(report=10000)


    def iterate(self, element):
        """Compares current and legacy data"""
        rec = self.parse(element)
        irn = rec('irn')
        legacy = rec('AdmOriginalDataRef', 'AdmOriginalData')
        lines = [re.split('[=:]', line, 1) for line in legacy.splitlines()]
        orig = {key.strip(): standardize(val) for key, val in lines}
        missing = []
        for key, val in orig.iteritems():
            # Check data in all fields
            try:
                func = self.function_lookup[key]
            except KeyError:
                missing.append(': '.join([key, val]))
            else:
                fields = self.field_lookup[func.__name__]
                r = func(rec, {field: orig.get(field) for field in fields
                               if orig.get(field) is not None})
                if r is not None and r.result is False:
                    self.groups.setdefault(func.__name__, []).append(irn)
                    self.errors.append([irn, func.__name__,
                                        r.emu_value, r.orig_value])
        # Kill iteration if any fields are missing from the function lookup
        if missing:
            print('\n'.join(sorted(missing)))
            return False


    def group(self):
        """Create group of problematic records"""
        dn = 'errors'
        try:
            for fn in os.listdir(dn):
                os.remove(os.path.join(dn, fn))
        except IOError:
            os.mkdir(dn)
        mask = os.path.join(dn, '{}')
        for name in self.groups:
            write_group('ecatalogue', self.groups[name],
                        fp=mask.format(name + '.xml'), name=name)
        if self.errors:
            with open(mask.format('results.log'), 'wb') as f:
                writer = csv.writer(f)
                writer.writerow(['irn', 'check', 'emu value', 'orig value'])
                [writer.writerow(row) for row in self.errors]



Result = namedtuple('Result', ['result', 'emu_value', 'orig_value'])

def standardize(val):
    """Normalize a string to improve comparisons"""
    return val.strip().upper()


def skip(rec, *args, **kwargs):
    """Placeholder function for fields that have not been mapped"""
    return


def verify_event(rec, orig):
    """Verifies collection event against legacy data"""
    pass


def verify_analysis(rec, orig):
    """Verifies chemical analysis against legacy data"""
    pass


def verify_country(rec, orig):
    """Verifies country against legacy data"""
    pass


def verify_mine(rec, orig):
    """Verifies mine name against legacy data"""
    pass


def verify_ocean(rec, orig):
    """Verifies ocean against legacy data"""
    pass


def verify_state(rec, orig):
    """Verifies state/province against legacy data"""
    pass


def verify_taxon(rec, orig):
    """Verifies classification against legacy data"""
    pass


def verify_volcano(rec, orig):
    """Verifies volcano name against legacy data"""
    pass


def create_receipt(fp, contents, creator, module, rec_id=None, title=None):
    """Creates a receipt for a record

    Args:
        fp (str): the path to the receipt file
        contents (list): a list of the form ['# File metadata', 'key: val', ...]
        creator (str): the name of the cataloger/record creator
        module (str): the name of the module
        rec_id (str): the identifier of the record (usually a catalog number
            or irn)
        title (str): the title of the multimedia resource

    """
    assert rec_id is not None or title is not None
    if title is None:
        # If the rec_id is an irn, include the module
        if rec_id.isdigit() and 7 <= len(str(rec_id)) <= 8:
            rec_id = '{} record {}'.format(module, rec_id)
        title = 'Verbatim data for {}'.format(rec_id)
    # Write receipt file
    with open(fp, 'wb') as f:
        f.write('\n'.join([line.encode('utf-8') for line in contents]))
    # Write and return EMu record
    return MediaRecord({
        'Multimedia': os.path.abspath(fp),
        'MulCreator_tab': [creator],
        'MulTitle': title,
        'MulDescription': contents[0].strip('# '),
        'DetResourceType': 'Documentation',
        'DetCollectionName_tab': ['Documents and data (Mineral Sciences)'],
        'DetRights': 'Internal use only',
        'DetSubject_tab': ['Verbatim data', module],
        'DetSource': 'Mineral Sciences, NMNH',
        'NotNotes': '\n'.join(contents),
        'AdmPublishWebPassword': 'No',
        'AdmPublishWebNoPassword': 'No'
    }).expand()
