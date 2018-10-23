"""Subclass of XMuRecord with methods specific to Mineral Sciences"""
from __future__ import print_function
from __future__ import unicode_literals

import re
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

from .xmurecord import XMuRecord
from ..tools.describer import get_caption, summarize
from ...helpers import oxford_comma




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


    def get_classification_string(self, taxa=None, standardized=True):
        if taxa is None:
            taxa = self.get_classification(True)
        return self.geotree.name_item(taxa)


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
        taxa = [taxon if taxon else u'' for taxon in taxa]
        if standardized:
            try:
                taxa = self.geotree.group(taxa)
            except (AttributeError, KeyError):
                print(taxa)
                #raise
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
        metnum = self('MetMeteoriteName')
        suffix = self('CatSuffix')
        if self.antmet.match(metnum) and not force_catnum:
            if suffix == metnum:
                return metnum
            else:
                return u'{},{}'.format(metnum, suffix).rstrip(',')
        else:
            prefix = self('CatPrefix')
            number = self('CatNumber')
            division = self('CatDivision')
            if self('MetMeteoriteName') or self('MetMeteoriteType'):
                division = 'Meteorites'
            if not number:
                return u''
            catnum = u'{}{}-{}'.format(prefix, number, suffix).strip('- ')
            if include_div:
                catnum = u'{} ({})'.format(catnum, division[:3].upper())
            if include_code:
                code = 'NMNH'
                if division == 'Meteorites':
                    code = 'USNM'
                catnum = u'{} {}'.format(code, catnum)
            return catnum


    def get_catnum(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


    def get_catalog_number(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


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


    def get_guid(self, kind='EZID', allow_multiple=False):
        """Gets value from the GUID table for a given key

        Args:
            kind (str): name of GUID
            allow_multiple (bool): if False, raises error if multiple
                values with same type are found

        Returns:
            First match from the GUID table for the key (if allow_multiple
            is False) or the full set of matches (if allow_multiple is True)
        """
        args = (kind, 'AdmGUIDType_tab', 'AdmGUIDValue_tab')
        if kind == 'IGSN':
            args = (kind, 'CatOtherNumbersType_tab', 'CatOtherNumbersValue_tab')
        matches = self.get_matching_rows(*args)
        if len(matches) > 1 and not allow_multiple:
            raise Exception('Multiple values found for {}'.format(kind))
        if allow_multiple:
            return matches
        else:
            try:
                return matches[0]
            except IndexError:
                return None


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


    def is_antarctic(self, metname=None):
        """Checks if record is an Antarctic meteorite based on regex pattern"""
        if metname is None:
            metname = self('MetMeteoriteName')
        return bool(self.antmet.match(metname))


    def describe(self):
        """Derives a short description of the object suitable for a caption"""
        return get_caption(self)

    def summarize(self):
        """Derives and formats basic information about an object"""
        return summarize(self)
