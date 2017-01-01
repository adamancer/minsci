"""Subclass of XMuRecord with methods specific to Mineral Sciences"""

import re
from itertools import izip_longest

from .xmurecord import XMuRecord
from ...helpers import oxford_comma
from ...geotaxa import GeoTaxa


GEOTAXA = GeoTaxa()
ANTMET = re.compile(r'([A-Z]{3} |[A-Z]{4})[0-9]{5,6}(,[A-z0-9]+)?')


class MinSciRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to Mineral Sciences"""

    def __init__(self, *args):
        super(MinSciRecord, self).__init__(*args)
        # Add constants as attributes so they're available elsewhere
        # without being explicitly imported
        self.geotaxa = GEOTAXA
        self.antmet = ANTMET


    def container(self, *args):
        """Creates new instance of class that carries over attributes"""
        container = self.__class__(*args)
        container.fields = self.fields
        container.module = self.module
        return container


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
        if ANTMET.match(metnum) and not force_catnum:
            if suffix == metnum:
                return metnum
            else:
                return u'{},{}'.format(metnum, suffix).rstrip(',')
        else:
            prefix = self('CatPrefix')
            number = self('CatNumber')
            division = self('CatDivision')
            catnum = u'{}{}-{}'.format(prefix, number, suffix).strip('- ')
            if include_div:
                catnum = u'{} ({})'.format(catnum, division[:3].upper())
            if include_code:
                code = 'NMNH'
                if division == 'Meteorites':
                    code = 'USNM'
                catnum = u'{} {}'.format(code, catnum)
            return catnum


    def get_name(self, taxa=None):
        """Derives object name based on record

        Args:
            taxa (list): list of taxa. Determined automatically if omitted.

        Returns:
            String with object name
        """
        for key in ('MinName', 'MetMeteoriteName'):
            name = self(key)
            if name:
                break
        else:
            if taxa is None:
                taxa = self.get_classification(True)
            setting = self('MinJeweleryType')
            name = GEOTAXA.item_name(taxa, setting)
        return name


    def get_age(self):
        """Gets geological age as string"""
        era = self('AgeGeologicAgeEra_tab')
        system = self('AgeGeologicAgeSystem_tab')
        series = self('AgeGeologicAgeSeries_tab')
        stage = self('AgeGeologicAgeStage_tab')
        ages = izip_longest(era, system, series, stage)
        ages = [' > '.join([s for s in period if s]) for period in ages]
        if len(ages) == 1:
            return ages[0]
        elif ages and ages[0] != ages[-1]:
            return ' to '.join([ages[0], ages[-1]])


    def get_stratigraphy(self):
        """Gets stratigraphy as string"""
        group = self('AgeStratigraphyGroup_tab')
        formation = self('AgeStratigraphyFormation_tab')
        member = self('AgeStratigraphyMember_tab')
        strat = izip_longest(group, formation, member)
        strat = [' > '.join([s for s in unit if s]) for unit in strat]
        return oxford_comma(strat)


    def get_classification(self, standardized=True):
        """Gets classification of object based on record

        Args:
            standardized (bool): if True, use GeoTaxa to try to group and
                standardize classification terms

        Returns:
            List of classification terms
        """
        for key in ('IdeTaxonRef_tab/ClaSpecies', 'MetMeteoriteType'):
            taxa = self(*key.split('/'))
            if taxa:
                break
        else:
            taxa = []
        # Get rid of empty list in empty row
        taxa = [taxon if taxon else u'' for taxon in taxa]
        if not isinstance(taxa, list):
            taxa = [taxa]
        if standardized:
            try:
                taxa = GEOTAXA.group_related_taxa(taxa)
            except AttributeError:
                print taxa
                raise
        return taxa


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



    def get_field_numbers(self):
        """Gets all the collector's field numbers for a record"""
        return self.get_matching_rows("Collector's field number",
                                      'CatOtherNumbersType_tab',
                                      'CatOtherNumbersValue_tab')


    def is_antarctic(self, metname=None):
        """Checks if record is an Antarctic meteorite based on regex pattern"""
        if metname is None:
            metname = self('MetMeteoriteName')
        return bool(ANTMET.match(metname))
