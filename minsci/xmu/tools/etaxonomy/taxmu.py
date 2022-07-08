import datetime as dt
import os
import shutil

from nmnh_ms_tools.records.classification import TaxaNamer, TaxaParser, Taxon

from ...containers import MinSciRecord
from ...xmu import XMu, write




class TaXMu(XMu):

    def __init__(self, *args, **kwargs):
        super(TaXMu, self).__init__(*args, **kwargs)
        # The tree contains the primary records for each taxon
        self.tree = TaxaNamer()
        self.autoiterate(['tree'], report=5000)
        # Convert the tree to a TaxaTree and set the timestamp
        self.tree = TaxaNamer(self.tree)
        self.tree.timestamp = self.newest
        Taxon.tree = self.tree
        MinSciRecord.geotree = self.tree


    def __getattr__(self, attr):
        try:
            return getattr(self.tree, attr)
        except AttributeError:
            try:
                return getattr(super(TaxMu, self), attr)
            except AttributeError:
                raise AttributeError(attr)


    def iterate(self, element):
        """Adds a Taxon to the tree"""
        rec = self.parse(element)
        self.tree[rec('irn')] = Taxon(rec)


    def finalize(self):
        """Determines relationships between taxa"""
        print('Assigning synonyms...')
        self.tree._assign_synonyms()
        print('Assigning similar...')
        self.tree._assign_similar()
        print('Assigning official...')
        self.tree._assign_official()


    def check(self):
        """Checks for consistency issues in the hierarchy"""

        updates = []
        errors = []


        # Check current designation
        for key, taxon in self.tree.items():
            if key.isnumeric():
                try:
                    rec = taxon.fix_current()
                    if rec:
                        updates.append(rec)
                except KeyError:
                    errors.append(f'Invalid IRN: {key}')

        # Validate tree
        if updates:
            timestamp = dt.datetime.now().strftime('%Y%m%dT%H%M%S')
            write('update_{}.xml'.format(timestamp), updates, 'etaxonomy')
            return False

        # Check for other integrity issues
        for key, taxon in self.tree.items():
            if key.isnumeric():
                try:
                    rec = taxon.fix()
                    if rec:
                        updates.append(rec)
                except (KeyError, ValueError) as err:
                    errors.append(str(err))

        # List errors if any found
        if errors:
            print('Errors:')
            print('\n'.join(errors))

        # Validate tree
        if updates:

            print('Writing updates...')
            timestamp = dt.datetime.now().strftime('%Y%m%dT%H%M%S')
            write('update_{}.xml'.format(timestamp), updates, 'etaxonomy')

            if not errors:
                print('Testing relationships...')
                for key, taxon in self.tree.items():
                    if key.isnumeric():
                        taxon.preferred()
                        taxon.parents()
                        taxon.official()

        return not (errors or updates)
