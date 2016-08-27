"""Subclass of XMuRecord with methods specific to Mineral Sciences"""

import re

from .xmurecord import XMuRecord
from ...geotaxa import GeoTaxa


GEOTAXA = GeoTaxa()
ANTMET = re.compile(r'([A-Z]{3} |[A-Z]{4})[0-9]{5,6}(,[A-z0-9]+)?')

class MinSciRecord(XMuRecord):

    def __init__(self, *args):
        super(MinSciRecord, self).__init__(*args)


    def get_identifier(self, include_code=True, include_div=False):
        """Derive sample identifier based on record

        Args:
            include_code (bool): specifies whether to include museum code
            include_div (bool): specifies whetehr to include division

        Returns:
            String of NMNH catalog number or Antarctic meteorite number
        """
        metnum = self('MetMeteoriteName')
        suffix = self('CatSuffix')
        if ANTMET.match(metnum):
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
        """Derive object name based on record

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


    def get_classification(self, standardized=True):
        """Get classification of object based on record

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
        # HACK: Get rid of empty list in empty row. This is a problem
        # with how gaps in tables are read from the export file.
        taxa = [taxon if taxon else '' for taxon in taxa]
        if not isinstance(taxa, list):
            taxa = [taxa]
        if standardized:
            try:
                taxa = GEOTAXA.group_taxa(taxa)
            except:
                print taxa
                raise
        return taxa


    def get_guid(self, kind='EZID'):
        guids = rec('AdmGUIDValue_tab', 'AdmGUIDValue')
        return [guid for guid in guids if guid.startswith('ark:/')][0]


    def get_field_numbers(self):
        kinds = rec('CatOtherNumbersType_tab', 'CatOtherNumbersType')
        values = rec('CatOtherNumbersValue_tab', 'CatOtherNumbersValue')
        field_nums = []
        for i in xrange(len(kinds)):
            kind = kinds[i].lower()
            if kind == "collector's field number":
                field_numbers.append(values[i])
        return field_nums
