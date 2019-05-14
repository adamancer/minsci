"""Tools to parse audits data from EMu"""
from __future__ import print_function
from __future__ import unicode_literals

from random import randint

from ...xmu import XMu, AuditRecord
from ..containers.auditrecord import Change


class Auditor(XMu):
    """Processes an eaudits XML export into HTML for easy viewing

    Args:
        keep (int): percent of records to include in the output
        whitelist (list): list of fields to output. All other fields
            will be ignored. The whitelist supersedes the blacklist.
        blacklist (list): list of fields to exclude from output. all
            other fields will be included.
        modules (list): list of modules to include in the report
        users (list): list of users to include in the report

    Attributes:
        keep (int): percent of records to include in the output
        whitelist (list): list of fields to output. All other fields
            will be ignored. The whitelist supersedes the blacklist.
        blacklist (list): list of fields to exclude from output. all
            other fields will be included.

    """

    def __init__(self, *args, **kwargs):
        # Process Audtito-specific keywaords
        self.percent_to_review = kwargs.pop('percent_to_review', 2)
        self.blacklist = kwargs.pop('blacklist', [])
        self.whitelist = kwargs.pop('whitelist', [])
        # Filter params
        self.modules = kwargs.pop('modules', [])
        self.users = kwargs.pop('users', [])
        super(Auditor, self).__init__(*args, **kwargs)
        print('Examining around {}% of records'.format(self.percent_to_review))
        # Default values for the blacklist. Fields included here are not
        # printed in the HTML report.
        if not self.blacklist:
            self.blacklist = [
                'AdmDateModified',
                'AdmModifiedBy',
                'AdmTimeModified',
                'DarDateLastModified',
                'ExiIfd_tab',
                'ExiName_tab',
                'ExiTag_tab',
                'ExiValue_tab',
                'ExtendedData',
                'SummaryData'
                ]
        self._container = AuditRecord
        self.records = {}
        self._html = []  # results is a list of self.containers


    def iterate(self, element, whitelist=None, blacklist=None):
        """Groups audit records by module and irn"""
        rec = self.parse(element)
        if whitelist or blacklist:
            rec = rec.simplify(whitelist=whitelist, blacklist=blacklist)
        if rec('AudTable') == 'egroups':
            return True
        key = '-'.join([rec('AudTable'), rec('AudKey')])
        self.records.setdefault(key, []).append(rec)


    def itermodified(self, element):
        rec = self.parse(element)
        self.records.setdefault(rec('AudTable'), []).append(rec('AudKey'))


    def combine(self, records=None, keep_all=False):
        """Parses audit records into HTML"""
        if records is None:
            records = self.records
        combined = {}
        for irn, recs in records.items():
            # Filter trails that don't include the specified users
            if self.users:
                if not [rec for rec in recs if rec('AudUser') in self.users]:
                    continue
            # Filter trails that don't include the specified modules
            if self.modules:
                if not [rec for rec in recs if rec('AudTable') in self.modules]:
                    continue
            # Filter trails that end in a delete
            if [rec for rec in recs if rec('AudOperation') == 'delete']:
                continue
            # Get the audit trail
            for rec in recs:
                rec.parse_changes(self.whitelist, self.blacklist)
            if len(recs) > 1:
                # Sort from least to most recent modification time
                recs.sort(key=lambda rec: 'T'.join([rec('AudDate'),
                                                    rec('AudTime')]))
                # Get the original values from the first record
                changes = recs[0].changes
                oldest = {fld: chg.old for fld, chg in changes.items()}
                newest = {fld: chg.new for fld, chg in changes.items()}
                for rec in recs[1:]:
                    # Update original with values not modified in first audit
                    old = {fld: chg.old for fld, chg in rec.changes.items()}
                    for key, val in old.items():
                        if oldest.get(key) is None:
                            oldest[key] = val
                    # Overwrite newest with new
                    new = {fld: chg.new for fld, chg in rec.changes.items()}
                    newest.update(new)
                # Summarize the oldest and newest dictionaries into one
                # record combining the metadata of all the records
                summarized = AuditRecord()
                summarized['AudKey'] = rec('AudKey')
                summarized['AudTable'] = rec('AudTable')
                fields = ['irn', 'AudUser', 'AudOperation']
                for fld in fields:
                    items = '</li><li>'.join([rec(fld) for rec in recs])
                    summarized[fld] = '<ul><li>{}</li></ul>'.format(items)
                summarized.changes = {
                    fld: Change(fld, oldest.get(fld), newest.get(fld))
                    for fld in set(list(oldest.keys()) + list(newest.keys()))
                    }
                #summarized.pprint(True)
                recs = [summarized]
            combined[irn] = recs[0]
        return combined


    def finalize(self):
        html = []
        try:
            combined = self.combine()
        except TypeError:
            pass
        else:
            print('{:,} distinct records were modified'.format(len(combined)))
            for irn, rec in combined.items():
                if (self.percent_to_review == 100
                    or randint(1, 100) <= self.percent_to_review):
                    html.extend(self.to_html(rec))
        self._html = html
        return html


    def to_html(self, rec):
        """Converts an audit record to HTML for display"""
        html = ['<h1>{}: {}</h1>'.format(rec('AudTable'), rec('AudKey'))]
        html.append(u'<table>')
        keys = ['irn', 'AudUser', 'AudOperation']
        for key in keys:
            html.append('<tr><th>{}</th><td colspan="2">{}'
                        '</td></tr>'.format(key, rec(key)))
        if rec.changes is None:
            rec.parse_changes(self.whitelist, self.blacklist)
        for field in sorted(rec.changes):
            change = rec.changes[field]
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


    def write_html(self, fp, html=None):
        """Writes HTML document containing the HTMLized records"""
        header = ['<!DOCTYPE html>'
                  '<html>'
                  '<head><title>Audit Review Tool</title></head>'
                  '<meta charset="utf-8">'
                  '<style>'
                  'body { font: 11pt calibri; }'
                  'h1 { color: #39f; }'
                  'table { width: 70%; font: 10pt calibri; border-collapse: collapse; margin-bottom: 1%; }'
                  'tr:hover { background-color: #e6f2ff; }'
                  'th, td { vertical-align: top; border: 1px solid #ccc; padding: 1%; }'
                  'th { width: 10%; font-weight: 800; text-align: left; }'
                  'td { width: 25%; }'
                  'ol { padding: 1%; margin: 2%; }'
                  '</style>'
                  '<body>']
        footer = ['</body>'
                  '</html>']
        html = header + self._html if html is None else html + footer
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(''.join(html))


    @staticmethod
    def format_value(field, val):
        """Formats values pulled from the old/new table for printing"""
        if field.endswith(('0', '_nesttab', '_nesttab_inner', '_tab')):
            vals = val if val is not None else []
            vals = [u'<li>{}</li>'.format(val) for val in vals]
            return u'<ol>' + u''.join(vals) + u'</ol>'
        return val
