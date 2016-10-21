"""Subclass of XMuRecord with methods specific to Mineral Sciences"""

import re

from .xmurecord import XMuRecord
from ...geotaxa import GeoTaxa


GEOTAXA = GeoTaxa()
ANTMET = re.compile(r'([A-Z]{3} |[A-Z]{4})[0-9]{5,6}(,[A-z0-9]+)?')

class MinSciRecord(XMuRecord):

    def __init__(self, *args):
        super(MinSciRecord, self).__init__(*args)


    def get_identifier(self, include_code=True, include_div=False,
                       force_catnum=False):
        """Derive sample identifier based on record

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
        # Get rid of empty list in empty row. This is a problem with how gaps
        # in tables are read from the export file.
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
        """Get value from the GUID table for a given key

        Args:
            kind (str): name of GUID

        Returns:
            First match from the GUID table for the key
        """
        matches = self._get_rows(kind, 'AdmGUIDType_tab', 'AdmGUIDValue_tab')
        try:
            return matches[0]
        except IndexError:
            return None


    def get_field_numbers(self):
        """Gets all the collector's field numbers for a record"""
        return self._get_rows("Collector's field number",
                              'CatOtherNumbersType_tab',
                              'CatOtherNumbersValue_tab')


    def _get_rows(self, match, label_field, value_field):
        """Helper function to find rows in any table matching a kind/label

        Args:
            match (str): the name of the label to match
            label_field (str): field in a table containing the label
            value_field (str): field in a table containing the value

        Returns:
            List of values matching the match string
        """
        rows = zip(self(label_field), self(value_field))
        match = standardize(match)
        return [val for label, val in rows if standardize(label) == match]


def standardize(s):
    return re.sub('[^\W]', '', s.upper()).upper()
