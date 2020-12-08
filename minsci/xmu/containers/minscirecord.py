"""Subclass of XMuRecord with methods specific to Mineral Sciences"""
import re
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

from nmnh_ms_tools.records import get_catnum
from nmnh_ms_tools.utils import oxford_comma

from .xmurecord import XMuRecord
from ..tools.describer import get_caption, summarize




class MinSciRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to Mineral Sciences"""
    geotree = None
    antmet = re.compile(r'([A-Z]{3} |[A-Z]{4})[0-9]{5,6}(,[A-z0-9]+)?')


    def __init__(self, *args):
        super(MinSciRecord, self).__init__(*args)
        self.module = 'ecatalogue'


    def get_name(self, taxa=None, force_derived=False):
        """Derives object name based on record

        Args:
            taxa (list): list of taxa. Determined automatically if omitted.

        Returns:
            String with object name
        """
        keys = ['MinName', 'MetMeteoriteName'] if not force_derived else []
        for key in keys:
            name = self(key)
            if name:
                break
        else:
            if taxa is None:
                taxa = self.get_classification(True)
            name = self.geotree.name_item(taxa, self('MinJeweleryType'))
        return name


    def get_classification_string(self, taxa=None, allow_varieties=False):
        if taxa is None:
            taxa = self.get_classification(True)
        return self.geotree.name_item(taxa, allow_varieties=allow_varieties)


    def get_classification(self, standardized=True):
        """Gets classification of object based on record

        Args:
            standardized (bool): if True, use GeoTaxa to try to group and
                standardize classification terms

        Returns:
            List of classification terms
        """
        for key in ('IdeTaxonRef_tab/ClaScientificName', 'MetMeteoriteType'):
            taxa = self(*key.split('/'))
            if any(taxa):
                if isinstance(taxa[0], list):
                    taxa = [taxon[0]['ClaScientificName'] for taxon in taxa]
                break
        else:
            taxa = []
        if not isinstance(taxa, list):
            taxa = [taxa]
        # Get rid of empty list in empty row
        taxa = [taxon if taxon else '' for taxon in taxa]
        if len(taxa) > 1 and standardized:
            try:
                taxa = [self.geotree.most_specific_common_parent(taxa)]
            except (AttributeError, KeyError) as e:
                raise ValueError(taxa) from e
        return taxa


    def get_identifier(self, include_code=True, include_div=False,
                       force_catnum=False):
        """Derives sample identifier based on record

        Args:
            include_code (bool): specifies whether to include museum code
            include_div (bool): specifies whetehr to include division

        Returns:
            String of NMNH catalog number or Antarctic meteorite number
        """
        ignore = {'MetMeteoriteName'} if force_catnum else {}
        catnum = get_catnum({k: v for k, v in self.items() if k not in ignore})
        if include_div:
            catnum.mask = 'include_div'
        elif include_code:
            catnum.mask = 'include_code'
        return str(catnum)
        '''
        metnum = self('MetMeteoriteName')
        suffix = self('CatSuffix')
        if self.antmet.match(metnum) and not force_catnum:
            if suffix == metnum:
                return metnum
            else:
                return '{},{}'.format(metnum, suffix).rstrip(',')
        else:
            prefix = self('CatPrefix')
            number = self('CatNumber')
            division = self('CatDivision')
            if not division and (metnum or self('MetMeteoriteType')):
                division = 'Meteorites'
            if not number:
                return ''
            catnum = '{}{}-{}'.format(prefix, number, suffix).strip('- ')
            if include_div:
                catnum = '{} ({})'.format(catnum, division[:3].upper())
            if include_code:
                code = 'NMNH'
                if division == 'Meteorites':
                    code = 'USNM'
                catnum = '{} {}'.format(code, catnum)
            return catnum
        '''


    def get_catnum(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


    def get_catalog_number(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


    def get_division(self):
        """Returns the three-character code for the division"""
        div = self('CatDivision')[:3].upper()
        return self('CatCatalog')[:3].upper() if div == 'MIN' else div


    def get_age(self, pretty_print=True):
        """Gets geological age as string"""
        era = self('AgeGeologicAgeEra_tab')
        system = self('AgeGeologicAgeSystem_tab')
        series = self('AgeGeologicAgeSeries_tab')
        stage = self('AgeGeologicAgeStage_tab')
        ages = zip_longest(era, system, series, stage)
        if not pretty_print:
            return ages
        ages = [' > '.join([s for s in period if s]) for period in ages]
        if len(ages) == 1:
            return ages[0]
        elif ages and ages[0] != ages[-1]:
            return ' to '.join([ages[0], ages[-1]])


    def get_stratigraphy(self, pretty_print=True):
        """Gets stratigraphy as string"""
        group = self('AgeStratigraphyGroup_tab')
        formation = self('AgeStratigraphyFormation_tab')
        member = self('AgeStratigraphyMember_tab')
        strat = zip_longest(group, formation, member)
        if not pretty_print:
            return strat
        strat = [' > '.join([s for s in unit if s]) for unit in strat]
        return oxford_comma(strat)


    def get_collectors(self):
        """Gets all the collector's field numbers for a record"""
        role = ['ColParticipantRole_tab']
        participant = ['ColParticipantRef_tab', 'NamFullName']
        if self.module == 'ecatalogue':
            role.insert(0, 'BioEventSiteRef')
            participant.insert(0, 'BioEventSiteRef')
        return self.get_matching_rows('Collector', role, participant)


    def get_political_geography(self):
        """Gets political geographic info for an object

        Returns:
            List of place names in order of decreasing specificity
        """
        country_path = ['LocCountry']
        state_path = ['LocProvinceStateTerritory']
        county_path = ['LocDistrictCountyShire']
        if self.module == 'ecatalogue':
            country_path.insert(0, 'BioEventSiteRef')
            state_path.insert(0, 'BioEventSiteRef')
            county_path.insert(0, 'BioEventSiteRef')
        country = self(*country_path)
        state = self(*state_path)
        county = self(*county_path)
        if country == 'United States' and county:
            county = county.rstrip('. ')
            if county.lower().endswith('county'):
                county = county.rsplit(' ')[0].rstrip() + ' Co.'
            elif not county.lower().rstrip('.').endswith(' co'):
                county = county.rstrip() + ' Co.'
            else:
                county += '.'
        return [s if s else '' for s in (country, state, county)]


    def get_field_numbers(self):
        """Gets all the collector's field numbers for a record"""
        return self.get_matching_rows("Collector's field number",
                                      'CatOtherNumbersType_tab',
                                      'CatOtherNumbersValue_tab')


    def get_other_numbers(self, label):
        """Gets all the collector's field numbers for a record"""
        return self.get_matching_rows(label,
                                      'CatOtherNumbersType_tab',
                                      'CatOtherNumbersValue_tab')


    def is_antarctic(self, metname=None):
        """Checks if record is an Antarctic meteorite based on regex pattern"""
        if metname is None:
            metname = self('MetMeteoriteName')
        return bool(self.antmet.match(metname))


    def visual_work(self):
        """Returns types of visual work in current object"""
        obj_types = self('MinJeweleryType').lower().split(';')
        obj_types = [s.strip() for s in obj_types if s]
        if not obj_types:
            cut = self('MinCut').lower()
            if cut.startswith('carved'):
                return ['carving']
            keywords = ['box', 'carving', 'cameo']
            for keyword in keywords:
                if keyword in cut:
                    return [keyword]
        return obj_types


    def describe(self):
        """Derives a short description of the object suitable for a caption"""
        return get_caption(self)

    def summarize(self):
        """Derives and formats basic information about an object"""
        return summarize(self)
