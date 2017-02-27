"""Tools for writing and verifying EMu multimedia imports"""

import csv
import hashlib
import os
from collections import namedtuple
from itertools import izip_longest

from .embedder import EmbedFromEMu
from ....xmu import XMu, MinSciRecord, write
from ....helpers import dedupe, parse_catnum




Error = namedtuple('Error', ['filename', 'message'])
Media = namedtuple('Media', ['irn', 'filename', 'checksum',
                             'record', 'is_primary'])


class MultimediaWriter(XMu):
    """Tools to write and check imports for the EMu Multimedia module"""

    def __init__(self, *args, **kwargs):
        catalog_path = kwargs.pop('catalog_path')
        super(MultimediaWriter, self).__init__(*args, **kwargs)
        # Create multimedia lookups
        self.multimedia = {}
        self.fast_iter(report_at=25000, callback=self.save)
        # Create catalog lookups
        self.cataloger = Cataloger(catalog_path, container=MinSciRecord)
        self.cataloger.fast_iter(report_at=25000, callback=self.cataloger.save)
        # Add embedder
        embedder = EmbedFromEMu()
        self.embed_from_emu = embedder.embed_from_emu
        # Create output container
        self.records = {}
        self.checksums = {}
        self.logfile = open('multimedia.log', 'wb')
        # Set defaults
        self.defaults = {
            'MulTitle': 'Mineral Sciences Photo',
            'DetRights': 'This image was obtained from the Smithsonian'
                         ' Institution. Its contents may be protected by'
                         ' international copyright laws.'
        }


    def iterate(self, element):
        """Reads multimedia information from file"""
        rec = self.parse(element)
        irn = rec('irn')
        filename = rec('MulIdentifier')
        if filename:
            # Add primary multimedia to lookup
            primary = Media(irn, filename, rec('ChaMd5Sum'), rec, True)
            for key in (int(irn), filename):
                self.multimedia.setdefault(key, []).append(primary)
            # Check for supplementary media
            supplementary = izip_longest(rec('SupIdentifier_tab'),
                                         rec('SupMD5Checksum_tab'))
            for filename, hexhash in supplementary:
                media = Media(irn, filename, hexhash, None, True)
                for key in (int(irn), filename):
                    self.multimedia.setdefault(filename, []).append(media)


    def get_media(self, key):
        """Test if an EMu record exists for the given filename"""
        try:
            key = key.lower()
        except AttributeError:
            # User has passed an IRN as the key
            return self.multimedia.get(key)
        # Test for short or generic filenames
        if key.startswith('img_') or key.isnumeric() or len(key) < 12:
            return []
        return self.multimedia.get(key)


    def check_and_write(self, records, fp='import.xml',
                        checksums='checksums.txt', report_at=0):
        """Checks import for errors and records checksums

        Args:
            records (list): list of xmu.DeepDict objects
            fp (str): path to import file
            checksums (str): path to checksum file
        """
        checked = []
        self.checksums = {}
        print '{:,} records to be imported'.format(len(records))
        i = 0
        for rec in records:
            if self._check_record(rec):
                checked.append(rec)
            i += 1
            if report_at and not i % report_at:
                print ('{:,} records processed'
                       ' ({:,} kept)').format(i, len(checked))
        print '{:,} records processed ({:,} kept)'.format(i, len(checked))
        if len(checked) == len(records):
            print 'All records checked out'
        else:
            print 'Errors found!'
        # Record checksums
        with open(checksums, 'wb') as f:
            writer = csv.writer(f)
            writer.writerow(['Filename', 'MD5'])
            for row in self.checksums.iteritems():
                writer.writerow(row)
        write(fp, checked, 'emultimedia')


    def create_record(self, rec, catnum=None):
        """Create multimedia record based on data from catalog"""
        # Check for existing media with this filename. Note that short or
        # generic filenames won't match even if records already exist.
        media = self.get_media(os.path.basename(rec('Multimedia')))
        if len(media) == 1:
            rec['irn'] = media[0].irn
        # Check for objects matching this catalog number
        if catnum is not None:
            fake_rec = {'MulTitle': catnum + ' [AUTO]'}
            objects = self.find_catalog_objects(fake_rec)
            if len(objects) == 1:
                self.update_record(rec, objects[0])


    def update_record(self, rec, obj):
        """Update multimedia record based on data from catalog"""
        update = self.container()
        # Update empty or automatically generated titles
        title = rec('MulTitle')
        if (not title
                or (title.startswith('Mineral Sciences')
                    and title.endswith('Photo'))
                or title.endswith('[AUTO]')):
            update['MulTitle'] = obj.title + ' [AUTO]'
        # Update empty or automatically generated captions
        description = rec('MulDescription')
        if not description or description.endwith('[AUTO]'):
            update['MulDescription'] = obj.caption + ' [AUTO]'
        # Update keywords, keeping any keywords in the original record that
        # are in KW_WHITELIST
        keywords = (obj.keywords + [kw for kw in rec('DetSubject_tab')
                                    if kw in KW_WHITELIST])
        update['DetSubject_tab'] = keywords
        # Updated related
        update.update(self.assign_collections(obj, rec))
        update.update(self.assign_related(rec))
        # Update note
        note = rec('NotNote').split(';')
        for i, val in enumerate(note):
            if val.strip().startswith('Linked:'):
                note[i] = 'Linked: Yes'
                break
        else:
            note.append('Linked: Yes')
        note = ';'.join(note)
        # Remove unchanged keys
        for key in rec:
            val = update.get(key)
            if val is None or val == rec(key):
                del update[key]
        # Embed multimedia if files are specified
        if update and rec('Multimedia'):
            update.update(self.embed_from_emu(rec))
        # Add to output list
        if update:
            irn = rec('irn')
            if irn:
                update['irn'] = irn
            self.records.setdefault('emultimedia', []).append(update.expand())


    def hash_image(self, fp):
        """Get MD5 hash of an image file

        Args:
            fp (str): path to image

        Returns:
            Tuple containing (filename, hash)
        """
        return os.path.basename(fp), self._hash(open(fp, 'rb'))


    def _check_record(self, rec):
        """Hashes images in record and applies defaults

        Returns:
            Dict of record data if record is okay, otherwise False
        """
        # Hash all files in the import file
        paths = [rec('Multimedia')]
        if rec('Supplementary_tab'):
            paths.extend(rec('Supplementary_tab'))
        for path in paths:
            print 'Hashing {}...'.format(path)
            try:
                fn, hexhash = self.hash_image(path)
            except IOError:
                self.logfile.write('Error: {}: Not found\n'.format(path))
                #return False
            else:
                try:
                    self.checksums[fn]
                except KeyError:
                    self.checksums[fn] = hexhash
                else:
                    print '{} already exists!'.format(fn)
                    return False
        # Assign defaults if key empty or not found
        for field, default in self.defaults.iteritems():
            if not rec(field):
                rec[field] = default
        rec = rec.expand()
        return rec


    @staticmethod
    def _hash(filestream, size=8192):
        """Generate md5 hash for a file

        Args:
            filestream (file): stream of file to hash
            size (int): size of block. Should be multiple of 128.

        Return:
            Tuple of (filename, hash)
        """
        if size % 128:
            raise ValueError('size must be a multiple of 128')
        md5_hash = hashlib.md5()
        while True:
            chunk = filestream.read(size)
            if not chunk:
                break
            md5_hash.update(chunk)
        return md5_hash.hexdigest()





class MultimediaUpdater(MultimediaWriter):
    """Tools to update existing records from the EMu Multimedia module"""

    def __init__(self, *args, **kwargs):
        checksums = kwargs.pop('checksums')
        super(MultimediaUpdater, self).__init__(*args, **kwargs)
        self.errors = []
        # Read checksums created prior to import
        with open(checksums, 'rb') as f:
            rows = csv.reader(f)
            next(rows)
            self.checksums = {row[0].lower(): row[1] for row in rows}


    def iterate(self, element):
        """Updates existing EMu record based on data from catalog"""
        rec = self.parse(element)
        # Verify checksums for primary and supplementary files
        files = self.multimedia.get(int(rec('irn')))
        for media in files:
            if media.checksum != self.checksums.get(media.filename.lower()):
                self.errors.append(Error(media.filename, 'Checksum mismatch'))
        # Update record from ecatalogue (but only if match is unique)
        objects = self.find_catalog_objects(rec)
        if len(objects) == 1:
            self.update_record(rec, objects[0])
            # Make attachments in ecatalogue
            attached = objects[0].record.get('MulMultiMediaRef_tab', 'irn')
            cat_irn = objects[0].irn
            mul_irn = rec('irn')
            if mul_irn not in attached:
                self.records.setdefault('ecatalogue', {}) \
                            .setdefault(cat_irn, {'irn': cat_irn}) \
                            .setdefault('MulMultiMediaRef_tab(+)', []) \
                            .append(mul_irn)


    def finalize(self):
        """Converts and expands records to prepare them for writing"""
        for key, module in self.records.iteritems():
            for irn, rec in module.iteritems():
                rec = self.container(rec).expand()
                self.records[key][irn] = rec
        # Write checksum problems to file
        if self.errors:
            with open('errors.txt', 'wb') as f:
                for error in self.errors:
                    f.write('{}\t{}\n'.format(*error))
        else:
            print 'No errors found!'
