"""Script to create or update a group via import"""
from __future__ import unicode_literals

import os

from minsci import xmu
from minsci.xmu.tools.groups import write_group


class XMu(xmu.XMu):

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.irns = []


    def iterate(self, element):
        rec = self.parse(element)
        if rec('MinName') == 'Hope Diamond':
            self.irns.append(rec('irn'))


xmudata = XMu(os.path.join('reports', 'ecatalogue.xml'))
xmudata.fast_iter()

irns = list(set(xmudata.irns))
# If you want to update an existing group, pass an irn
write_group('ecatalogue', irns, irn=1000000)
# If this a new group, specify the name of the group
write_group('ecatalogue', irns, name='CursedDiamonds')