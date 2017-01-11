"""Subclass of XMuRecord with methods specific to emultimedia"""

import os
import re
from collections import namedtuple
from itertools import izip_longest

from dateparser import parse

from .xmurecord import XMuRecord
from ..tools.multimedia.embedder import Embedder
from ..tools.multimedia.hasher import hash_file
from ...helpers import format_catnums, oxford_comma, parse_catnum


class BiblioRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to ebibliography"""

    def __init__(self, *args):
        super(BiblioRecord, self).__init__(*args)
        self.module = 'ebibliography'
        self.prefix = self('BibRecordType')[:3]
        self.masks = {
            'Art': (u'{authors}, {year}. "{title}." <i>{source}</i>,'
                     ' {volume}:({issue}) {pages}'),
        }



    def __call__(self, *args, **kwargs):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        args = [self.prefix + arg[3:] if arg.startswith('Art')
                else arg for arg in args]
        return self.smart_pull(*args)


    def format_reference(self):
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
        authors = []
        for author in self('ArtAuthorsRef_tab'):
            authors.append(self.format_name(author('NamLast'),
                                            author('NamFirst'),
                                            author('NamMiddle')))
        return authors


    def get_source(self):
        sources = {
            'Art': 'Jou',
            'Cha': 'Boo'
        }
        return self('ArtParentRef', sources[self.prefix] + 'Title')


    @staticmethod
    def clean_reference(ref):
        characters = ['()', ' : ', ' :', ' ,', ' .', '""', '<i></i>']
        for char in characters:
            ref = ref.replace(char, ' ')
        while '  ' in ref:
            ref = ref.replace('  ', ' ')
        return ref


    @staticmethod
    def format_name(last, first, middle, use_initials=True,
                    mask='{last}, {first} {middle}'):
        if use_initials:
            first = first[0] + '.' if first else ''
            middle = middle[0] + '.' if middle else ''
        return mask.format(last=last, first=first, middle=middle).rstrip()
