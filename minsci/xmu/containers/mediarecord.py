"""Subclass of XMuRecord with methods specific to emultimedia"""

import os
from collections import namedtuple
from itertools import izip_longest

from .xmurecord import XMuRecord
from ..tools.multimedia.embedder import Embedder, EmbedField
from ..tools.multimedia.hasher import hash_file
from ...helpers import dedupe, format_catnums, oxford_comma, parse_catnum


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

FORMATS = ('.cr2', '.gif', '.jpg', '.jpeg', '.png', '.tif', '.tiff')


MediaFile = namedtuple('MediaFile', ['irn', 'filename', 'path', 'hash',
                                     'width', 'height', 'is_image', 'row'])

class MediaRecord(XMuRecord):
    """Subclass of XMuRecord with methods specific to emultimedia"""

    def __init__(self, *args):
        super(MediaRecord, self).__init__(*args)
        self.module = 'emultimedia'
        self._attributes = ['cataloger', 'embedder', 'fields', 'module']
        self.cataloger = None
        self.embedder = None
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


    def add_embedder(self, embedder, **kwargs):
        """Create an Embedder instance for the MediaRecord"""
        self.embedder = embedder(**kwargs)


    def add_cataloger(self, cataloger):
        """Add a Cataloger instance to the MediaRecord"""
        self.cataloger = cataloger


    def get_all_media(self):
        """Gets the filepaths for all media in this record"""
        return [self.get_primary()] + self.get_supplementary()


    def get_primary(self):
        """Gets properties for the primary asset"""
        filename = self('MulIdentifier')
        if not filename:
            filename = os.path.basename(self('Multimedia'))
        is_image = filename.lower().endswith(FORMATS)
        width = self('ChaImageWidth')
        height = self('ChaImageHeight')
        return MediaFile(self('irn'),
                         filename,
                         self('Multimedia'),
                         self('ChaMd5Sum'),
                         int(width) if is_image and width else None,
                         int(height) if is_image and height else None,
                         is_image,
                         None)


    def get_supplementary(self):
        """Gets supplementary assets and their basic properites"""
        paths = self('Supplementary_tab')
        files = self('SupIdentifier_tab')
        hashes = self('SupMD5Checksum_tab')
        widths = self('SupWidth_tab')
        heights = self('SupWidth_tab')
        supp_files = izip_longest(paths, files, hashes, widths, heights)
        supplementary = []
        for i, supp_file in enumerate(supp_files):
            path, filename, hexhash, w, h = supp_file
            if not filename:
                filename = os.path.basename(path)
            is_image = filename.lower().endswith(FORMATS)
            supplementary.append(MediaFile(self('irn'),
                                           filename,
                                           path,
                                           hexhash,
                                           int(w) if is_image and w else None,
                                           int(h) if is_image and h else None,
                                           is_image,
                                           i + 1))
        return supplementary


    def get_catalog_numbers(self, field='MulTitle', **kwargs):
        """Find catalog numbers in the given field"""
        return parse_catnum(self(field), **kwargs)


    def get_photo_numbers(self):
        """Gets the photo number"""
        return self.get_matching_rows('Photographer number',
                                      'AdmGUIDType_tab',
                                      'AdmGUIDValue_tab')


    def embed_metadata(self, verify_master=True):
        """Update metadata in primary and supplementary images"""
        rec = self.clone(self)
        for media in self.get_all_media():
            # Embed metadata or add a placeholder for non-image files
            fp = media.path
            if media.is_image:
                if verify_master:
                    self._verify_master(media)
                fp = self.embedder.embed_metadata(media.path, self)
            if fp and media.row is None:
                rec['Multimedia'] = fp
            elif media.row and rec('irn'):
                rec.setdefault('Supplementary_tab({}=)', []).append(fp)
                if len(rec['Supplementary_tab({}=)']) != media.row:
                    raise ValueError
            else:
                rec['Supplementary_tab'][media.row - 1] = fp
        if rec:
            rec['irn'] = media.irn
            return rec.strip_derived().expand()


    @staticmethod
    def _verify_master(media):
        """Check if download is master by comparing hashes"""
        if hash_file(media.path) != media.hash:
            raise ValueError('Checksums do not match')


    def match(self):
        """Returns list of catalog objects matching data in MulTitle"""
        parsed = parse_catnum(self('MulTitle'))
        records = []
        for identifier in parsed:
            matches = self.cataloger.get(identifier, [])
            for match in matches:
                if not match in records:
                    records.append(match)
        self.catnums = format_catnums(parsed)
        return records


    def match_one(self):
        """Returns a matching catalog object if exactly one match found"""
        matches = self.match()
        catnums = [m.object['catnum'] for m in matches]
        matches = [m for i, m in enumerate(matches)
                   if not m.object['catnum'] in catnums[:i]]
        if not matches or len(matches) > 1:
            raise ValueError('No unique match: {}'.format(self.catnums))
        return matches[0]


    def match_and_fill(self, strict=True):
        """Updates record if unique match in catalog found"""
        print 'Matching against {}...'.format(self('MulTitle'))
        try:
            match = self.match_one()
        except ValueError:
            if strict:
                raise
        else:
            print 'Unique match found! Updating record...'
            enhanced = self.clone(self)
            enhanced.object = match
            enhanced.catnums = self.catnums
            for key, func in enhanced.smart_functions.iteritems():
                enhanced[key] = func() if func is not None else enhanced(key)
            # Tweak rights statement for non-collections objects
            non_si_coll = 'Non-collections object (Mineral Sciences)'
            if non_si_coll in enhanced.get('DetCollectionName_tab', []):
                enhanced['DetRights'] = ('One or more objects depicted in this'
                                         ' image are not owned by the'
                                         ' Smithsonian Institution.')
            enhanced['_Objects'] = [match]
            return enhanced


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
        strip.extend([key for key in self.keys() if key.startswith('_')])
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
            xname = self.object.object['xname']
            catnum = self.catnums[0]
            title = u'{} ({}) [AUTO]'.format(xname, catnum).replace(' ()', ' ')
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
            whitelist = KW_WHITELIST
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
                          for catnum, links in related.iteritems()])
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
        else:
            collections.append(si_object)
            try:
                collections.remove(non_si_object)
            except ValueError:
                pass
        # Return collection and rights data as a dict
        if rights:
            self.enhanced['DetRights'] = rights
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


    @staticmethod
    def get_objects(rec, field='MulTitle'):
        """Returns list of catalog numbers parsed from MulTitle"""
        catnums = parse_catnum(rec(field), prefixed_only=True)
        # FIXME: Only handles one catalog number for now
        if catnums:
            catnums = [catnums[0]]
        return format_catnums(catnums)


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
        return oxford_comma(rec('MulCreator_tab'), False)


    def get_credit_line(self, rec):
        """Returns short credit line"""
        if not rec('MulCreator_tab'):
            creator = self.creator
        else:
            creator = rec('MulCreator_tab')[0]
        return u'{}, SI'.format(creator)


    def get_date_created(self, rec):
        """Placeholder function returning the date created"""
        return self.get_mtime(rec('Multimedia'), '%Y%d%m')


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
        return self.get_objects('MulTitle')


    def get_job_id(self, rec):
        """Returns the import identifier"""
        return rec('AdmImportIdentifier')


    def get_keywords(self, rec):
        """Returns a list of keywords"""
        return rec('DetSubject_tab')


    def get_media_topics(self, rec):
        """Returns relevant media topics"""
        pass


    def get_object_name(self, rec):
        """Returns the photo identifier or list of pictured objects"""
        object_name = rec.get_guid('Photographer number')
        if object_name is None:
            object_name = '; '.join(self.get_objects(rec))
        return object_name


    def get_source(self, rec):
        """Returns source of the multimedia file"""
        return rec('DetSource')


    def get_special_instructions(self, rec):
        """Returns long credit line for special instructions"""
        creator = self.get_creator(rec)
        if creator.startswith('Unknown'):
            creator = creator[0].lower() + creator[1:]
        credit = ['Full credit line: Photo by {}, '
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
        for obj in rec.get('_Objects', []):
            obj_data.append(obj.object['catnum'])
        return obj_data


    def get_object_sources(self, rec, source='National Museum of Natural History'):
        """Returns list with museum name"""
        return [source] * len(rec.get('_Objects', []))


    def get_object_titles(self, rec):
        """Returns list of object titles"""
        obj_data = []
        for obj in rec.get('_Objects', []):
            obj_data.append(obj.object['xname'])
        return obj_data


    def get_object_urls(self, rec):
        """Returns list of object URLs"""
        """Returns list of object titles"""
        obj_data = []
        for obj in rec.get('_Objects', []):
            obj_data.append(obj.object['url'])
        return obj_data
