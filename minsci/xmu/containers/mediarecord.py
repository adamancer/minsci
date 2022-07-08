"""Subclass of XMuRecord with methods specific to emultimedia

To create a copy of an image with embedded metadata:

```
from minsci import xmu

# Define embedder
embedder = xmu.EmbedFromEMu('path/to/output', overwrite=False)

# Embed metadata from EMu
rec = xmu.MediaRecord({...})
rec.embedder = embedder
rec.embed_metadata()
```

"""
import copy
import os
import re
import shutil
import time
from collections import OrderedDict, namedtuple
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

from nmnh_ms_tools.records.catnums import parse_catnums
from nmnh_ms_tools.utils import dedupe, lcfirst, oxford_comma, to_pascal
from unidecode import unidecode

from .xmurecord import XMuRecord
from ..tools.emultimedia.embedder import Embedder, EmbedField
from ..tools.emultimedia.hasher import hash_file




VALID_COLLECTIONS = [
    'Behind the scenes (Mineral Sciences)',
    'Catalog cards (Mineral Sciences)',
    'Collections objects (Mineral Sciences)',
    'Documents and data (Mineral Sciences)',
    'Exhibit (Mineral Sciences)',
    'Field photos (Mineral Sciences)',
    'Illustrations (Mineral Sciences)',
    'Inventory (Mineral Sciences)',
    'Labels (Mineral Sciences)',
    'Ledgers (Mineral Sciences)',
    'Macro photographs (Mineral Sciences)',
    'Micrographs (Mineral Sciences)',
    'Non-collections objects (Mineral Sciences)',
    'People (Mineral Sciences)',
    'Pretty pictures (Mineral Sciences)',
    'Research pictures (Mineral Sciences)',
    'Transaction - Accession (Mineral Sciences)',
    'Transaction - Loan (Mineral Sciences)',
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




class Asset():
    """Stores basic info about EMu multimedia files"""

    def __init__(self, data, index=None):
        self.irn = None
        self.verbatim_filename = None
        self.verbatim_path = None
        self.hash = None
        self.size = None
        self.width = None
        self.height = None
        self.is_image = None
        self.index = None
        self.local = None
        self._path = None
        # Parse data
        if 'Multimedia' in data:
            self.from_primary(data)
        elif 'Supplementary_tab' in data:
            self.from_supplementary(data, index=index)
        else:
            raise ValueError('Could not parse: {}'.format(data))


    def __str__(self):
        mask = 'Asset(path={}, verbatim_path={})'
        return mask.format(self.path, self.verbatim_path)


    @property
    def filename(self):
        return os.path.basename(self.path)


    @property
    def path(self):
        return self._path


    @path.setter
    def path(self, path):
        path = os.path.abspath(path)
        if self.verbatim_path is None:
            self.verbatim_path = path
        self._path = path


    def from_primary(self, data):
        """Creates an asset based on the primary asset in the record"""
        self.irn = data('irn')
        self.path = data('Multimedia')
        filename = data('MulIdentifier')
        if not filename:
            filename = os.path.basename(self.path)
        self.verbatim_filename = filename
        self.path = os.path.abspath(data('Multimedia'))
        self.checksum = data('ChaMd5Sum')
        self.is_image = self.filename.lower().endswith(FORMATS)
        # Get dimensions
        if data('ChaFileSize'):
            self.size = int(data('ChaFileSize'))
        if data('ChaImageWidth'):
            self.wdith = int(data('ChaImageWidth'))
        if data('ChaImageHeight'):
            self.height = int(data('ChaImageHeight'))
        self.index = 0


    def from_supplementary(self, data, index):
        """Creates an asset based on a supplementary asset in the record"""
        self.irn = data('irn')
        self.path = data('Supplementary_tab')
        filename = data('SupIdentifier_tab')
        if not filename:
            filename = os.path.basename(self.path)
        self.verbatim_filename = filename
        self.checksum = data('SupMD5Checksum_tab')
        self.is_image = self.filename.lower().endswith(FORMATS)
        # Get dimensions
        if data('SupFileSize_tab'):
            self.size = int(data('SupFileSize_tab'))
        if data('SupWidth_tab'):
            self.wdith = int(data('SupWidth_tab'))
        if data('SupHeight_tab'):
            self.height = int(data('SupHeight_tab'))
        self.index = index


    def verify(self):
        """Verifies that the file matches its hash"""
        checksum = hash_file(self.path)
        verified = checksum == self.checksum
        if not verified:
            mask = 'Checksums do not match: {} ({} != {})'
            raise ValueError(mask.format(self.filename,
                                         checksum,
                                         self.checksum))
        return verified


    def fix_timestamp(self):
        """Fixes corrupted timestamps by setting them to now"""
        fix_timestamp(self.path)




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
        self.matches = []
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
        self.mask = '{catnum}_{title}_{creators}_{pid}_{suffix}'
        self.masks = {
            'MulTitle': '{name} ({catnum}) [AUTO]'
        }
        # Create a dict of paths to all assets in the record
        self.assets = OrderedDict()


    def finalize(self):
        if 'Multimedia' in self:
            self.assets[self('Multimedia')] = Asset(self)
            supplementary = self.grid([
                'Supplementary_tab',
                'SupIdentifier_tab',
                'SupMD5Checksum_tab',
                'SupFileSize_tab',
                'SupWidth_tab',
                'SupHeight_tab'
            ])
            for i, row in enumerate(supplementary):
                verbatim_path = row('Supplementary_tab')
                if verbatim_path:
                    self.assets[verbatim_path] = Asset(row, index=i)


    def get_asset(self, asset):
        """Maps a filepath to an asset"""
        if asset is None:
            asset = self.get_primary()
        if not isinstance(asset, Asset):
            try:
                asset = self.assets[asset]
            except KeyError:
                assets = [a for a in self.assets.values() if a.path == asset]
                if len(assets) != 1:
                    raise ValueError('Asset not found: {}'.format(path))
                asset = assets[0]
        return asset


    def get_all_media(self):
        """Gets all assets in this record"""
        return list(self.assets.values())


    def get_primary(self):
        """Gets properties of the primary asset"""
        return self.get_all_media()[0]


    def get_supplementary(self):
        """Gets properties of all supplementary assets"""
        return self.get_all_media()[1:]


    def reassess_assets(self):
        """Assesses assets, updating asset list if needed"""
        assets = []
        for asset in list(self.assets.values()):
            try:
                open(asset.path, 'r')
                assets.append(asset)
            except FileNotFoundError as e:
                del self.assets[asset.verbatim_path]
        return self.assets


    def copy(self, src, dst, overwrite=False, verify=True):
        """Copies an asset"""
        src = self.get_asset(src)
        dst = os.path.abspath(dst)
        if not is_file(dst):
            dst = os.path.join(dst, src.filename)
        if not samefile(src.path, dst):
            # Ensure that destination directory exists
            try:
                os.makedirs(os.path.dirname(dst))
            except OSError:
                pass
            # Copy file, overwriting if desired
            try:
                open(dst, 'rb')
            except IOError:
                shutil.copy2(src.path, dst)
            else:
                if overwrite:
                    os.remove(dst)
                    shutil.copy2(src.path, dst)
            # Update assets dict with new location
            self.assets[src.verbatim_path].path = dst
        return self


    def rename(self, src, dst, mask='{stem}_{index}{ext}'):
        """Renames an asset"""
        src = self.get_asset(src)
        open(src.path, 'r')  # verify source file exists
        dst = os.path.abspath(dst)
        if not samefile(src.path, dst):
            stem, ext = os.path.splitext(dst)
            index = 0
            while True:
                try:
                    os.rename(src.path, dst)
                    break
                except OSError as e:
                    if not mask:
                        raise
                    index += 1
                    dst = mask.format(stem=stem, index=index, ext=ext)
            # Update assets dict with new name
            self.assets[src.verbatim_path].path = dst
        return self



    def verify_asset(self, mixed):
        """Verifies an asset by comparing it to its original checksum"""
        return self.get_asset(mixed).verify()


    def use_local_files(self, copy_to, overwrite=False,
                        verify=True, exclude=None):
        """Uses local copies of assets, copying them over if necessary"""
        for asset in self.assets.values():
            if exclude is not None and asset.filename.endswith(exclude):
                continue
            if isinstance(copy_to, str):
                # If no map provided, copy_to must be a directory
                self.copy(asset, copy_to, overwrite=overwrite, verify=verify)
            else:
                for relpath, path in copy_to.items():
                    if asset.verbatim_path.endswith(relpath):
                        asset.path = os.path.abspath(path)
                        break
                else:
                    raise KeyError('{} not found'.format(asset.verbatim_path))



    def standardize_filename(self, mixed, suffix=''):
        """Creates a standardized filename using image metadata

        G003551_HopeDiamond_ChipClark_97-4941_<EZIDMM>
        """
        asset = self.get_asset(mixed)
        ext = os.path.splitext(asset.filename)[1].lower()
        # Get catalog numbers
        title = self('MulTitle').replace('[AUTO]', '').strip()
        catnums = parse_catnums(title)
        catnums.sort()
        catnums = [c.to_filename(code='') for c in catnums]
        if len(catnums) > 2:
            catnum = '{}EtAl'.format(catnums[0])
        else:
            catnum = '+'.join(catnums)
        # Get title
        if not title:
            title = 'No title'
        title = to_pascal(title)
        if not title.startswith(('Nmnh', 'Usnm')):
            title = re.split(r'(Nmnh|Usnm)', title, 1, flags=re.I)[0]
        # Get creators
        creators = oxford_comma(self('MulCreator_tab'))
        creators = re.sub('(?<=[a-z])And(?=[A-Z])', '+', creators)
        if not creators:
            creators = 'No photographer'
        creators = to_pascal(creators)
        # Get photographer ID
        try:
            pids = self.get_guid('Photographer Number', allow_multiple=True)
            pids.sort()
            pid = format_pid(pids[0])
        except (IndexError, KeyError):
            pid = to_pascal('No number')
        # Format file name
        parts = {
            'catnum': catnum,
            'title': title,
            'creators': creators,
            'pid': pid,
            'ezid': self.get_guid('EZIDMM', strip_ark=True),
            'suffix': suffix
        }
        stem = re.sub(r'_+', '_', self.mask.format(**parts)).strip('_')
        return '{}{}'.format(stem, ext)


    def standardize_filenames(self):
        """Standardizes all file names in the record"""
        for asset in self.assets.values():
            fn = self.standardize_filename(asset)
            dst = os.path.join(os.path.dirname(asset.path), fn)
            self.rename(asset, dst)
        return self


    def copy_to(self, path, overwrite=False, verify_asset=False):
        """Copies primary asset to path"""
        self.copy(self.get_primary(), path, **kwargs)


    def to_csv(self, exclude=None):
        """Summarizes record for csv"""
        assert not exclude or all([s.islower() for s in exclude])
        try:
            pids = self.get_guid('Photographer Number', allow_multiple=True)
            pids.sort()
            pid = format_pid(pids[0])
        except IndexError:
            pid = ''
        rows = []
        for i, mm in enumerate(self.get_all_media()):
            if exclude is not None and mm.path.lower().endswith(exclude):
                continue
            ezid = self.get_guid('EZIDMM')
            if i:
                ezid += ' (alternative version)' if i else ''
            rows.append({
                'filename': mm.filename,
                'title': self('MulTitle').replace('[AUTO]', '').strip(),
                'creator': oxford_comma(self('MulCreator_tab')),
                'photo_id': pid,
                'ezid': 'http://n2t.net/{}'.format(ezid)
            })
        return rows


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
        stem = re.sub(r'[\s_]+', '_', unidecode(stem))
        stem = re.sub(r'[^a-zA-Z0-9_]', '', stem)
        print(fn, '=>', stem.rstrip('_') + ext.lower())
        return stem.rstrip('_') + ext.lower()


    def set_default(self, key):
        """Sets default value for the given key"""
        defaults = {
            'DetSource': self.embedder.source,
            'DetRights': self.embedder.rights
        }
        self[key] = defaults[key]


    def get_catalog_numbers(self, field='MulTitle', **kwargs):
        """Find catalog numbers in the given field"""
        return parse_catnums(self(field), **kwargs)


    def get_photo_numbers(self):
        """Gets the photo number"""
        return self.get_matching_rows('Photographer number',
                                      'AdmGUIDType_tab',
                                      'AdmGUIDValue_tab')


    def get_url(self):
        """Gets the resolvable URL for this record"""
        return super().get_url('EZIDMM')


    def embed_metadata(self, verify=True):
        """Updates metadata in the primary and supplementary images"""
        rec = self.clone(self)
        rec.assets = copy.deepcopy(self.assets)
        rec.matches = self.matches[:]
        names = []
        for asset in rec.get_all_media():
            # Embed metadata or add a placeholder for non-image files
            fp = asset.path
            if asset.is_image:
                # Verify the asset if this is an update
                if verify and rec('irn'):
                    self.verify_asset(asset)
                # Names must be unique within a record, so iterate if needed
                new_name = asset.filename
                i = 1
                while new_name in names:
                    stem, ext = os.path.splitext(new_name)
                    new_name = '{}_{}{}'.format(stem, i, ext)
                    i += 1
                names.append(new_name)
                if fp.endswith(new_name):
                    new_name = None
                # Update path to the asset
                asset.path = self.embedder.embed_metadata(self, fp, new_name)
        if rec:
            return rec.strip_derived().expand()


    def verify_master(self, media=None):
        """Verifies download/copy of master file by comparing hashes"""
        if media is None:
            media = self.get_primary()
        hexhash = hash_file(media.path)
        verified = hexhash == media.hash
        if not verified:
            mask = 'Checksums do not match: {} ({} != {})'
            raise ValueError(mask.format(media.filename, hexhash, media.hash))
        return verified


    def verify_import(self, images, strict=True, test=False):
        """Verifies import against images on path"""
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
        self.catnums = parse_catnums(val)
        records = []
        if len(self.catnums) > 1:
            # Multiple catalog numbers found! Record them all
            for catnum in self.catnums:
                records.extend(self.match(str(catnum)))
        else:
            for identifier in self.catnums:
                matches = self.cataloger.get(identifier, [], ignore_suffix)
                for match in matches:
                    if not match in records:
                        records.append(match)
        return records


    def match_one(self, val=None):
        """Returns a matching catalog object if exactly one match found"""
        matches = self.match(val)
        catnums = [m.object['catnum'] for m in matches]
        matches = [m for i, m in enumerate(matches)
                   if not m.object['catnum'] in catnums[:i]]
        if not matches or len(matches) > 1:
            raise KeyError('No unique match: {}'.format(self.catnums))
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
        if 'micrograph' in self('MulTitle').lower() and coll not in collections:
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


    def _get_params(self, for_filename=False):
        # Format catalog numbers
        catnums = sorted(self.catnums)
        if len(catnums) > 1:
            mask = '{} and others' if for_filename else '{} and others'
            catnum = mask.format(catnums[0])
        else:
            catnum = catnums[0]
        params = {
            'catnum': str(catnum),
            'catnum_simple': catnum.summarize('exclude_code'),
            'name': self.object.object['xname'],
            'primary': self.object.object['xname'].split(' with ')[0],
        }
        if for_filename:
            return {k: v.replace(' ', '_') for k, v in params.items()}
        return params




class EmbedFromEMu(Embedder):
    """Tools to embed metadata into a file based on existing data in EMu"""

    def __init__(self, *args, **kwargs):
        super(EmbedFromEMu, self).__init__(*args, **kwargs)
        # Default rights statement
        self.creator = 'Unknown photographer'
        self.rights = 'Usage Conditions Apply'
        self.source = 'SI-NMNH'
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
        catnums = parse_catnums(rec(field))
        # FIXME: Only handles one catalog number for now
        if catnums:
            catnums = catnums.__class__(catnums[:1])
        return catnums


    def get_guid(self, rec):
        """Placeholder function returning the EZIDMM"""
        return rec.get_url()


    def get_caption(self, rec):
        """Placeholder function returning the caption"""
        return rec('MulDescription')


    def get_copyright(self, rec):
        """Placeholder function returning copyright info"""
        rights = rec('DetSIRightsStatement')
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
        return '{}'.format(creator)


    def get_date_created(self, rec):
        """Placeholder function returning the date created"""
        return self.get_mtime(rec.get_primary().path, '%Y%m%d')


    def get_datetime_created(self, rec):
        """Placeholder function returning the full date and time created"""
        return self.get_mtime(rec.get_primary().path)


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
        object_name = ' | '.join(rec.get_guid('Photographer number', True))
        if object_name is None:
            objects = []
            for obj in self.get_objects(rec):
                obj.mask = mask
                objects.append(obj.summarize())
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
            subjects.append('medtop:20000012')  # jewelry
        return subjects


    def get_time_created(self, rec):
        """Placeholder function returning the time created"""
        return self.get_mtime(rec.get_primary().path, '%H%M%S%z')


    def get_transmission_reference(self, rec):
        """Returns the import identifier"""
        return self.get_job_id(rec)


    def get_object_numbers(self, rec):
        """Returns list of catalog numbers"""
        obj_data = []
        for obj in rec.objects if hasattr(rec, 'objects') else []:
            obj_data.append(obj.object['catnum'])
        return obj_data


    def get_object_sources(self, rec, source='SI-NMNH'):
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




def get_photo_num(val):
    """Looks for and formats common photo numbers"""
    for func in (get_a_num, get_ken_num, get_ms_num, get_yy_num):
        pid = func(val)
        if pid:
            return format_pid(pid)


def get_a_num(val):
    """Parses a Chip Clark A-number"""
    pattern = r'\bA ?\d{5}[A-z]?\b'
    try:
        val = re.search(pattern, val, flags=re.I).group()
        return 'A{}'.format(val.lstrip('A- '))
    except AttributeError:
        return


def get_ken_num(val):
    """Parses a Ken Larsen yyknnnn nnumber"""
    pattern = r'\b\d{2}[bsk]\d{4,5}(-nr)?\b'
    try:
        val = re.search(pattern, val, flags=re.I).group()
        return val.lower()
    except AttributeError:
        return


def get_ms_num(val):
    """Parses a Mineral Sciences Archive number"""
    pattern = r'\b(?:Mineral Sciences? Archives?|MSA?)\.?[ -](\d+)\b'
    try:
        match = re.search(pattern, val, flags=re.I)
        prefix = 'MSA' if 'A' in match.group() else 'MS'
        val = match.group(1)
        return '{}-{}'.format(prefix, val)
    except AttributeError:
        return


def get_yy_num(val):
    """Parses a NMNH photo number from a string"""
    pattern = r'\b(NHB)?(20)?\d{2}-\d{4,6}[A-z]?\b'
    try:
        val = re.search(pattern, val, flags=re.I).group()
        try:
            n1, n2 = [int(n) for n in val.split('-')]
            if n1 <= 2019 and abs(n2 - n1) > 25:
                return val
        except ValueError:
            return val
    except AttributeError:
        pass
    return


def split_pid(pid):
    """Splits a photo id into prefix and number"""
    if re.match(r'\d+$', pid):
        pre = ''
        num = pid
    elif re.match(r'\d{2}[bks]', pid, flags=re.I):
        pre = pid[:3]
        num = pid[3:]
    else:
        # Extract alpha prefix
        try:
            pre = re.match(r'([A-z]+)', pid).group().strip('-')
            num = pid[len(pre):].strip('- ')
            if pre == 'NHB':
                pre = ''
        except AttributeError:
            pre = ''
            num = pid
        # Extract numeric prefix if no alpha prefix found
        if not pre:
            try:
                pre = re.match(r'(\d{2,4})(?=[\-\.])', pid).group().strip('-')
                num = pid[len(pre):].strip('- ')
            except AttributeError:
                pass
    # Trim trailing letters
    num = re.sub(r'[A-z\-]+$', '', num, flags=re.I)
    return pre, num


def combine_pid(pre, num):
    """Combines a prefix and number into a photo id"""
    if re.match(r'\d{2}[bks]$', pre, flags=re.I):
        pre = pre.lower()
        pid = '{}{}'.format(pre, str(num).zfill(4))
    else:
        pre = pre.upper()
        delim = '' if pre == 'A' else '-'
        pid = '{}{}{}'.format(pre, delim, str(num)).lstrip('-')
    return pid


def format_pid(pid):
    """Formats a photo id"""
    return combine_pid(*split_pid(pid))


def fix_timestamp(fp):
    """Fixes corrupted timestamp on files exported from EMu"""
    stat = os.stat(fp)
    if stat.st_ctime < 315532800:
        print('Fixed corrupted timestamp in {}'.format(fp))
        timestamp = dt.datetime.now()
        os.utime(fp, (timestamp, timestamp))


def is_file(path):
    """Tests if path looks like it points to a file"""
    return bool(re.search(r'\.[A_z]{3,4}(_[A-z]{3,7})?$', path))


def samefile(path1, path2):
    """Tests if two paths point to the same object"""
    return os.path.normcase(path1) == os.path.normcase(path2)
