"""Subclass of XMuRecord with methods specific to MinSci taxonomy"""

from itertools import izip_longest

from ...xmu import XMuRecord


class MinSciTaxon(XMuRecord):
    """Contains methods to read taxonomic info from an EMu XML export"""

    def __init__(self, *args):
        super(MinSciTaxon, self).__init__(*args)


    def get_synonyms(self):
        """Returns a list of preferred synonyms for the current taxon"""
        return self.get_matching_rows('Preferred synonym',
                                      'AssAssociatedWithComment_tab',
                                      ('AssAssociatedWithRef_tab', 'NarTitle'))


    def get_schema(self):
        """Returns a list of schema that include the current taxon"""
        schema = izip_longest(self('NarType_tab'), self('NarExplanation_tab'))
        return [{'scheme': scheme, 'value': val} for scheme, val in schema]
