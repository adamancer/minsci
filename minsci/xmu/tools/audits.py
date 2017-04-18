"""Tools to parse audits data from EMu"""

from random import randint

from ...xmu import XMu, AuditRecord


class Auditor(XMu):
    """Processes an eaudits XML export into HTML for easy viewing

    Args:
        keep (int): percent of records to include in the output
        whitelist (list): list of fields to output. All other fields
            will be ignored. The whitelist supersedes the blacklist.
        blacklist (list): list of fields to exclude from output. all
            other fields will be included.

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
        super(Auditor, self).__init__(*args, **kwargs)
        print 'Reviewing about {}% of records'.format(self.percent_to_review)
        # Default values for the blacklist. Fields included here are not
        # printed in the HTML report.
        if not self.blacklist:
            self.blacklist = [
                'AdmDateModified',
                'AdmModifiedBy',
                'AdmTimeModified',
                'DarDateLastModified'
                ]
        self._container = AuditRecord
        self._html = []  # results is a list of self.containers


    def iterate(self, element):
        """Parses audit records into HTML"""
        if (self.percent_to_review == 100
            or randint(1, 100) <= self.percent_to_review):
            rec = self.parse(element)
            self._html.extend(rec.to_html(self.whitelist, self.blacklist))
        else:
            return True


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
        with open(fp, 'wb') as f:
            f.write(''.join([s.encode('utf-8') for s in html]))
