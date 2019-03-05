"""Subclass of XMuRecord with methods specific to emultimedia"""
from __future__ import print_function
from __future__ import unicode_literals

from builtins import str
from past.builtins import basestring
import os
import re
import shutil
from collections import namedtuple
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

from unidecode import unidecode

from .xmurecord import XMuRecord
from ..tools.multimedia.embedder import Embedder, EmbedField
from ..tools.multimedia.hasher import hash_file
from ...catnums import get_catnums
from ...helpers import dedupe, format_catnums, oxford_comma, parse_catnum, lcfirst, sort_catnums


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

FORMATS = (
    '.cr2',
    '.dng',
    '.gif',
    '.jp2',
    '.jpg',
    '.jpeg',
    '.png',
    '.tif',
    '.tiff'
    )


MediaFile = namedtuple('MediaFile', ['irn', 'filename', 'path', 'hash', 'size',
                                     'width', 'height', 'is_image', 'row'])

class MediaRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to emultimedia"""

    def __init__(self, *args):
        super(MediaRecord, self).__init__(*args)
        self.module = 'emultimedia'
        self._attributes = ['cataloger', 'embedder', 'fields', 'module']
        #self.cataloger = None
        #self.embedder = None
        self.image_data = {}
        # Attributes used with cataloger
        self.catnums = []
        self.object = None
        self.smart_functions = {
            'MulTitle': self.smart_title,
            'MulDescription': self.smart_caption,
            'DetRelation_tab': self.smart_related,
            'DetSubject_tab': self.smart_keywords,
            'DetCollectionName_tab': self.smart_collections,
            'NotNotes': self.smart_note
        }
        self.defaults = {
            'DetSubject_tab': []
        }
        self.whitelist = KW_WHITELIST
        self.masks = {
            'MulTitle': u'{name} (NMNH {catnum}) [AUTO]'
        }


    def add_embedder(self, embedder, **kwargs):
        """Create an Embedder instance for the MediaRecord"""
        self.embedder = embedder(**kwargs)


    def add_cataloger(self, cataloger):
        """Add a Cataloger instance to the MediaRecord"""
        self.cataloger = cataloger


    def check_filename(self, primary=True):
        """Verifies that filename follows best practices"""
        media = [self.get_primary()] if primary else self.get_all_media()
        for mm in media:
            stem, ext = os.path.splitext(mm.filename)
            matches = re.findall(r'[^a-zA-Z0-9_\-]', stem)
            if matches or ext != ext.lower():
                return False
        return True


    def fix_filename(self, fn=None):
        """Fixes filename to conform with best practices"""
        if fn is None:
            fn = self.get_primary().filename
        stem, ext = os.path.splitext(fn)
        stem = stem.replace('-', '_')
        stem = re.sub(r'\((\d+)\)', r'_\1_', stem)
        stem = re.sub(r'[\s_]+', u'_', unidecode(stem))
        stem = re.sub(r'[^a-zA-Z0-9_]', '', stem)
        print(fn, '=>', stem.rstrip('_') + ext.lower())
        return stem.rstrip('_') + ext.lower()


    def _get_params(self, for_filename=False):
        # Format catalog numbers
        catnums = sort_catnums(self.catnums)
        if len(catnums) > 1:
            mask = '{} and others' if for_filename else '{} and others'
            catnum = mask.format(catnums[0])
        else:
            catnum = catnums[0]
        params = {
            'catnum': catnum,
            'catnum_simple': catnum.replace('NMNH ', '') \
                                   .replace('USNM', '') \
                                   .replace('-00', ''),
            'name': self.object.object['xname'],
            'primary': self.object.object['xname'].split(' with ')[0],
        }
        if for_filename:
            return {k: v.replace(' ', '_') for k, v in params.items()}
        return params


    def set_filename(self, mask):
        params = self._get_params(for_filename=True)
        ext = os.path.splitext(self('Multimedia'))[1]
        self['MulIdentifier'] = mask.format(**params) + ext


    def set_mask(self, key, mask):
        assert isinstance(mask, str)
        self.masks[key] = mask


    def set_default(self, key):
        defaults = {
            'DetSource': self.embedder.source,
            'DetRights': self.embedder.rights
        }
        self[key] = defaults[key]


    def get_all_media(self):
        """Gets the filepaths for all media in this record"""
        return [self.get_primary()] + self.get_supplementary()


    def get_primary(self):
        """Gets properties for the primary asset"""
        filename = self('MulIdentifier')
        if not filename:
            filename = os.path.basename(self('Multimedia'))
        is_image = filename.lower().endswith(FORMATS)
        size = self('ChaFileSize')
        width = self('ChaImageWidth')
        height = self('ChaImageHeight')
        return MediaFile(self('irn'),
                         filename,
                         self('Multimedia'),
                         self('ChaMd5Sum'),
                         int(size) if is_image and size else None,
                         int(width) if is_image and width else None,
                         int(height) if is_image and height else None,
                         is_image,
                         None)


    def get_supplementary(self):
        """Gets supplementary assets and their basic properites"""
        paths = self('Supplementary_tab')
        files = self('SupIdentifier_tab')
        hashes = self('SupMD5Checksum_tab')
        sizes = self('SupFileSize_tab')
        widths = self('SupWidth_tab')
        heights = self('SupWidth_tab')
        supp_files = zip_longest(paths, files, hashes, sizes, widths, heights)
        supplementary = []
        for i, supp_file in enumerate(supp_files):
            path, filename, hexhash, s, w, h = supp_file
            if not filename:
                filename = os.path.basename(path)
            is_image = filename.lower().endswith(FORMATS)
            supplementary.append(MediaFile(self('irn'),
                                           filename,
                                           path,
                                           hexhash,
                                           int(s) if is_image and s else None,
                                           int(w) if is_image and w else None,
                                           int(h) if is_image and h else None,
                                           is_image,
                                           i + 1))
        return supplementary


    def get_catalog_numbers(self, field='MulTitle', **kwargs):
        """Find catalog numbers in the given field"""
        return get_catnums(self(field), **kwargs)


    def get_photo_numbers(self):
        """Gets the photo number"""
        return self.get_matching_rows('Photographer number',
                                      'AdmGUIDType_tab',
                                      'AdmGUIDValue_tab')


    def copy_to(self, path, overwrite=False, verify_image=False):
        """Copies the primary file to a new location

        Args:
            path (str): the directory to copy the image to
            overwrite (bool): specifies whether to overwrite existing file
            verify_master (bool): specifies whether to verify copied file
        """
        primary = self.get_primary()
        try:
            os.makedirs(path)
        except OSError:
            pass
        dst = os.path.join(path, primary.filename)
        try:
            open(dst, 'rb')
        except IOError:
            print('Copying {} to {}...'.format(primary.path, dst))
            shutil.copy2(primary.path, dst)
        else:
            if overwrite:
                print('Copying {} to {}...'.format(primary.path, dst))
                os.remove(dst)
                shutil.copy2(primary.path, dst)
        # Verify the copy if required
        if verify_image and hash_file(dst) != primary.hash:
            raise ValueError('Checksums do not match')
        self['Multimedia'] = dst


    def embed_metadata(self, verify_image=True):
        """Updates metadata in the primary and supplementary images"""
        rec = self.clone(self)
        for media in self.get_all_media():
            # Embed metadata or add a placeholder for non-image files
            fp = media.path
            if media.is_image:
                if verify_image and rec('irn'):
                    self.verify_master(media)
                # Rename file based on MulIdentifier if that is different
                # from the filename in Multimedia
                if media.row is None:
                    new_name = rec('MulIdentifier')
                else:
                    new_name = rec('SupIdentifier_tab')[media.row - 1]
                if fp.endswith(new_name):
                    new_name = None
                fp = self.embedder.embed_metadata(self, fp, new_name)
            if fp and media.row is None:
                rec['Multimedia'] = fp
            elif media.row and rec('irn'):
                rec.setdefault('Supplementary_tab({}=)', []).append(fp)
                if len(rec['Supplementary_tab({}=)']) != media.row:
                    raise ValueError
            else:
                try:
                    rec['Supplementary_tab'][media.row - 1] = fp
                except:
                    print(fp)
                    print(rec['Supplementary_tab'])
                    print(media.row)
                    print(media)
                    raise

        if rec:
            rec['irn'] = media.irn
            return rec.strip_derived().expand()


    def verify_master(self, media=None):
        """Verifies download/copy of master file by comparing hashes"""
        if media is None:
            media = self.get_primary()
        verified = hash_file(media.path) == media.hash
        if not verified:
            raise ValueError('Checksums do not match')
        return verified


    def verify_import(self, images, strict=True, test=False):
        """Verifies import against path"""
        Image = namedtuple('Image', ['path', 'hash'])
        for mm in self.get_all_media():
            matches = images.get(mm.filename, [])
            # Get MD5 hashes and store them for future use
            hashes = {}
            if strict:
                for i, im in enumerate(matches):
                    try:
                        im.hash
                    except AttributeError:
                        try:
                            matches[i] = Image(im, hash_file(im))
                        except IOError:
                            print('File not found: {}'.format(im))
                images[mm.filename] = matches
                hashes = {im.hash: im.path for im in matches}
            # Delete if the filename and hash match (strict) or if
            # the filename exists (not strict)
            ok_to_delete = ((strict and mm.hash in hashes)
                            or (not strict and len(matches) == 1))
            if ok_to_delete:
                fp = hashes[mm.hash] if mm.hash in hashes else matches[0]
            if ok_to_delete and test:
                print('Would delete: {}'.format(fp))
            elif ok_to_delete:
                print('Deleting {}...'.format(fp))
                #os.unlink(paths[0])
            elif strict and mm.hash not in hashes:
                print('Hash mismatch: {}'.format(mm.filename))
            elif not strict and len(matches) != 1:
                print('Non-unique match (n={}): {}'.format(len(matches), fp))
            elif not matches:
                print('File error: No matches found for {}'.format(mm.filename))
            else:
                print('Unknown error: {}'.format(mm.filename))
            # Provide additional info about hashes if strict
            if strict:
                print(' File hash:\n      {}'.format(mm.hash))
                print(' Ref hashes:')
                for i, md5 in enumerate(sorted(hashes)):
                    asterisk = ''
                    if md5 == mm.hash:
                        asterisk = '*'
                    print('  {: >2d}. {}{}'.format(i + 1, md5, asterisk))
                print('-' * 60)


    def match(self, val=None, ignore_suffix=False):
        """Returns list of catalog objects matching data in MulTitle"""
        if val is None:
            val = self('MulTitle')
        parsed = get_catnums(val)
        records = []
        if len(parsed) > 1:
            # Multiple catalog numbers found! Record them all
            for catnum in parsed:
                records.extend(self.match(str(catnum)))
            self.catnums = [str(c) for c in parsed]
        else:
            for identifier in parsed:
                matches = self.cataloger.get(identifier, [], ignore_suffix)
                for match in matches:
                    if not match in records:
                        records.append(match)
            self.catnums = str(parsed)
        if isinstance(self.catnums, basestring):
            self.catnums = [self.catnums]
        return records


    def match_one(self, val=None):
        """Returns a matching catalog object if exactly one match found"""
        matches = self.match(val)
        catnums = [m.object['catnum'] for m in matches]
        matches = [m for i, m in enumerate(matches)
                   if not m.object['catnum'] in catnums[:i]]
        if not matches or len(matches) > 1:
            raise ValueError('No unique match: {}'.format(self.catnums))
        return matches[0]


    def match_and_fill(self, strict=True):
        """Updates record if unique match in catalog found"""
        print('Matching on identifiers in "{}"...'.format(self('MulTitle')))
        self.expand()
        try:
            match = self.match_one()
        except ValueError:
            # The current record includes more than one object. Test if
            # each object resolves, creating a modified enhanced record if so.
            catnums = self.catnums[:]
            matches = []
            for catnum in self.catnums:
                matches.append(self.match_one(catnum).object['irn'])
            else:
                enhanced = self.clone(self)
                enhanced.matches = matches
                enhanced.whitelist = self.whitelist
                enhanced.masks = self.masks
                enhanced.catnums = catnums
                # Set keys for multiple objects
                enhanced['DetResourceType'] = 'Specimen/Object'
                enhanced.setdefault('DetCollectionName_tab', []).append('Collections objects (Mineral Sciences)')
                enhanced['DetRelation_tab'] = ['NMNH {} (1/1)'.format(c)
                                               for c in catnums]
                return enhanced.expand()
        else:
            print('Unique match found! Updating record...')
            enhanced = self.clone(self)
            enhanced.matches = [match.object['irn']]
            enhanced.whitelist = self.whitelist
            enhanced.masks = self.masks
            enhanced.object = match
            enhanced.objects = [match]
            enhanced.catnums = self.catnums
            for key, func in enhanced.smart_functions.items():
                enhanced[key] = func() if func is not None else enhanced(key)
            # Tweak rights statement for non-collections objects
            non_si_coll = 'Non-collections object (Mineral Sciences)'
            if non_si_coll in enhanced.get('DetCollectionName_tab', []):
                enhanced['DetRights'] = ('One or more objects depicted in this'
                                         ' image are not owned by the'
                                         ' Smithsonian Institution.')
            enhanced['DetRelation_tab'] = [rel.replace('(0/', '(1/') for rel
                                           in enhanced['DetRelation_tab']]
            #enhanced['_Objects'] = [match]
            return enhanced.expand()


    def _fill_on_match(self, match):
        print('Unique match found! Updating record...')
        enhanced = self.clone(self)
        enhanced.whitelist = self.whitelist
        enhanced.masks = self.masks
        enhanced.object = match
        enhanced.objects = [match]
        enhanced.catnums = self.catnums
        for key, func in enhanced.smart_functions.items():
            enhanced[key] = func() if func is not None else enhanced(key)
        # Tweak rights statement for non-collections objects
        non_si_coll = 'Non-collections object (Mineral Sciences)'
        if non_si_coll in enhanced.get('DetCollectionName_tab', []):
            enhanced['DetRights'] = ('One or more objects depicted in this'
                                     ' image are not owned by the'
                                     ' Smithsonian Institution.')
        enhanced['DetRelation_tab'] = [rel.replace('(0/', '(1/') for rel
                                       in enhanced['DetRelation_tab']]
        #enhanced['_Objects'] = [match]
        return enhanced.expand()



    def strip_derived(self):
        """Strips fields derived by EMu from the record"""
        strip = [
            'AdmImportIdentifier',
            'ChaImageHeight',
            'ChaImageWidth',
            'ChaMd5Sum',
            'MulIdentifier',
            'MulMimeFormat',
            'SupIdentifier_tab',
            'SupHeight_tab',
            'SupWidth_tab',
            'SupMD5Checksum_tab'
        ]
        strip.extend([key for key in list(self.keys()) if key.startswith('_')])
        for key in strip:
            try:
                del self[key]
            except KeyError:
                pass
        return self


    def smart_title(self):
        """Derives image title from catalog"""
        title = self('MulTitle')
        if (not title
                or (title.startswith('Mineral Sci') and title.endswith('Photo'))
                or title.endswith('[AUTO]')):
            # Use the catnum originally parsed from the title, not the one
            # from the linked record
            params = self._get_params()
            title = self.masks['MulTitle'].format(**params).replace(' ()', ' ')
        return title


    def smart_caption(self):
        """Derives image caption from catalog"""
        description = self('MulDescription')
        if not description or description.endswith('[AUTO]'):
            description = self.object.caption + ' [AUTO]'
        return description


    def smart_keywords(self, whitelist=None):
        """Derives keywords from catalog"""
        if whitelist is None:
            whitelist = self.whitelist
        keywords = self.object.keywords
        keywords.extend([kw for kw in self('DetSubject_tab')
                         if ':' in kw or kw in whitelist])
        keywords.extend(self.defaults['DetSubject_tab'])
        return dedupe(keywords, False)


    def smart_related(self):
        """Populates DetRelation_tab with info about matching catalog records"""
        # Find all catalog records that currently link to this multimedia record
        cat_irns = self.cataloger.media.get(self('irn'), [])
        # Find all catalog records that match this multimedia record
        related = {}
        for obj in self.match():
            linked = 1 if obj.object['irn'] in cat_irns else 0
            related.setdefault(obj.object['catnum'], []).append(linked)
        related = sorted(['{} ({}/{})'.format(catnum, sum(links), len(links))
                          for catnum, links in related.items()])
        return related


    def smart_collections(self):
        """Populates DetCollectionName_tab based on catalog record"""
        collections = self('DetCollectionName_tab') if self else []
        collections = [COLLECTION_MAP.get(c, c) for c in collections]
        # Check if micrograph
        coll = 'Micrographs (Mineral Sciences)'
        if 'micrograph' in self('MulTitle').lower() and not coll in collections:
            collections.append(coll)
        # Check if there are any non-SI objects in photos. Different
        # collections and restrictions are applied for these photos.
        if self('DetResourceType') == 'Specimen/Object':
            si_object = 'Collections objects (Mineral Sciences)'
            non_si_object = 'Non-collections object (Mineral Sciences)'
            if self.object.object['status'] != 'active':
                rights = ('One or more objects depicted in this image are not'
                          ' owned by the Smithsonian Institution.')
                collections.append(non_si_object)
                try:
                    collections.remove(si_object)
                except ValueError:
                    pass
                self['DetRights'] = rights
            else:
                collections.append(si_object)
                try:
                    collections.remove(non_si_object)
                except ValueError:
                    pass
        return dedupe(collections, False)


    def smart_note(self):
        """Updates note based on catalog record"""
        note = self('NotNotes').split(';')
        for i, val in enumerate(note):
            if val.strip().startswith('Linked:'):
                note[i] = 'Linked: Yes'
                break
        else:
            note.append('Linked: Yes')
        return '; '.join(note).strip('; ')




class EmbedFromEMu(Embedder):
    """Tools to embed metadata into a file based on existing data in EMu"""

    def __init__(self, *args, **kwargs):
        super(EmbedFromEMu, self).__init__(*args, **kwargs)
        # Default rights statement
        self.creator = 'Unknown photographer'
        self.rights = ('This image was obtained from the Smithsonian'
                       ' Institution. Its contents may be protected by'
                       ' international copyright laws.')
        self.source = 'NMNH-Smithsonian Institution'
        self.job_id = None
        # Use artwork identifiers to store specimen info
        object_metadata = {
            'object_number': EmbedField('ArtworkSourceInventoryNo', 16,
                                        self.get_object_numbers),
            'object_source': EmbedField('ArtworkSource', 16,
                                        self.get_object_sources),
            'object_url': EmbedField('ArtworkSourceInvURL', 64,
                                     self.get_object_urls),
            'object_title': EmbedField('ArtworkTitle', 64,
                                       self.get_object_titles)
        }
        self.metadata_fields.update(object_metadata)


    def set_job_id(self, job_id):
        """Sets job id manually for images not imported into EMu yet"""
        self.job_id = job_id


    @staticmethod
    def get_objects(rec, field='MulTitle'):
        """Returns list of catalog numbers parsed from MulTitle"""
        catnums = get_catnums(rec(field), prefixed_only=True)
        # FIXME: Only handles one catalog number for now
        if catnums:
            catnums = catnums.__class__(catnums[:1])
        return catnums


    def get_caption(self, rec):
        """Placeholder function returning the caption"""
        return rec('MulDescription')


    def get_copyright(self, rec):
        """Placeholder function returning copyright info"""
        rights = rec('DetRights')
        if not rights:
            return self.rights
        return rights


    def get_creator(self, rec):
        """Placeholder function returning the creator"""
        if not rec('MulCreator_tab'):
            return self.creator
        return rec('MulCreator_tab')
        #return oxford_comma(rec('MulCreator_tab'), False)


    def get_credit_line(self, rec):
        """Returns short credit line"""
        if not rec('MulCreator_tab'):
            creator = self.creator
        else:
            creator = rec('MulCreator_tab')[0]
        return u'{}'.format(creator)


    def get_date_created(self, rec):
        """Placeholder function returning the date created"""
        return self.get_mtime(rec('Multimedia'), '%Y%m%d')


    def get_datetime_created(self, rec):
        """Placeholder function returning the full date and time created"""
        return self.get_mtime(rec('Multimedia'))


    def get_headline(self, rec):
        """Placeholder function returning the headline"""
        headline = rec('MulTitle')
        # Limit to exactly 64 characters
        if len(headline) > 64:
            if '(NMNH' in headline or '(USNM' in headline:
                headline, catnum = headline.rsplit('(', 1)
                len_catnum = len(catnum) + 1
                headline = headline[:60 - len_catnum].rstrip() + '... (' + catnum
            else:
                headline = headline[:61].rstrip() + '...'
        return headline


    def get_inventory_numbers(self, rec):
        """Returns a list of catalog numbers"""
        return self.get_objects()


    def get_job_id(self, rec):
        """Returns the import identifier"""
        job_id = rec('AdmImportIdentifier')
        if not job_id:
            job_id = self.job_id
        return job_id


    def get_keywords(self, rec):
        """Returns a list of keywords"""
        return rec('DetSubject_tab')


    def get_media_topics(self, rec):
        """Returns relevant media topics"""
        pass


    def get_object_name(self, rec, mask='include_code'):
        """Returns the photo identifier or list of pictured objects"""
        object_name = rec.get_guid('Photographer number')
        if object_name is None:
            objects = []
            for obj in self.get_objects(rec):
                obj.set_mask(mask)
                objects.append(obj.from_mask())
            object_name = '; '.join(objects)
        return object_name


    def get_source(self, rec):
        """Returns source of the multimedia file"""
        return rec('DetSource')


    def get_special_instructions(self, rec):
        """Returns long credit line for special instructions"""
        creators = [c if not c.startswith('Unknown') else lcfirst(c)
                    for c in self.get_creator(rec)]
        creator = oxford_comma(creators, False)
        credit = ['Full credit line: Photo by {} provided courtesy of the '
                  'Smithsonian Institution'.format(creator)]
        # Add any photo enhancements logged in EMu
        contributors = [contrib for contrib in rec('DetContributor_tab')
                        if 'enhanced by ' in contrib]
        credit.extend(contributors)
        return '. '.join(credit)


    def get_subjects(self, rec):
        """Returns media topics for this record"""
        subjects = ['medtop:20000727']  # geology
        if 'NMNH G' in rec('MulTitle'):
            subjects.append('medtop:20000012')  # jewellery
        return subjects


    def get_time_created(self, rec):
        """Placeholder function returning the time created"""
        return self.get_mtime(rec('Multimedia'), '%H%M%S%z')


    def get_transmission_reference(self, rec):
        """Returns the import identifier"""
        return self.get_job_id(rec)


    def get_object_numbers(self, rec):
        """Returns list of catalog numbers"""
        obj_data = []
        for obj in rec.objects if hasattr(rec, 'objects') else []:
            obj_data.append(obj.object['catnum'])
        return obj_data


    def get_object_sources(self, rec, source='NMNH-Smithsonian Institution'):
        """Returns list with museum name"""
        return [source] * len(rec.objects if hasattr(rec, 'objects') else [])


    def get_object_titles(self, rec):
        """Returns list of object titles"""
        obj_data = []
        for obj in rec.objects if hasattr(rec, 'objects') else []:
            obj_data.append(obj.object['xname'])
        return obj_data


    def get_object_urls(self, rec):
        """Returns list of object URLs"""
        """Returns list of object titles"""
        obj_data = []
        for obj in rec.objects if hasattr(rec, 'objects') else []:
            obj_data.append(obj.object['url'])
        return obj_data
