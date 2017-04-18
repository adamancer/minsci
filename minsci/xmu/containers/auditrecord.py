"""Subclass of DeepDict with methods specific to eaudits"""

from collections import namedtuple

from lxml import etree

from .xmurecord import XMuRecord


Change = namedtuple('Change', ['field', 'old', 'new'])

class AuditRecord(XMuRecord):
    """Contains methods for reading data from EMu XML exports"""

    def __init__(self, *args):
        super(AuditRecord, self).__init__(*args)


    def format_value(self, field, val):
        """Formats values pulled from the old/new table for printing"""
        if field.endswith(('0', '_nesttab', '_nesttab_inner', '_tab')):
            vals = val if val is not None else []
            vals = [u'<li>{}</li>'.format(val) for val in vals]
            return u'<ol>' + u''.join(vals) + u'</ol>'
        return val


    def to_html(self, whitelist=None, blacklist=None):
        """Converts an audit record to HTML for display"""
        html = ['<h1>{}</h1>'.format(self('AudKey'))]
        html.append(u'<table>')
        keys = ['irn', 'AudUser', 'AudTable', 'AudOperation']
        for key in keys:
            html.append('<tr><th>{}</th><td colspan="2">{}</a>'.format(key, self(key)))
        changes = self.parse_changes()
        # Limit fields if whitelist or blacklist set
        if whitelist:
            changes = {fld: changes[fld] for fld in changes if fld in whitelist}
        elif blacklist:
            changes = {fld: changes[fld] for fld in changes if fld not in blacklist}
        for field in sorted(changes):
            change = changes[field]
            #num_rows = max([len(val) if isinstance(val, list) else 1
            #                for val in [change.old, change.new]
            #                if val is not None])
            old = self.format_value(field, change.old)
            new = self.format_value(field, change.new)
            # Capture changes only
            if old != new:
                html.append(u'<tr>')
                html.append(u'<th>{}</th>'.format(field))
                html.append(u'<td>{}</td>'.format(old))
                html.append(u'<td>{}</td>'.format(new))
                html.append(u'</tr>')
        html.append(u'</table>')
        return html


    def parse_field(self, field):
        """Parse values found in a single field in the old/new table"""
        vals = {}
        for line in self(field):
            field, xml = line.split(': ', 1)
            tree = etree.fromstring(xml)
            if xml.startswith('<atom'):
                val = tree.text if isinstance(tree.text, unicode) else tree.text.decode('utf-8')
            else:
                atoms = [tuple.find('atom') for tuple in tree.findall('tuple')]
                val = [atom.text if atom is not None else '' for atom in atoms]
            vals[field] = val
        return vals


    def parse_changes(self):
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
        # Return dictionary of all changes
        return {field: Change(field, old.get(field), new.get(field))
                for field in set(old.keys() + new.keys())}
