import re
from collections import namedtuple

from ....xmu import XMu, BiblioRecord


Existing = namedtuple('Existing', ['irn', 'authors', 'pub_date'])


class BibCheck(XMu):

    def __init__(self, *args, **kwargs):
        kwargs['container'] = BiblioRecord
        super(BibCheck, self).__init__(*args, **kwargs)
        self.records = {}


    def iterate(self, element):
        """Returns basic information about a reference"""
        rec = self.parse(element)
        self.records[rec('irn')] = Existing(rec('irn'),
                                            self.get_authors(rec),
                                            self.get_pub_date(rec))


    @staticmethod
    def get_authors(rec):
        key = '{}AuthorsRef_tab'.format(rec.prefix)
        return [re.sub(r'[^A-Za-z0-9]', '', a['NamLast']).lower() for a in rec(key)]


    @staticmethod
    def get_pub_date(rec):
        for key in ('{}PublicationDate', '{}PublicationDates'):
            val = rec(key.format(rec.prefix))
            if val:
                return get_year(val)




def compare_citations(authors, pub_date, existing, show_warnings=True):
    """Checks new author and publication date against existing record"""
    # Test authors
    if not authors:
        msg = 'E: No authors found: {}'.format(existing.irn)
        print msg
        return False
    # Test first authors. These MUST match.
    if existing.authors and authors[0] != existing.authors[0]:
        msg = ('E: First author mismatch: {}: {} =>'
               ' {}').format(existing.irn, existing.authors, authors)
        print msg
        return False
    # Test full author list. This is only yields a warning because mismatches
    # here are common and to some extent expected (for example, if there is a
    # long list of authors)
    if (existing.authors
        and authors != existing.authors
        and existing.authors[-1] != 'others'):
        if show_warnings:
            print ('W: Author mismatch: {}: {} =>'
                   ' {}').format(existing.irn, existing.authors, authors)
    # Test publication year. This MUST match.
    new_year = get_year(pub_date)
    old_year = get_year(existing.pub_date)
    if old_year and old_year != new_year:
        msg = ('E: Pub. year mismatch: {}: {} =>'
               ' {}').format(existing.irn, existing.pub_date, pub_date)
        print msg
        return False
    return True


def get_year(val):
    """Parses a four-digit year from a date string"""
    if val is not None:
        match = re.search(r'\d{4}', val)
        if match is not None:
            return match.group(0)
