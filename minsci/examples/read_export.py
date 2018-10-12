"""Script to read data from an EMu export file"""
from __future__ import print_function
from __future__ import unicode_literals

import os

from minsci import xmu


class XMu(xmu.XMu):

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.records = {}


    def iterate(self, element):
        # The parse method converts the element into a dict
        rec = self.parse(element)
        # Keys can be accessed using the normal bracket notation
        irn = rec['irn']
        # Values can also be retrieved by calling the record as a function.
        # This method offers the following advantages:
        #   + Allows user to pass multiple arguments to access data deep
        #     in the dictionary
        #   + Automatically returns a list of values if key is a grid
        #   + Paths are validated against the organization schema file
        #
        # Calling the record suppresses KeyError exceptions, which could be
        # a bug or a feature depending on your point of view.
        print('--------\nSample data retrieval\n--------')
        print('irn:', rec('irn'))                                # 1001299
        print('name:', rec('MinName'))                           # Hope Diamond
        print('country:', rec('BioEventSiteRef', 'LocCountry'))  # India
        print('measurements:', rec('MeaType_tab'))               # list
        # Some common operations have shortcut methods. For example, the
        # get_guid method returns the value from the row with type EZID.
        print(rec.get_guid('EZID'))


xmudata = XMu(os.path.join('reports', 'ecatalogue.xml'))
xmudata.fast_iter()
