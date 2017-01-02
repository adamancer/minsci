import csv
import os
import re
from collections import namedtuple
from pprint import pprint

from ..xmu import XMu, write
from .groups import group


class Legacy(XMu):

    def __init__(self, *args, **kwargs):
        super(Legacy, self).__init__(*args, **kwargs)
        self.function_lookup = {
            'AAAAAAAA': skip,
            'ACCESSION_': skip,
            'ACCESSION NO.': skip,
            'AL2O3': check_analysis,
            'ANALYST': check_analysis,
            'ANALYTICAL_KEYWORDS': check_analysis,
            'ANALYTICAL2': check_analysis,
            'ASSOCIATED': skip,
            'ASSOCIATED ROCK(S)': skip,
            'AUTHOR': skip,
            'AUTHOR_2': skip,
            'BAO': check_analysis,
            'C': check_analysis,
            'CAO': check_analysis,
            'CASE': skip,
            'CATALOG_NO': skip,
            'CATALOG_NU': skip,
            'CATALOG_SU': skip,
            'CHEMICAL_M': skip,           # chemical modifier of taxon
            'CITY_TOWN': check_event,
            'CITY/TOWN/TOWNSHIP': check_event,
            'CL': check_analysis,
            'CO': check_analysis,
            'COLKEYCOLLECTION': skip,
            'COLLECTIO0': skip,
            'COLLECTION': skip,
            'COLLECTOR NUMBER': skip,
            'CO2': check_analysis,
            'COMMODITY/METAL': skip,
            'CONTINENT': check_event,
            'CONTINENT/COUNTRY/U.S. ST': check_country,
            'COUNTRY': check_country,
            'COUNTRY_MO': check_country,
            'COUNTY/DISTRICT': check_country,
            'CR2O3': check_analysis,
            'DATE COLLECTED': check_event,
            'DEPTH__OFF': check_event,
            'DEPTH__ON_': check_event,
            'DESCRIBED': skip,
            'DISTRICT_C': check_event,           # district/county
            'DIMENSIONS': skip,
            'DONOR': skip,
            'DRAWER': skip,
            'E_W(OFF_BOTTOM)': check_event,
            'E_W(ON_BOTTOM)': check_event,
            'E/I': skip,
            'ELEVATION': check_event,
            'ERUPTION DATE': skip,
            'F': check_analysis,
            'FE2O3': check_analysis,
            'FEO': check_analysis,
            'FES': check_analysis,
            'FIGURED': skip,
            'FLOW/TEPHRA DATE': skip,
            'GEOGRAPHICAL LOCATION': check_event,
            'GEOLOGIC FORMATION': check_event,
            'GEOLOGIC SETTING': check_event,
            'H2O_': check_analysis,
            'H2O__TOTAL': check_analysis,
            'H2O_0': check_analysis,
            'INV.PAST_LOANS': skip,
            'ISLAND': check_event,
            'ISLAND_GRO': check_event,
            'JOURNAL': skip,
            'JOURNAL_2': skip,
            'KEY': skip,
            'LATD(OFF_BOTTOM)': check_event,
            'LATM(OFF_BOTTOM)': check_event,
            'LATS(OFF_BOTTOM)': check_event,
            'LATD(ON_BOTTOM)': check_event,
            'LATM(ON_BOTTOM)': check_event,
            'LATS(ON_BOTTOM)': check_event,
            'LAVA SOURCE': skip,
            'LI2O': check_analysis,
            'LOCALITY SORT KEY': check_event,
            'LONGD(OFF_BOTTOM)': check_event,
            'LONGM(OFF_BOTTOM)': check_event,
            'LONGS(OFF_BOTTOM)': check_event,
            'LONGD_ON_B': check_event,
            'LONGM_ON_B': check_event,
            'LONGS_ON_B': check_event,
            'LOSS_ON_IG': skip,
            'MAJOR ISLAND GROUP': check_event,
            'MICROPROBE': skip,
            'MINE_NAME': check_mine,
            'MINE_SPECI': skip,
            'MINE/QUARRY': check_mine,
            'MINERAL_NA': check_taxon,
            'MINERAL_N1': skip,
            'MINERAL_PETROGRAPHY': skip,
            'MINING DISTRICT': check_mine,
            'MISSING/ON LOAN': skip,
            'MGO': check_analysis,
            'MNO': check_analysis,
            'MODIFIER OF SPECIFIC LOCA': check_event,
            'MSC LOCATION/FUMIGATION D': skip,
            'NA2O': check_analysis,
            'NEAREST_NA': check_event,   # nearest named feature
            'NIO': check_analysis,
            'N_S_ON_BOT': check_event,
            'N_S(OFF_BOTTOM)': check_event,
            'NUMBER_MOD': skip,          # specimen count modifier
            'NUMBER_OF_': skip,
            'OCEAN': check_ocean,
            'OCEAN/SEA': check_ocean,
            'PETROGRAPHIC SECTIONS': skip,
            'PUBLICATIO': skip,
            'QUADRANGLE': check_event,
            'QUANTITY': skip,
            'QUESTIONABLE IDENTIFICATI': skip,
            'REMARKS': skip,
            'R_TYPE': skip,               # object type?
            'S': check_analysis,
            'SIO2': check_analysis,
            'SPECIFIC_L': check_event,    # locality
            'SPECIAL_GE': skip,           # special geo(logy? graphy?)
            'SPECIMEN NAME': skip,        # taxonomic info
            'SPECIMEN_T': skip,           # object type?
            'SO3': check_analysis,
            'SRO': check_analysis,
            'STATE_MODI': check_state,
            'STATE_PROV': check_state,
            'STATE/PROVINCE': check_state,
            'STATUS': skip,
            'STORAGE_ID': skip,
            'STRATIGRAPHIC AGE': skip,
            'SUBREGION': check_event,     # GVP subregion
            'SYNONYMS_V': skip,           # what is the V?
            'SYNTHETIC': skip,
            'TEXTURE_STRUCTURE': skip,
            'TOTAL': check_analysis,
            'TIO2': check_analysis,
            'TYPE': skip,
            'USNM#': skip,
            'V2O3': check_analysis,
            'VNUM': check_volcano,        # GVP legacy number
            'VOLCANO_NA': check_volcano,
            'VOLC_NAME': check_volcano,
            'VOLCANIC GLASS (VG) NUMBE': check_volcano,
            'VOLCANO NAME': check_volcano,
            'VOLCANO NUMBER AND SUBREG': check_volcano,
            'WEIGHT': skip,
            'X_RAYED': skip,
            'YEAR_ACQUI': skip,
            'YEAR_PUBLI': skip,
            'YEAR_PUBLI2': skip,
            'ZRO2': check_analysis,
            'Accession number': skip,
            'Age': skip,
            'Al2O3': check_analysis,
            'Associated gems': skip,
            'Associated minerals': skip,
            'Catalog Number': skip,
            'CaO': check_analysis,
            'Chemical modifier': skip,
            'Coll_Key_ID': skip,
            'Collection': skip,
            'Collection Type': skip,
            'Collection_ID': skip,
            'CollectionID': skip,
            'Color': skip,
            'Country': check_country,
            'Comments': skip,
            'Condition': skip,
            'Country_Code': check_country,
            'Cruise': check_event,
            'Current Wt. (g)': skip,
            'CutRemarks': skip,
            'Date Out': skip,
            'Date out on Loan': skip,
            'Date Due': skip,
            'Depth': check_event,
            'DescribedBy': skip,
            'DescribedDate': skip,
            'DescribedIn': skip,
            'Description': skip,
            'Discription': skip,
            'Dimensions': skip,
            'Dimensions in cm': skip,
            'Donor': skip,
            'DonorID': skip,
            'Dredge': check_event,
            'Fashion/Cut': skip,
            'FeO*': check_analysis,
            'Identifier': skip,
            'In/Out': skip,               # loan status
            'InventoryStat': skip,
            'Group # code': skip,
            'Jewelry type': skip,
            'K2O': check_analysis,
            'Keywords': skip,
            'Latitude': check_event,
            'Loan': skip,
            'Locality': check_event,
            'Location': skip,             # storage location
            'Location_1': skip,           # storage location
            'Location_2': skip,
            'Location_3': skip,
            'Location_4': skip,
            'Longitude': check_event,
            'LotDescription': skip,
            'Maker': skip,
            'MajorIsID': check_event,     # island group ID
            'Mine name': check_mine,
            'MgO': check_analysis,
            'MnO': check_analysis,
            'Na2O': check_analysis,
            'Name': skip,                 # object name
            'Number modifier': skip,
            'Not Migrated - OldRemarks': skip,
            'ObjectOrImage': skip,
            'Ocean': check_ocean,
            'OceanSeaID': check_ocean,
            'On Loan': skip,
            'On Loan to': skip,
            'Origional Wt. (g)': skip,
            'OthNumSource': skip,
            'OthNumSource2': skip,
            'OthNumValue': skip,
            'OthNumValue2': skip,
            'P2O5': check_analysis,
            'Past Loan': skip,
            'Provenance': check_event,
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
            'Ship/Dredge': check_event,
            'ShipName': check_event,
            'SiO2': check_analysis,
            'Split': skip,
            'State': check_state,
            'State_Code': check_state,
            'Station': check_event,
            'Special or 1/2': skip,       # for thin sections
            'Species Name': skip,
            'Species_Name_Code': skip,
            'Specific locality': check_event,
            'Specimens': skip,
            'SpecimenTypeID': skip,
            'Status': skip,
            'Suffix': skip,
            'Sum': skip,
            'Synonym': skip,              # meteorite!
            'Synonyms': skip,
            'Synthetic': skip,
            'Tectonic code': check_event,
            'TiO2': check_analysis,
            'Total Wt. (g)': skip,
            'VG Disk #': skip,
            'VG no#': skip,
            'Weight': skip,
            'WeightRemarks': skip,
            'XRayed': skip,
            'Year': skip                  # year of expedition
        }
        self.field_lookup = {}
        for field, func in self.function_lookup.iteritems():
            self.field_lookup.setdefault(func.__name__, []).append(field)
            if func.__name__ in ('check_country',
                                 'check_mine',
                                 'check_ocean',
                                 'check_state',
                                 'check_volcano'):
                self.field_lookup.setdefault('check_event', []).append(field)
        skipped = []
        for field, func in self.function_lookup.iteritems():
            if func == skip:
                skipped.append(field)
        if skipped:
            print '\n'.join(sorted(skipped))
            raw_input()
        self.missing = []
        # Read legacy data automatically
        self.errors = []
        self.groups = {}
        self.fast_iter(report=10000)


    def iterate(self, element):
        """Default function called by self.fast_iter()"""
        return self.iterlegacy(element)


    def iterlegacy(self, element):
        """Compares current and legacy """
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
            print '\n'.join(sorted(missing))
            return False


    def group(self):
        """Create EMu import for egroups for problematic records"""
        dn = 'errors'
        try:
            for fn in os.listdir(dn):
                os.remove(os.path.join(dn, fn))
        except IOError:
            os.mkdir(dn)
        mask = os.path.join(dn, '{}')
        for name in self.groups:
            group('ecatalogue', self.groups[name],
                  fp=mask.format(name + '.xml'), name=name)
        if self.errors:
            with open(mask.format('results.log'), 'wb') as f:
                writer = csv.writer(f)
                writer.writerow(['irn', 'check', 'emu value', 'orig value'])
                [writer.writerow(row) for row in self.errors]



Result = namedtuple('Result', ['result', 'emu_value', 'orig_value'])

def standardize(s):
    return s.strip().upper()


def skip(rec, *args, **kwargs):
    return


def check_event(rec, orig):
    return
    if len(orig) == 1 and 'Locality' in orig and rec('LocPreciseLocation'):
        pprint(orig)
        rec.pprint(True)
    return


def check_analysis(rec, orig):
    return


def check_country(rec, orig):
    emu_value = standardize(rec('BioEventSiteRef', 'LocCountry'))
    try:
        orig_value = orig.values()[0]
    except IndexError:
        orig_value = None
    result = emu_value == orig_value
    # Exceptions
    exceptions = {
        'GERMANY, EAST': 'EAST GERMANY',
        'GERMANY, WEST': 'WEST GERMANY',
        'OCEAN': None,
        'UNKNOWN': None,
    }
    eq = exceptions.get(orig_value)
    if emu_value == eq or (eq is None and not emu_value):
        result = True
    return Result(result, emu_value, orig_value)


def check_mine(rec, orig):
    return
    emu_value = standardize(rec('BioEventSiteRef', 'LocMineName'))
    try:
        orig_value = orig.values()[0]
    except IndexError:
        orig_value = None
    result = emu_value == orig_value
    return Result(result, emu_value, orig_value)


def check_ocean(rec, orig):
    emu_key = rec('BioEventSiteRef', 'LocOcean')


def check_state(rec, orig):
    return


def check_taxon(rec, orig):
    emu_key = rec('IdeTaxonRef_tab', 'ClaSpecies')


def check_volcano(rec, orig):
    return
