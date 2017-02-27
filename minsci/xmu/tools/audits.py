"""Tools to parse audits data from EMu"""

from collections import namedtuple
from lxml import etree


Change = namedtuple('Change', ['field', 'old', 'new'])

def parse_audit(rec):
    """Parse values in the old and new values table in Audits

    Args:
        rec (xmu.DeepDict): data from eaudits

    Returns:
        List of named tuples containing the old and new values
    """
    # The new and old lists do not always contain the same fields, so
    # process each separately.
    old = {}
    for line in rec('AudOldValue_tab'):
        field, xml = line.split(': ', 1)
        val = [s for s in etree.fromstring(xml).itertext()]
        if not xml.startswith('<table>'):
            val = val[0]
        old[field] = val
    new = {}
    for line in rec('AudNewValue_tab'):
        field, xml = line.split(': ', 1)
        val = [s for s in etree.fromstring(xml).itertext()]
        if not xml.startswith('<table>'):
            val = val[0]
        new[field] = val
    # Return dictionary of all changes
    return {field: Change(field, old.get(field), new.get(field))
            for field in set(old.keys() + new.keys())}
