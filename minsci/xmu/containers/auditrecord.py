"""Subclass of DeepDict with methods specific to eaudits"""
from __future__ import print_function
from __future__ import unicode_literals

from collections import namedtuple

from lxml import etree

from .xmurecord import XMuRecord


Change = namedtuple('Change', ['field', 'old', 'new'])

class AuditRecord(XMuRecord):
    """Contains methods for reading data from EMu XML exports"""

    def __init__(self, *args):
        super(AuditRecord, self).__init__(*args)
        self.module = 'eaudits'
        self.changes = None


    def parse_field(self, field):
        """Parse values found in a single field in the old/new table"""
        vals = {}
        for line in self(field):
            field, xml = line.split(': ', 1)
            if len(xml) >= 30000:
                print('Could not parse {}'.format(field))
                vals[field] = 'PARSE_ERROR'
                continue
            try:
                tree = etree.fromstring(xml)
            except etree.XMLSyntaxError:
                print(xml)
                raise
            if xml.startswith('<atom'):
                val = tree.text if isinstance(tree.text, str) else tree.text.decode('utf-8')
            else:
                atoms = [tuple.find('atom') for tuple in tree.findall('tuple')]
                val = [atom.text if atom is not None else '' for atom in atoms]
            vals[field] = val
        return vals


    def parse_changes(self, whitelist=None, blacklist=None):
        """Parse values in the old and new values table in Audits

        Args:
            rec (xmu.DeepDict): data from eaudits

        Returns:
            List of named tuples containing the old and new values
        """
        # The new and old lists do not always contain the same fields, so
        # process each separately.
        old = self.parse_field('AudOldValue_tab')
        new = self.parse_field('AudNewValue_tab')
        changes = {field: Change(field, old.get(field), new.get(field))
                   for field in set(list(old.keys()) + list(new.keys()))
                   if old.get(field) != new.get(field)}
        # Limit fields based on whitelist/blacklist
        if whitelist:
            changes = {fld: changes[fld] for fld
                       in changes if fld in whitelist}
        elif blacklist:
            endswith = ('Local', 'Local0', 'Local_tab')
            changes = {fld: changes[fld] for fld in changes
                       if (fld not in blacklist
                           and not fld.startswith('Dar')
                           and not fld.endswith(endswith))}
        self.changes = changes
        return changes
