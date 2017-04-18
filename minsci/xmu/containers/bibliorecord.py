"""Subclass of XMuRecord with methods specific to emultimedia"""

import re

from dateparser import parse

from .xmurecord import XMuRecord
from ...helpers import oxford_comma


class BiblioRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to ebibliography"""

    def __init__(self, *args, **kwargs):
        super(BiblioRecord, self).__init__(*args, **kwargs)
        self.module = 'ebibliography'
        self.prefix = self.get_prefix()
        self.masks = {
            'Art': (u'{authors}, {year}. "{title}." <i>{source}</i>,'
                    ' {volume}({issue}): {pages}'),
            'Boo': (u'{authors}, {year}. {title}. In <i>{source}</i> '
                    ' (v. {volume}), {pages}p.'),
        }


    def __call__(self, *args, **kwargs):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        args = [self.prefix + arg[3:] if arg.startswith('Art')
                else arg for arg in args]
        try:
            return self.smart_pull(*args)
        except KeyError:
            print 'Path not found:', args
            return ''


    def __getattribute__(self, key):
        val = object.__getattribute__(self, key)
        if key == 'prefix' and not val and self.is_biblio():
            prefix = self.get_prefix()
            self.prefix = prefix
            return prefix
        return val


    def get_prefix(self):
        """Get prefix based on record type or keys"""
        prefix = self('BibRecordType')[:3]
        if not prefix and self.is_biblio():
            prefixes = {}
            for key in self:
                prefixes.setdefault(key[:3], 0)
                prefixes[key[:3]] += 1
            prefix = [key for key, val in prefixes.iteritems()
                      if val == max(prefixes.values())][0]
        return prefix



    def is_biblio(self):
        """Checks if record is a reference"""
        prefixes = ('Art', 'Bib', 'Boo', 'Bos', 'Jou')
        return bool([key for key in self if key.startswith(prefixes)])


    def format_reference(self):
        """Formats reference according to publication type"""
        authors = oxford_comma(self.get_authors())
        title = self('ArtTitle')
        # Get publication date
        pub_date = parse(self('ArtPublicationDates'))
        if pub_date is not None:
            year = pub_date.year
            month = pub_date.month
        else:
            pub_date = self('ArtPublicationDates')
            try:
                year = re.search(r'\b\d{4}\b', pub_date).group()
            except AttributeError:
                year = None
            month = None
        # Get periodical/book info
        source = self.get_source()
        volume = self('ArtVolume')
        issue = self('ArtIssue')
        pages = self('ArtPages')
        if not volume and month:
            volume = pub_date.strftime('%b. %Y')
        elif not volume and pub_date != year:
            volume = pub_date
        ref = self.masks[self.prefix].format(authors=authors,
                                             year=year,
                                             title=title,
                                             source=source,
                                             volume=volume,
                                             issue=issue,
                                             pages=pages)
        return self.clean_reference(ref)


    def get_authors(self):
        """Formats a list of author names"""
        authors = []
        for author in self('ArtAuthorsRef_tab'):
            authors.append(self.format_name(author('NamLast'),
                                            author('NamFirst'),
                                            author('NamMiddle')))
        return authors


    def get_source(self):
        """Determines the type of the source/parent publication"""
        sources = {
            'Art': 'Jou',
            'Boo': 'Bos',
            'Cha': 'Boo'
        }
        return self('ArtParentRef', sources[self.prefix] + 'Title')


    @staticmethod
    def clean_reference(ref):
        """Cleans punctuation, etc. left behind when ref has empty fields
        FIXME: This is horrible
        """
        characters = ['()', ' : ', ' :', ' ,', ' .', '""', '<i></i>', ', p.', '(v. )']
        for char in characters:
            ref = ref.replace(char, ' ')
        while '  ' in ref:
            ref = ref.replace('  ', ' ')
        return ref


    @staticmethod
    def format_name(last, first, middle, use_initials=True,
                    mask='{last}, {first} {middle}'):
        """Formats a name according to the given mask"""
        if use_initials:
            first = first[0] + '.' if first else ''
            middle = middle[0] + '.' if middle else ''
        return mask.format(last=last, first=first, middle=middle).rstrip()
