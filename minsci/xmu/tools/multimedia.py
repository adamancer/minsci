"""Contains helper functions for importing, matching, and organizing
multimedia in EMu"""

import cPickle as pickle
import csv
import hashlib
import glob
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import Tkinter
from collections import namedtuple
from copy import copy
from datetime import datetime

from lxml import etree
from PIL import Image, ImageTk
from scandir import walk

from ..deepdict import MinSciRecord
from ...geotaxa import GeoTaxa
from ..xmu import XMu, write
from ...helpers import (cprint, dedupe, prompt, oxford_comma,
                        parse_catnum, format_catnums)


# TODO: Tune match function
# TODO: Tune describe function



# FIXME: Confirm overwriting behavior for multiple source files
# FIXME: Handling multiple source files when used as input, not reference.
#        Or should multimedia always be given as a file, and never a dir?


# Objects that (1) are sometimes found in the cut field and
# (2) represent a whole object, not a setting. Entries in this
# list are processed in the order they appear.
OBJECTS = [
    'box',
    'bead',
    'bowl',
    'bottle',
    'cup',
    'pendant',
    'sphere',
    'urn',
    'vase',
    'carved',
    'carving'
]


PAIRS = [
    ['  ', ' '],
    [',-', ', '],
    [' med ', ' medium '],
    [' shaped', '-shaped'],
    ['off white', 'off-white'],
    ['play of color', 'play-of-color'],
    ['light medium', 'light-to-medium'],
    ['light to medium', 'light-to-medium'],
    ['light dark', 'light-to-dark'],
    ['light to dark', 'light-to-dark'],
    ['medium light', 'medium-to-light'],
    ['medium to light', 'medium-to-light'],
    ['medium dark', 'medium-to-dark'],
    ['medium to dark', 'medium-to-dark'],
    ['dark light', 'dark-to-light'],
    ['dark to light', 'dark-to-light'],
    ['medium light', 'medium-to-light'],
    ['medium to light', 'medium-to-light']
]

VALID_COLLECTIONS = [
    'Behind the scenes (Mineral Sciences)',
    'Collections objects (Mineral Sciences)',
    'Documents and data (Mineral Sciences)',
    'Exhibit (Mineral Sciences)',
    'Field pictures (Mineral Sciences)',
    'Inventory (Mineral Sciences)',
    'Macro photographs (Mineral Sciences)',
    'Micrographs (Mineral Sciences)',
    'Non-collections objects (Mineral Sciences)',
    'Pretty pictures (Mineral Sciences)',
    'Research pictures (Mineral Sciences)',
    'Unidentified objects (Mineral Sciences)'
]

COLLECTION_MAP = {
    'Behind the Scenes' : 'Behind the scenes',
    'Catalog Cards': 'Documents and data',
    'Datasets': 'Documents and data',
    'Demonstrations': 'Behind the scenes',
    'Documentation': 'Documents and data',
    'Exhibit': 'Exhibit',
    'Inventory': 'Inventory',
    'Ledgers': 'Documents and data',
    'Logs': 'Documents and data',
    'Maps': 'Documents and data',
    'Micrographs': 'Micrographs',
    'Miscellaneous': '',
    'Other': '',
    'Pretty Pictures': 'Pretty pictures',
    'Publications': 'Documents and data',
    'Research': 'Research pictures',
    'Specimens': '',
    'Meteorite Datapacks': 'Documents and data'
}

KW_WHITELIST = [
    'Allure of Pearls',
    'Blue Room',
    'Splendor of Diamonds',
    'Micrograph, cross-polarized light',
    'Micrograph, plane-polarized light',
    'Micrograph, reflected light'
]


# Define named tuples used herein
Media = namedtuple('Media', ['irn', 'filename', 'md5', 'is_primary'])
MetaField = namedtuple('MetadataField', ['field', 'length', 'xmu', 'exiftool'])
MinSciObject = namedtuple('MinSciObject', ['irn',
                                           'catnum',
                                           'field_nums',
                                           'xname',
                                           'name',
                                           'division',
                                           'catalog',
                                           'collections',
                                           'primary_taxon',
                                           'taxa',
                                           'locality',
                                           'country',
                                           'state',
                                           'setting',
                                           'cut',
                                           'weight',
                                           'lot',
                                           'status',
                                           ])

ObjectSummary = namedtuple('ObjectSummary', ['title', 'caption', 'keywords'])


class Multimedia(XMu):
    """Tools to check multimedia import"""

    def __init__(self, *args, **kwargs):
        # Get optional keywords
        #catpath = kwargs.pop('catpath', None)
        super(Multimedia, self).__init__(*args, **kwargs)
        self.defaults = {
            'DetRights': ('This image was obtained from the Smithsonian'
                          ' Institution. Its contents may be protected by'
                          ' international copyright laws.')
        }
        # Read data from existing multimedia
        self.existing = {}
        #self.fast_iter(report=10000)


    def iterread(self, element):
        """Reads basic file info from EMu export

        Use this function to test imports against the checksum file created
        by self.check_and_write() or to find existing multimedia records
        """
        rec = self.read(element).unwrap()
        irn = rec('irn')
        primary = (rec('MulIdentifier'), rec('ChaMd5Sum'))
        supp = [(fn, h) for fn, h in zip(rec('SupIdentifier_tab'),
                                         rec('SupMD5Checksum_tab'))]
        fn, h = primary
        self.existing.setdefault(fn, []).append(Media(irn, fn, h, True))
        for fn, h in supp:
            self.existing.setdefault(fn, []).append(Media(irn, fn, h, False))


    def iterlink(self, element):
        """Matches and makes links between media to catalog

        Use this function to match multimedia to catalog records
        """
        rec = self.read(element).unwrap()
        mulirn = rec('irn')
        # Use catalog number in title field to find matching catalog record(s)
        catirns = self.find_objects(rec)
        if len(catirns) == 1:
            self.update_media(rec, catirn)
        # Write import files for ecatalogue and emultimedia
        xmu.write('ecatalogue.xml', catalog, 'ecatalogue')
        xmu.write('emultimedia.xml', multimedia, 'emultimedia')


    def verify_checksums(self, records, checksums='checksums.txt'):
        """Check checksums in record set against list of checksums

        Args:
            records (list): list of xmu.DeepDict objects
            checksums (str): path to checksum file
        """
        with open('checksums.txt', 'rb') as f:
            rows = csv.reader(f)
            next(rows)
            self.checksums = {row[0]: row[1] for row[0], row[1] in rows}
        errors = []
        for fn, media in records.iteritems():
            if len(media) > 1:
                errors.append(fn)
            else:
                m = media[0]
                if m.checksum != self.checksums.get(m.filename):
                    errors.append(fn)
        # Write any errors to file
        if errors:
            with open('errors.txt', 'wb') as f:
                f.write('\n'.join(errors))
        else:
            print 'No errors found!'


    def check_and_write(self, records, fp='import.xml',
                        checksums='checksums.txt'):
        """Checks records for errors and records checksums

        Args:
            records (list): list of xmu.DeepDict objects
            fp (str): path to import file
            checksums (str): path to checksum file
        """
        checked = []
        self.checksums = {}
        for rec in records:
            if self._check_record(rec):
                checked.append(rec)
        if len(checked) == len(records):
            print 'All records checked out'
        else:
            print 'Errors found'
        # Record checksums
        with open(checksums, 'wb') as f:
            writer = csv.writer(f)
            writer.writerow(['Filename', 'MD5'])
            for row in self.checksums.iteritems():
                writer.writerow(row)
        write(fp, checked, 'emultimedia')


    def combine(self, rec, fields):
        combined = []
        for field in fields:
            val = rec(field)
            if val and not isinstance(val, list):
                combined.append(val)
            elif val:
                combined.extend(val)
        return combined


    def hash_image(self, fp):
        """Get MD5 hash of a full image file

        Args:
            fp (str): path to image

        Returns:
            Tuple with (filename, hash)
        """
        return os.path.basename(fp), self._hash(open(fp, 'rb'))


    def _check_record(self, rec):
        """
        Returns:
            Dict of record data if record is okay, otherwise False
        """
        # Hash all files
        for fp in self.combine(rec, ['Multimedia', 'Supplementary_tab']):
            try:
                fn, h = self.hash_image(fp)
            except IOError:
                self.logfile.write('Error: {}: Not found\n'.format(fp))
                #return False
            else:
                try:
                    self.checksums[fn]
                except KeyError:
                    self.checksums[fn] = h
                else:
                    print '{} already exists!'.format(fn)
                    return False
        # Assign defaults if key empty or not found
        for field, default in self.defaults.iteritems():
            if not rec(field):
                rec[field] = default
        rec = rec.expand()
        return rec


    def _hash(self, f, size=8192):
        """Generate md5 hash for a file

        Args:
            f (file): stream of file to hash
            size (int): size of block. Should be multiple of 128.

        Return:
            Tuple of (filename, hash)
        """
        if size % 128:
            raise ValueError('size must be a multiple of 128')
        h = hashlib.md5()
        while True:
            chunk = f.read(size)
            if not chunk:
                break
            h.update(chunk)
        return h.hexdigest()


    def update_media(self, rec, catirn):
        metadata = self.objects[catirn]
        # Update descriptive metadata
        title = rec('MulTitle')
        if (not title
            or title.startswith('Mineral Sciences') and title.endswith('Photo')
            or title.endswith('[AUTO]')):
            title = metadata.title + ' [AUTO]'
        description = rec('MulDescription')
        if (not description or description.endwith('[AUTO]')):
            description = metadata.caption + ' [AUTO]'
        # Update keywords, keeping any keywords in the original record that
        # are in KW_WHITELIST
        keywords = (metadata.keywords + [kw for kw in rec('DetSubjects_tab')
                                         if kw in KW_WHITELIST])
        # Update collection list to reflect that this is a collections object
        collections = rec('DetCollectionName_tab')
        collections = [COLLECTION_MAP.get(coll, coll) for coll in collections]
        coll = 'Micrographs (Mineral Sciences)'
        if 'micrograph' in title and not coll in collections:
            collections.append(coll)
        # Note any non-SI objects in photos
        coll_object = 'Collections objects (Mineral Sciences)'
        ext_object = 'Non-collections object (Mineral Sciences)'
        if metadata.obj.status != 'active':
            rights = ('One or more objects depicted in this image are not'
                      ' owned by the Smithsonian Institution.')
            collections.append(ext_object)
            try:
                collections.remove(coll_object)
            except ValueError:
                pass
        else:
            collections.append(coll_object)
            try:
                collections.remove(ext_object)
            except ValueError:
                pass

        collections = dedupe(collections)
        # Updated related
        related = rec('DetRelation_tab')
        # Update note
        note = rec('NotNote').split(';')
        for i, val in enumerate(note):
            if val.strip().startswith('Linked:'):
                note[i] = ' Linked: Yes'
                break
        else:
            note.append(' Linked: Yes')
        note = ';'.join(note)
        # Add to output
        update = self.container({
            'MulTitle': title,
            'MulDescription': description,
            'DetSubjects_tab': keywords,
            'DetCollectionName_tab': collections,
            'DetRelation_tab': related,
            'DetRights': rights,
            'NotNote': note
        })
        # FIXME: Fix case where rec(field) is empty but val is not
        for key in rec:
            val = update.get(key)
            if val is None or val == rec(key):
                del update[key]
        if update:
            update['irn'] = irn
            self.records.append(update.expand())


    '''
    def find_objects(self, element=None, rec=None):
        """Find catalog records matching data in specified field"""
        rec = self.read(element).unwrap()
        irn = rec('irn')
        val = rec(self.field)
        mm = rec('Multimedia')
        self.n += 1
        if os.path.splitext(mm)[1].lower() != '.jpg':
            print '{} is not a JPEG'.format(os.path.basename(mm))
            return True
        print 'FILE #{:,}'.format(self.n)
        try:
            im = Image.open(mm)
        except:
            print '{} skipped'.format(os.path.basename(mm))
            return True
        else:
            im.thumbnail((640,640), Image.ANTIALIAS)
            tkim = ImageTk.PhotoImage(im)
            self.panel = Tkinter.Label(self.root, image=tkim)
            self.panel.place(x=0, y=0, width=640, height=640)
            try:
                self.old_panel.destroy()
            except AttributeError:
                pass
            except:
                raise
            self.old_panel = self.panel
            self.root.title(val)

        catnums = format_catnums(parse_catnum(val), code=False)
        catirns = []
        n = len(self.field)
        for catnum in catnums:
            # Set up options for user to select from
            other = ['No match']
            if catnum == catnums[0]:
                other = ['No match', 'Write import']
            matches = match(catnum, self.catalog)
            # Check to see if this irn has already been added. This can
            # happen with Antarctic meteorites when the catnum function
            # finds both a catalog number and meteorite number.
            if len([m for m in matches if m[0] in catirns]):
                print 'Term already matched'
                matches = []
            if len(matches):
                print '-' * 60
                print '{}: {}'.format(self.field, val)
                print 'Term:{} {}'.format(' '*(n-4), catnum)
                caption = rec('MulDescription')
                if bool(caption):
                    print 'Caption: ' + ''.join([c if ord(c) <= 128 else '_'
                                                 for c in caption])
                notes = rec('NotNotes').split(';')
                for i in xrange(len(notes)):
                    note = notes[i]
                    if note.lower().startswith('slide data'):
                        note = u'Note:{} {}'.format(' '*(n-4),
                                                    note.split(':')[1].strip())
                        # Semicolons within notes--blech
                        while not note.strip().endswith('"'):
                            try:
                                note += notes[i+1]
                            except IndexError:
                                break
                            else:
                                i += 1
                        print ''.join([c if ord(c) <= 128 else '_'
                                       for c in note])
                        break
                options = other + sorted([m[1] for m in matches])
                m = prompt('Select best match:', options)
                try:
                    catirn = [rec[0] for rec in matches if rec[1] == m][0]
                except IndexError:
                    if m == 'Write import':
                        return False
                else:
                    catirns.append(catirn)
                    try:
                        irns = self.links[catirn]
                    except KeyError:
                        pass
                    else:
                        print 'Existing irns: {}'.format(', '.join(irns))
                        if irn in irns:
                            continue
                    cprint(('Multimedia record {} added to'
                            ' catalog record {}').format(irn, catirn))
                    try:
                        self.results[catirn].append(irn)
                    except KeyError:
                        self.results[catirn] = [irn]
        n = 1
        m = 5
        while True:
            try:
                os.remove(mm)
            except OSError:
                if n > 5:
                    return False
                cprint('Could not remove {}'.format(mm))
                time.sleep(2)
                print 'Retrying ({}/{})...'.format(n, m)
                n += 1
            else:
                break
        return True
    '''




    def test_object(self, element):
        """Test if multimedia record is a specimen photo"""
        rec = self.read(element).unwrap()
        irn = rec('irn')
        resource_type = rec('DetResourceType').lower()
        if resource_type != 'specimen/object':
            self.is_object[irn] = False
        else:
            self.is_object[irn] = True


    def find_objects(self, element=None, rec=None):
        if element is None:
            rec = self.read(element).unwrap()
        parsed = parse_catnum(rec('MulTitle'))
        matches = []
        for _id in [self.container(_id) for _id in parsed]:
            catnum = _id.get_identifier(include_code=False, force_catnum=True)
            metnum = _id.get_identifier(include_code=False)
            indexes = [idx for idx in set([catnum, metnum]) if idx]
            for idx in indexes:
                idx = idx.upper()
                try:
                    primary, suffix = re.split('[-,]', idx)
                except IndexError:
                    primary = index
                    suffix = None
                try:
                    irns = self.lookup[primary][suffix]
                except KeyError:
                    irns = []
                else:
                    break
            matches.append(irns)





class Embedder(Multimedia):
    """Embeds data from EMu record into file using exiftool"""

    def __init__(self, *args, **kwargs):
        # Pop keywords needed below
        dirpath = kwargs.pop('dirpath', None)
        metadata_fields = kwargs.pop('metadata_fields', None)
        kwargs['module'] = 'emultimedia'  # force module of emultimedia
        # Use emultimedia as the default module
        super(Embedder, self).__init__(*args, **kwargs)
        # Set directory for writing images
        if dirpath is None:
            raise Exception('dirpath keyword argument is required')
        try:
            os.makedirs(dirpath)
        except OSError:
            pass
        self.dirpath = dirpath
        # Update metadata field map with data from kwarg
        self.metadata_fields = {
            'Headline': MetaField('Headline', 64,
                                  get_headline,
                                  'Headline'),
            'Title': MetaField('Document Title', 64,
                               get_title,
                               'Title'),
            'Caption-Abstract': MetaField('Description', 2000,
                                          'MulDescription',
                                          'Caption-Abstract'),
            'CopyrightNotice': MetaField('Copyright Notice', 128,
                                         'DetRights',
                                         'CopyrightNotice'),
            'Source': MetaField('Source', 64,
                                'DetSource',
                                'Source'),
            'Creator': MetaField('Creator', 64,
                                 'MulCreator_tab',
                                 'Creator'),
            'DateCreated': MetaField('Date', 64,
                                     get_date,
                                     'DateCreated'),
            'Keywords': MetaField('Keywords', 64,
                                  'DetSubject_tab',
                                  'Keywords'),
            'Credit': MetaField('Credit/Provider', 64,
                                get_short_credit,
                                'Credit'),
            'JobID': MetaField('Job Identifier', 64,
                               'AdmImportIdentifier',
                               'JobID'),
            'Special Instructions': MetaField('Instructions', 256,
                                              get_full_credit,
                                              'SpecialInstructions')
        }
        if metadata_fields is not None:
            self.metadata_fields.update(metadata_fields)
        # Read existing data
        self.existing = {}
        self.fast_iter(self.iterread, report=5000)
        # Initialize class-wide attributes used for logging, etc.
        self.records = []
        self.tmpfile = tempfile.NamedTemporaryFile()
        self.logfile = open('embedder.log', 'wb')


    def iterate(self, element):
        return self.embed(element)


    def embed(self, element):
        """Embed metadata and write an EMu import file"""
        rec = self.read(element).unwrap()
        emu_rec = self.container({'irn': rec('irn')})
        # Check main multimedia file
        fp = rec('Multimedia')
        if fp is not None:
            result = self.embed_metadata(fp, rec)
            if result:
                emu_rec['Multimedia'] = result
            else:
                return True
        # Check supplementary files
        supp = rec('Supplementary_tab')
        if supp is not None:
            for i, fp in enumerate(supp):
                result = self.embed_metadata(fp, rec)
                if result:
                    emu_rec.setdefault('Supplementary_tab', []).append(result)
                else:
                    return True
        # Add to import
        self.records.append(emu_rec.expand())



    def embed_metadata(self, fp, rec):
        """Embed metadata in an image file

        Args:
            fp (str): path of file in which to embed metadata
            rec (xmu.DeepDict): metadata for media file

        Returns:
            Boolean indicating whether embed succeeded
        """
        # Copy and hash image data from original file
        fn = os.path.basename(fp)
        print 'Embedding metadata into {}...'.format(fn)
        dst = os.path.join(self.dirpath, fn)
        try:
            open(dst, 'rb')
        except IOError:
            pass
        else:
            self.logfile.write('Info: {}: Already exists\n'.format(fp))
            return dst
        h1 = self.hash_image_string(fp)
        shutil.copy2(fp, dst)
        # Use exiftool to embed metadata in file
        metadata = self.get_metadata(rec)
        cmd = ['exiftool', '-overwrite_original', '-v']
        [cmd.extend(['-{}={}'.format(key, val)]) for key, val in metadata]
        cmd.append(dst)
        return_code = subprocess.call(cmd, cwd=os.getcwd(), stdout=self.tmpfile)
        if return_code:
            self.logfile.write('Error: {}: Bad return code ({})\n'.format(
                fp, return_code))
        # Check temporary log for errors
        result = self._parse_log(self.tmpfile)
        if not '1 image files updated' in result:
            self.logfile.write('Error: {}: Embed failed\n'.format(fp))
            return False
        # Check modified file
        h2 = self.hash_image_string(dst)
        if h1 == h2:
            self.logfile.write('Info: {}: Embed succeeded\n'.format(fp))
            return dst
        else:
            self.logfile.write('Error: {}: Hash check failed\n'.format(fp))
            return False


    def hash_image_string(self, fp):
        """Returns hash based on image data

        Args:
            fp (str): path to image file

        Returns:
            Hash of image data as string
        """
        # FIXME: Output directory is hardcoded
        try:
            return hashlib.md5(Image.open(fp).tobytes()).hexdigest()
        except IOError:
            # Encountered a file format that PIL can't handle. Convert
            # file to something usable, hash, then delete the derivative.
            print 'Hashing jpeg derivative...'
            fn = os.path.basename(fp)
            jpeg = os.path.splitext(fn)[0] + '.jpg'
            cmd = 'iconvert "{}" "{}"'.format(fp, jpeg)  # FIXME
            return_code = subprocess.call(cmd, cwd=r'D:\embedded')
            if return_code:
                self.logfile.write('Error: {}: Bad return code ({})\n'.format(
                    fp, return_code))
            dst = os.path.join(r'D:\embedded', jpeg)
            h = hashlib.md5(Image.open(dst).tobytes()).hexdigest()
            os.remove(dst)
            return h


    def get_metadata(self, rec, include_empty=False):
        """Maps EMu multimedia data to IPTC fields as used by exiftool"""
        metadata = []
        for prop in self.metadata_fields.values():
            field = prop.exiftool.lower()
            # prop.xmu can be either an EMu field or a function
            try:
                val = prop.xmu(rec)
            except TypeError:
                val = rec(prop.xmu)
            if isinstance(val, list):
                for s in val:
                    if len(s) > prop.length:
                        warn = ('Warning: {} is too long ({}/{}'
                                ' characters)').format(prop.exiftool, len(s),
                                                       prop.length)
                        self.logfile.write('{}: {}\n'.format(fp, warn))
                    metadata.append((field, s))
            else:
                if len(val) > prop.length:
                    warn = ('Warning: {} is too long ({}/{}'
                            ' characters)').format(prop.exiftool, len(s),
                                                   prop.length)
                    self.logfile.write('{}: {}\n'.format(fp, warn))
                metadata.append((field, val))
        # Remove empty fields if not needed
        if not include_empty:
            metadata = [(key, val) for key, val in metadata if val]
        return metadata


    def _parse_log(self, f):
        """Parses success/failure info from exiftool log"""
        result = []
        f.seek(0)
        for line in f:
            line = line.strip()
            if line.startswith('========'):
                result.append(line.split(' ', 1)[1])
            elif line.endswith('updated'):
                result.append(line)
        f.seek(0)
        return ': '.join(result)




class CataMedia(XMu):
    """Facilitates adding image metadata and linking multimedia to catalog

    Attributes:
        objects (dict): contains object data
    """

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.objects = {}
        self._catnum_lookup = {}     # used by self.find_objects()
        self._media_lookup = {}      # used by self.find_depicted()
        self._all_linked_media = {}  # used by self.find_linked_media


    def iterate(self, element):
        """Reads object data and creates lookups to use with multimedia"""
        rec = self.read(element).unwrap()
        # Add data to lookups
        self._create_catalog_lookup(rec=rec)
        self._create_media_lookups(rec=rec)
        # Summarize object data
        obj = self.prep_object(rec)
        caption = self.set_caption(obj)
        keywords = self.set_keywords(obj)
        tags = self.set_tags(obj)
        summary = self.set_summary(obj, caption, tags)
        self.objects[irn] = ObjectSummary(object=obj,
                                          caption=cation,
                                          keywords=keywords,
                                          summary=summary)


    def prep_object(self, rec):
        """Clean and return object data from an EMu record"""
        # Basic specimen info
        irn = rec('irn')
        catnum = rec.get_identifier()
        field_nums = rec.get_field_numbers()
        xname = rec.get_name(taxa)
        name = rec('MinName') if rec('MinName') else rec('MetMeteoriteName')
        taxa = rec.get_classification()
        division = rec('CatDivision')
        catalog = rec('CatCatalog')
        collections = rec('CatCollectionName_tab')
        kind = catalog.split(' ', 1)[0]
        status = rec('SecRecordStatus').lower()
        # Locality info
        location = rec('LocPermanentLocationRef', 'SummaryData')
        country = rec('BioEventSiteRef', 'LocCountry')
        state = rec('BioEventSiteRef', 'LocProvinceStateTerritory')
        county = rec('BioEventSiteRef', 'LocDistrictCountyShire')
        # Gem/mineral info
        setting = rec('MinJeweleryType')
        cut = rec('MinCut')
        color = rec('MinColor_tab')
        lot = rec('BioLiveSpecimen')
        weight = rec('MeaCurrentWeight')
        unit = rec('MeaCurrentUnit')
        # Media info
        multimedia = rec('MulMultiMediaRef_tab', 'irn')
        # Set title. This should use the catalog number from the multimedia
        # record, not the catalog record being matched to.
        title = u'{} '.format(xname)
        # Set caption for gem/mineral
        caption = []
        if cut or setting:
            make_plural = ['bead']
            # Derive setting from cut, if necessary
            cut = cut.lower()
            if not setting:
                for term in OBJECTS:
                    for s in (singular(term), plural(term)):
                        # Check for an exact object
                        if s in cut:
                            setting = s
                            if s == term and term != 'carved':
                                cut = ''
                            break
            cut = cut.lower()
            if cut in make_plural:
                cut = plural(cut)
            if cut.endswith(' cut'):
                cut = cut[:-4]
            # Format setting
            if setting in make_plural:
                setting = plural(setting)
            if setting in cut:
                setting = ''
            setting = setting.lower().rstrip('. ')
        # Format color
        if color:
            color = oxford_comma(color[0].lower().split(','), False)
        # Format taxa
        taxon = ''
        if any(taxa):
            taxon = self.gt.item_name(taxa).split(' with ').pop(0).strip()
        # Add weight
        weight_unit = ''
        if weight and unit:
            weight_unit = u'{} {}'.format(weight.rstrip('0.'), unit.lower())
        # Locality string
        locality = [county, state, country]
        locality = ', '.join([s for s in locality if bool(s)])
        return MinSciObject(irn=irn,
                            catnum=catnum,
                            field_nums=field_nums,
                            xname=xname,
                            name=name,
                            division=division,
                            catalog=catalog,
                            collections=collections,
                            primary_taxon=taxon,
                            taxa=taxa,
                            locality=locality,
                            country=country,
                            state=state,
                            setting=setting,
                            cut=cut,
                            weight=weight_unit,
                            lot=lot,
                            status=status)


    def set_caption(self, obj):
        """Derive a caption based on object data"""
        caption = []
        if obj.cut or obj.setting:
            if 'beads' in obj.cut or 'crystal' in obj.cut:
                caption.append(u'{} of'.format(obj.cut))
            elif 'carv' in obj.cut and not 'carving' in obj.setting:
                caption.append(u'carved')
            else:
                caption.append(u'{}-cut'.format(obj.cut))
            # Distinguish carved objects like bowls and spheres
            if obj.setting and not ('carv' in obj.cut and 'carv' in obj.setting):
                if obj.setting.rstrip('s') in OBJECTS[:-2]:
                    caption.append(u'{}'.format(obj.setting))
                else:
                    caption.append(u'in {}{}'.format(add_article(obj.setting)))
            # Format color
            if obj.color:
                caption.append(u'{}'.format(obj.color))
            # Format taxa
            if any(obj.taxa):
                taxon = self.gt.item_name(obj.taxa).split(' with ').pop(0).strip()
                caption.append(u'{}'.format(taxon[0].lower() + taxon[1:]))
            # Add weight
            if obj.weight:
                if lot.lower().startswith(('set', 'with')) or obj.setting:
                    caption.append(u'({})'.format(obj.weight))
                else:
                    caption.append(u'weighing {}'.format(obj.weight))
            # Handle lots
            if obj.lot:
                lot = lot.lower()
                if lot.startswith(('set', 'with')):
                    caption.append(u'{}'.format(lot))
                else:
                    caption.append(u'. Lot described as "{}."'.format(
                        lot.replace('"',"'").strip()))
            # Format caption
            caption[0] = caption[0][0].upper() + caption[0][1:]
            if obj.name:
                caption.insert(0, obj.name)
            caption = ' '.join(caption).replace(' .', '.')
            if not caption.endswith('"') and not caption.endswith('.'):
                caption += '.'
            # Mark inactive records
            if obj.status != 'active':
                status = obj.status
                if status == 'inactive':
                    status = 'made inactive'
                caption += (' The catalog record associated with this'
                            'specimen has been {}.').format(status)
            # Neaten up the color modifiers in the caption
            for s1, s2 in PAIRS:
                caption = caption.replace(s1, s2)
        else:
            # Provide less detailed caption for rocks and minerals
            caption.append(obj.xname)
            if obj.locality:
                caption.append(u'from {}'.format(obj.locality))
        return ' '.join(caption)


    def set_keywords(self, obj):
        """Set multimedia keywords for the given object"""
        keywords = [obj.kind]
        if obj.setting:
            keywords.append(obj.setting)
        if any(taxa):
            try:
                keywords.extend(self.gt.clean_taxa(taxa, dedupe=True))
            except:
                print taxa
                raise
        keywords.append(country)
        if country.lower().startswith('united states') and state:
            keywords.append(state)
        keywords = [s[0].upper() + s[1:] for s in keywords
                    if s and not 'unknown' in s.lower()]


    def set_tags(self, obj):
        """Set tags with special information useful in identifying objects"""
        tags = []
        if collection and 'polished thin' in obj.collection[0].lower():
            tags.append('PTS')
        if 'GGM' in obj.location.upper():
            tags.append('GGM')
        elif 'POD 4' in obj.location.upper():
            tags.append('POD 4')
        return tags


    def set_summary(self, obj, caption, tags):
        """Summarizes obkect data"""
        if obj.catnum is not None:
            summary = ['{} {}:'.format(obj.division, obj.catnum), caption]
        else:
            summary = [obj.division + ':', caption]
        if tags:
            summary.append(u'[{}]'.format(','.join(tags)))
        return ' '.join(summary)


    def _create_catalog_lookup(self, element=None, rec=None):
        """Create catalog number lookup"""
        if rec is None:
            rec = self.read(element).unwrap()
        irn = rec('irn')
        catnum = rec.get_identifier(include_code=False, force_catnum=True)
        metnum = rec.get_identifier(include_code=False)
        for index in set([catnum, metnum]):
            index = index.upper()
            try:
                primary, suffix = re.split('[-,]')
            except IndexError:
                primary = index
                suffix = None
            self._catnum_lookup.setdefault(primary, {})\
                               .setdefault(suffix, []).append(irn)


    def _create_media_lookups(self, element=None, rec=None):
        """Create lookups linking media to catalog records"""
        if rec is None:
            rec = self.read(element).unwrap()
        cat_irn = rec('irn')
        multimedia = rec('MulMultiMediaRef_tab', 'irn')
        self._all_linked_media.extend(multimedia)
        for mul_irn in multimedia:
            self._media_lookup.setdefault(mul_irn, []).append(cat_irn)


    def find_object(self, catnum):
        """Finds catalog records that match a given catalog number"""
        try:
            primary, suffix = re.split('[-,]')
        except IndexError:
            primary = index
            suffix = None
        return self._catnum_lookup.get(primary, {}).get(suffix, [])


    def find_depicted(self, mul_irn):
        """Finds catalog records that link to a given multimedia record"""
        return self._media_lookup.get(mul_irn)


    def find_linked_media(self, mul_irn):
        """Tests if a given multimedia record is linked in catalog"""
        return mul_irn in self._all_linked_media


    def organize_multimedia(self, element):
        """Sort specimen images to top of catalog multimedia list"""
        rec = self.read(element).unwrap()
        catirn = rec('irn')
        orig = rec('MulMultiMediaRef_tab', 'irn')
        multimedia = []
        bumped = []
        for irn in orig:
            if not irn in multimedia+bumped:
                try:
                    is_object = self.is_object[irn]
                except:
                    # This is dangerous--anything not in the multimedia
                    # lookup will be removed. This means that organize
                    # shouldn't be run on partial multimedia reports,
                    # which is not ideal. Of course, this also means
                    # retired records will be automcaitcally detached,
                    # which might be fine.
                    self.warning = True
                    return False
                else:
                    if is_object:
                        multimedia.append(irn)
                    else:
                        bumped.append(irn)
            else:
                print 'Duplicate in {}'.format(orig)
        multimedia += bumped
        if multimedia != orig:
            self.update[catirn] = {
                'irn': catirn,
                'MulMultiMediaRef_tab': multimedia
                }


def get_objects(rec):
    """Parse list of catalog numbers from MulTitle"""
    catnums = parse_catnum(rec('MulTitle'), prefixed_only=True)
    return format_catnums(catnums)


def get_date(rec):
    """Get modified date of file in Multimedia"""
    return datetime.fromtimestamp(int(os.path.getmtime(rec('Multimedia'))))\
                   .strftime('%Y%d%m')


def get_short_credit(rec):
    """Get short credit line from MulCreator_tab for IPTC Credit field"""
    return '{}, SI'.format(rec('MulCreator_tab')[0])


def get_full_credit(rec):
    """Get credit line for IPTC Instructions field"""
    creator = oxford_comma(rec('MulCreator_tab'), False)
    contributors = [contrib for contrib in rec('DetContributor_tab')
                    if 'enhanced by ' in contrib]
    credit = ['Credit line: Photo by {}, '
              'Smithsonian Institution'.format(creator)]
    credit.extend(contributors)
    return '. '.join(credit)


def get_title(rec):
    """Get title for IPTC Title field (distinct from Headline)"""
    title = rec.get_guid('Photo number')
    if title is None:
        title = '; '.join(get_objects(rec))
    return title


def get_headline(rec):
    """Get headline for IPTC Headline field"""
    headline = rec.get('MulTitle')
    # Limit to exactly 64 characters
    if len(headline) > 64:
        if '(NMNH' in headline or '(USNM' in headline:
            headline, catnum = headline.rsplit('(', 1)
            n = len(catnum) + 1
            headline = headline[:60-n].rstrip() + '... (' + catnum
        else:
            headline = headline[:61].rstrip() + '...'
    return headline
