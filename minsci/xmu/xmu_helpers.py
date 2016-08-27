"""Contains helper functions for importing, matching, and organizing
multimedia in EMu"""

import cPickle as pickle
import csv
import hashlib
import os
import re
import sys
import time
import Tkinter
from copy import copy

from lxml import etree
from PIL import Image, ImageTk
from scandir import walk

import xmu
from .deepdict import MinSciRecord
from ..helpers import (cprint, dedupe, prompt, oxford_comma,
                       parse_catnum, format_catnums)
from ..geotaxa import GeoTaxa





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


class XMu(xmu.XMu):

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.antmet = re.compile(r'([A-Z]{3} |[A-Z]{4})[0-9]{5,6}(,[A-z0-9]+)?')


    def verify_from_report(self, element):
        """Reads hashes from EMu report"""
        rec = self.read(element).unwrap()
        identifiers = [rec('MulIdentifier')] + rec('SupIdentifier_tab')
        hashes = [rec('ChaMd5Sum')] + rec('SupMD5Checksum_tab')
        d = dict(zip(identifiers, hashes))
        for identifier in d:
            self.hashes[identifier] = d[identifier]
        return True


    def summarize_catalog(self, element):
        """Summarize catalog data to allow matching of multimedia

        self.catalog = {index: {suffix : {irn : summary}}}
        """
        rec = self.read(element).unwrap()
        irn = rec('irn')
        catnum = rec.get_identifier(include_code=False)
        if not catnum:
            return True
        indexes = [re.split('[-,]', catnum)[0]]
        # Get catalog data used to match specimens. There are two types of
        # identificaiton numbers: Smithsonian catalog numbers and Antarctic
        # meteorite numbers.
        prefix = rec('CatPrefix')
        number = rec('CatNumber')
        suffix = rec('CatSuffix')
        name = rec('MetMeteoriteName').upper()
        if self.antmet.match(name):
            try:
                name, suffix = name.split(',')
            except ValueError:
                pass
            indexes.append(name)
        if suffix == name:
            suffix = None
        indexes = [indexes[i] for i in xrange(len(indexes))
                   if indexes[i].strip() and not indexes[i] in indexes[:i]]
        if not len(indexes):
            #cprint('irn: {}'.format(irn))
            return True

        # Skip records that already exist
        try:
            self.metadata[irn]
        except KeyError:
            pass
        else:
            # Confirm that irn appears in the right place in the catalog
            # lookup. It's a problem if not.
            cprint('{} already exists'.format(irn), self.verbose)
            for index in indexes:
                try:
                    self.catalog[index][suffix][irn]
                except KeyError:
                    cprint('Fatal error: Existing irn not found in catalog.'
                           ' Delete catalog.p and retry.')
                    print irn, catnum, indexes
                    raise
            return True

        # Get basic specimen information from record. This will be used
        # to write a caption and keyword list for this object.
        collection = rec('CatCollectionName_tab')
        location = rec('LocPermanentLocationRef', 'SummaryData')
        country = rec('BioEventSiteRef', 'LocCountry')
        state = rec('BioEventSiteRef', 'LocProvinceStateTerritory')
        county = rec('BioEventSiteRef', 'LocDistrictCountyShire')
        taxa = rec.get_classification()
        setting = rec('MinJeweleryType')
        cut = rec('MinCut')
        color = rec('MinColor_tab')
        lot = rec('BioLiveSpecimen')
        weight = rec('MeaCurrentWeight')
        unit = rec('MeaCurrentUnit')
        status = rec('SecRecordStatus').lower()
        if not bool(status):
            return True

        # Check cut for setting info if nothing is in the jewelery field
        cut = cut.lower()
        if not bool(setting) and bool(cut):
            for term in OBJECTS:
                if term == cut:
                    # Special handling for exact matches
                    setting = term
                    if term != 'carved':
                        cut = ''
                    #print 'Cut is a setting: {}'.format(setting)
                    break
                elif (term + 's') in cut:
                    setting = term + 's'
                    #print 'Found setting in cut: {}'.format(setting)
                    break
                elif term in cut:
                    setting = term
                    #print 'Found setting in cut: {}'.format(setting)
                    break
        # General rule: beads should always be plural
        if setting in cut:
            setting = ''
        if setting == 'bead':
            setting += 's'
        if cut == 'bead':
            cut += 's'

        # Fun with meteorites
        name = rec('MetMeteoriteName')
        if bool(name):
            if bool(suffix) and not bool(number):
                try:
                    name = u'{},{}'.format(name, suffix)
                except:
                    print name, type(name)
                    print suffix, type(suffix)
        else:
            name = rec('MinName')

        division = rec('CatDivision')
        try:
            division = division[:3].upper()
        except IndexError:
            return True
        if not bool(division):
            return True

        # Title
        xname = self.gt.item_name(taxa, setting, name)
        title = u'{} '.format(xname)  # must use catnum from multimedia record!

        # Keywords
        divmap = {
            'MET' : 'Meteorite',
            'MIN' : 'Mineral',
            'PET' : 'Rock'
        }
        try:
            stype = divmap[division]
        except KeyError:
            return True
        else:
            if stype == 'Mineral' and prefix == 'G':
                stype = 'Gem'
        keywords = [stype]
        if bool(setting):
            if setting == 'carved':
                keywords.append('Carving')
            else:
                keywords.append(setting)
        if any(taxa):
            try:
                keywords.extend(self.gt.clean_taxa(taxa, dedupe=True))
            except:
                print taxa
                raw_input()
        keywords.append(country)
        if country.lower().startswith('united states') and bool(state):
            keywords.append(state)
        keywords = [s[0].upper() + s[1:] for s in keywords
                    if bool(s) and not 'unknown' in s.lower()]

        # Set descriptive caption
        caption = self.get_caption(name, xname, taxa, country, state, county,
                                   setting, cut, color, weight, unit, lot,
                                   status)

        # Set tags containing special information that can be
        # useful in identifying specimens
        tags = []
        try:
            if 'polished thin' in collection[0].lower():
                tags.append('PTS')
        except IndexError:
            pass
        if 'GGM' in location.upper():
            tags.append('GGM')
        elif 'POD 4' in location.upper():
            tags.append('POD 4')

        # Set summary
        if catnum is not None:
            summary = ['{} {}:'.format(division, catnum), caption]
        else:
            summary = [division + ':', caption]
        if len(tags):
            summary.append(u'[{}]'.format(','.join(tags)))
        try:
            summary = ' '.join(summary)
        except:
            print summary
            raw_input()

        # The matching dictionary is tiered, with the first level consisting
        # of a primary identificaiton (either a catalog number or meteorite
        # number) and the second level consisting of suffixes.
        for index in indexes:
            index = index.upper()
            try:
                self.catalog[index]
            except KeyError:
                self.catalog[index] = {}
            try:
                self.catalog[index][suffix][irn] = summary
            except KeyError:
                self.catalog[index][suffix] = { irn : summary }
            self.n += 1
            if not self.n % 25000:
                print u'{:,} records processed'.format(self.n)
                #return False

        # For multiple source files, the newer file will overwrite
        # the older one.
        self.metadata[irn] = {
            'division' : division,
            'title': title,
            'caption' : caption,
            'keywords' : keywords,
            'status' : status
            }


    def get_caption(self, name, xname, taxa, country, state, county,
                    setting, cut, color, weight, unit, lot, status):
        caption = []
        if any([cut, setting]):
            # Generate detailed description of gems and jewelery
            setting = setting.lower().rstrip('. ')
            caption = []
            if bool(name):
                caption.append(u'{}.'.format(name))
            if bool(cut):
                cut = cut.lower()
                if cut.endswith(' cut'):
                    cut = cut[:-4]
                if 'beads' in cut or 'crystal' in cut:
                    caption.append(u'{} of'.format(cut))
                elif 'carv' in cut and not 'carving' in setting:
                    caption.append(u'carved')
                else:
                    caption.append(u'{}-cut'.format(cut))
            if bool(color):
                color = oxford_comma(color[0].lower().split(','), False)
                caption.append(u'{}'.format(color))
            if any(taxa):
                taxon = self.gt.item_name(taxa).split(' with ').pop(0).strip()
                taxon = taxon[0].lower() + taxon[1:]
                caption.append(u'{}'.format(taxon))
            if bool(weight) and bool(unit):
                weight = u'{} {}'.format(weight.rstrip('0.'), unit.lower())
                if lot.lower().startswith(('set', 'with')) or bool(setting):
                    caption.append(u'({})'.format(weight))
                else:
                    caption.append(u'weighing {}'.format(weight))
            if bool(setting) and not ('carv' in cut and 'carv' in setting):
                # Distinguish carved objects like bowls and spheres
                if setting.rstrip('s') in OBJECTS[:-2]:
                    caption.append(u'{}'.format(setting))
                else:
                    article = 'a '
                    if setting.endswith('s'):
                        article = ''
                    elif setting.startswith(('a','e','i','o','u')):
                        article = 'an '
                    caption.append(u'in {}{}'.format(article, setting))
            if len(lot):
                lot = lot.lower()
                if lot.startswith(('set', 'with')):
                    caption.append(u'{}'.format(lot))
                else:
                    caption.append(u'. Lot described as "{}."'.format(
                        lot.replace('"',"'").strip()))

            if bool(name):
                name = caption.pop(0)
            else:
                name = ''
            caption[0] = caption[0][0].upper() + caption[0][1:]
            if bool(name):
                caption.insert(0, name)
            caption = ' '.join(caption).replace(' .', '.')
            if not caption.endswith('"') and not caption.endswith('.'):
                caption += '.'
            if status != 'active':
                if status == 'inactive':
                    status = 'made inactive'
                caption += (' The catalog record associated with this'
                            'specimen has been {}.').format(status)
            # Neaten up the caption
            pairs = [
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
            for pair in pairs:
                caption = caption.replace(pair[0], pair[1])
        else:
            # Provide less detailed caption for rocks and minerals
            caption.append(xname)
            locality = [county, state, country]
            locality = ', '.join([s for s in locality if bool(s)])
            if bool(locality):
                try:
                    caption.append(u'from {}'.format(locality))
                except:
                    pass
            caption = ' '.join(caption)
        return caption





    def summarize_links(self, element):
        """Find multimedia attachments in catalog"""
        rec = self.read(element).unwrap()
        irn = rec('irn')

        # Skip records that already exist
        try:
            self.links[irn]
        except KeyError:
            pass
        else:
            return True

        multimedia = rec('MulMultiMediaRef_tab', 'irn')
        self.multimedia += multimedia
        # Record multimedia linked to a given catalog record
        self.links[irn] = multimedia
        # Record catalog records linking to a given multimedia record
        for mmirn in multimedia:
            try:
                self.mlinks[mmirn].append(irn)
            except KeyError:
                self.mlinks[mmirn] = [irn]




    def match_against_catalog(self, element):
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




    def blind_match_against_catalog(self, element):
        """Match against catalog with no review

        Configured for ledgers
        """
        rec = self.read(element).unwrap()
        irn = rec('irn')
        val = rec(self.field)
        catnums = format_catnums(parse_catnum(val, strip_suffix=True),
                                 code=False)
        if 'Meteorite Collection' in val:
            divs = ['MET']
        elif 'Mineral Collection' in val:
            divs = ['MIN']
        elif 'Rock & Ore Collection' in val:
            divs = ['PET']
        elif val.startswith(('Bosch', 'Petrographic')):
            return True
        else:
            divs = ['MIN', 'PET']
        matches = []
        for catnum in [catnum for catnum in catnums
                       if not (catnum[0].isdigit() and len(catnum) < 4)]:
            matches.extend(match(catnum, self.catalog, divs))
        matches = [m for m in matches if not irn in self.links[m[0]]]
        if len(matches):
            cprint('{} yielded {:,} new matches'.format(val, len(matches)))
        for m in matches:
            '''
            for m in matches:
                try:
                    cprint(u' {}'.format(': '.join(m)))
                except UnicodeEncodeError:
                    cprint(m[0])
            '''
            try:
                self.results[m[0]].append(irn)
            except KeyError:
                self.results[m[0]] = [irn]




    def mark_links(self, element):
        """Record multimedia attachments in catalog in multimedia"""
        rec = self.read(element).unwrap()
        irn = rec('irn')
        linked = ''
        if irn in self.multimedia:
            linked = 'Linked: Yes'
        elif not self.unlink:
            return True
        notes = rec('NotNotes')
        orig = copy(notes)
        notes = [s.strip() for s in notes.split(';')]
        i = 0
        while i < len(notes):
            note = notes[i]
            if note.lower().startswith('linked:'):
                notes[i] = linked
                break
            i += 1
        else:
            notes.append(linked)
        notes = '; '.join([s.strip() for s in notes if bool(s)])
        if notes != orig:
            self.update[irn] = self.container({
                'irn' : irn,
                'NotNotes' : notes
            })
        self.n += 1
        if not self.n % 5000:
            cprint((u'{:,} multimedia records checked'
                     ' ({:,} to be updated)').format(self.n, len(self.update)))
        return True




    def assign_collections(self, element):
        rec = self.read(element).unwrap()
        valid = [
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
        cmap = {
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
        for key in cmap.keys():
            newkey = key
            if not newkey in ('Meteorite Datapacks'):
                newkey = 'Mineral Sciences {}'.format(newkey)
                cmap[newkey] = cmap[key]
                del cmap[key]

        irn = rec('irn')
        # Skip record if no match in active links file
        if not irn in self.multimedia:
            return True
        title = rec('MulTitle')
        collections = rec('DetCollectionName_tab', 'DetCollectionName')
        keywords = [s.lower() for s in
                    rec('DetSubject_tab')]
        resource_type = rec('DetResourceType')

        # Map old collection names to preferred values, discarding
        # names that contain no information
        revised = []
        for key in collections:
            try:
                val = cmap[key]
            except KeyError:
                if key in valid:
                    revised.append(key)
                else:
                    cprint(u'{} not found'.format(key))
            else:
                if bool(val):
                    revised.append('{} (Mineral Sciences)'.format(val))

        # Assign object that is linked in catalog
        if resource_type == 'Specimen/Object':
            if irn in self.multimedia:
                revised.append('Collections objects (Mineral Sciences)')
            else:
                revised.append('Unidentified objects (Mineral Sciences)')
        elif 'Exhibit (Mineral Sciences)' in revised and irn in self.multimedia:
            cprint('Exhibit object found')
            revised.append('Collections objects (Mineral Sciences)')

        # Clear unidentified flag if collections object found. This is
        # not ideal for assigning collections generally and will
        # need to be revisited.
        if ('Collections objects (Mineral Sciences)' in revised
            and 'Unidentified objects (Mineral Sciences)' in revised):
            revised.remove('Unidentified objects (Mineral Sciences)')


        if len([s for s in keywords if 'micrograph' in s]):
            revised.append('Micrographs (Mineral Sciences)')

        if 'macro' in title.lower():
            try:
                revised.pop(revised.index('Micrographs (Mineral Sciences)'))
            except ValueError:
                pass

        revised = [revised[i] for i in xrange(len(revised))
                   if not revised[i] in revised[:i]]
        # Move object status to front
        temp = []
        for collection in revised:
            if 'object' in collection:
                temp.insert(0, collection)
            else:
                temp.append(collection)
        revised = temp

        invalid = [val for val in revised if not val in valid]
        if len(invalid):
           cprint('Invalid collections names: {}'.format(', '.join(invalid)))
        cprint('Revised:  {}'.format(revised), VERBOSE)
        cprint('Original: {}'.format(collections), VERBOSE)
        cprint('-' * 60, VERBOSE)
        if revised != collections:
            try:
                self.update[irn]['DetCollectionName'] = revised
            except KeyError:
                self.update[irn] = {
                    'irn': irn,
                    'DetCollectionName': revised
                }
                self.n += 1
                if not self.n % 500:
                    print '{:,} records assigned to new collection(s)'.format(
                              self.n)




    def assign_related(self, element):
        """Assigns"""
        rec = self.read(element).unwrap()
        # Skip anything that isn't a specimen
        if rec('DetResourceType') != 'Specimen/Object':
            return True
        irn = rec('irn')
        val = rec('MulTitle')
        orig = rec('DetRelation_tab', 'DetRelation')
        catnums = format_catnums(parse_catnum(val), code=False)
        try:
            divs = sorted(list(set([self.metadata[catirn]['division']
                                    for catirn in self.mlinks[irn]])))
        except KeyError:
            divs = ['MET', 'MIN', 'PET']
        related = []
        for catnum in catnums:
            matches = match(catnum, self.catalog, divs)
            if not len(matches):
                continue
            nt = len(matches)
            try:
                n = len([m for m in matches if m[0] in self.mlinks[irn]])
            except KeyError:
                n = 0
            # Add division, if appropriate
            div = ''
            if len(divs) < 3:
                div = '({}) '.format('/'.join(divs))
            # Add the museum code, if appropriate
            mcode = ''
            if bool(div) and not 'MET' in div:
                mcode = 'NMNH '
            elif bool(div) and not catnum[:3].isalpha():
                mcode = 'USNM '
            related.append('{}{} {}({}/{})'.format(mcode, catnum, div, n, nt))
            # Capture catalog irn
            catirn = matches[0][0]
        related.sort()
        if len(related) and related != orig:
            try:
                self.update[irn]['DetRelation'] = related
            except KeyError:
                self.update[irn] = { 'irn': irn, 'DetRelation' : related }
            self.n += 1
            if not self.n % 5000:
                print '{:,} records related to catalog!'.format(self.n)
                #return False

        # Assign metadata based on catalog record
        if len(related) == 1 and related[0].endswith('(1/1)'):
            result = {}
            # Title
            val = rec('MulTitle').strip()
            if (val.startswith('Mineral Sciences Specimen Photo')
                or val.endswith('[AUTO]')):
                catnum = val.rsplit('(', 1).pop().strip('() ')
                title = u'{} ({}) [AUTO]'.format(
                    self.metadata[catirn]['title'].strip(), catnum)
                if title.lower() != val.lower() and '(NMNH' in title:
                    result['MulTitle'] = title
                else:
                    raw_input(title)

            # Caption
            val = rec('MulDescription').strip()
            if not bool(val) or val.endswith('[AUTO]'):
                caption = u'{} [AUTO]'.format(self.metadata[catirn]['caption'])
                if caption.lower() != val.lower():
                    result['MulDescription'] = caption

            # Keywords
            whitelist = [
                'Allure of Pearls',
                'Blue Room',
                'Splendor of Diamonds',
                'Micrograph, cross-polarized light',
                'Micrograph, plane-polarized light',
                'Micrograph, reflected light'
            ]
            whitelist = [kw.lower() for kw in whitelist]
            existing = rec('DetSubject_tab', 'DetSubject')
            keywords = copy(self.metadata[catirn]['keywords'])
            keywords.extend([kw for kw in existing
                             if kw.lower() in whitelist and not kw in keywords])
            if existing != keywords:
                self.added.extend([kw.lower() for kw in keywords])
                result['DetSubject'] = keywords
                missing = sorted(list(set(existing) - set(keywords)))
                if len(missing):
                    self.removed.extend([kw.lower() for kw in missing])
                    print (u'Warning: The following keywords will be'
                            ' lost: {}').format(', '.join(missing))

            # Handle non-active records. These will sometimes preservce
            # info for photographs of objects no longer in the collection.
            if self.metadata[catirn]['status'] != 'active':
                results['MulTitle'] = '{} (catalog record {}) [AUTO]'.format(
                    results['MulTitle'][:-7], status)
                result['DetRights'] = ('One or more objects depicted in'
                                     ' this image are not owned by the'
                                     ' Smithsonian Institution.')
                collection = 'Non-collections object (Mineral Sciences)'
                try:
                    collections = self.update[irn]['DetCollectionName']
                except KeyError:
                    collections = rec('DetCollectionName_tab',
                                            'DetCollectionName')
                for i in xrange(len(collections)):
                    if 'objects' in collections[i]:
                        collections[i] = collection
                        break
                else:
                    collections.append(collection)
                result['DetCollectionName'] = dedupe(collections)

            if len(result):
                try:
                    self.update[irn]
                except KeyError:
                    self.update[irn] = {'irn': irn}
                for key in result:
                    self.update[irn][key] = result[key]
                status = rec('SecRecordStatus').lower()
                if status != 'active':
                    print result




    def test_object(self, element):
        """Test if multimedia record is a specimen photo"""
        rec = self.read(element).unwrap()
        irn = rec('irn')
        resource_type = rec('DetResourceType').lower()
        if resource_type != 'specimen/object':
            self.is_object[irn] = False
        else:
            self.is_object[irn] = True




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
                    # which is fine.
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




VERBOSE = True

def verify_import(path, report_path, delete_verified=False):
    """Verifies imported media by comparing hashes between local and imported

    Arguments:
    import_path (str): path to import file
    report_path (str): path to report file for records created via import.
        Use the VerifyImport report to generate this file.
    """

    emu = XMu(report_path, container=MinSciRecord)
    emu.hashes = {}
    emu.fast_iter(emu.verify_from_report)
    os.remove(fo)

    cprint(u'Walking {}...'.format(path))
    matches = {}
    mismatches = {}
    for root, dirs, files in walk(path):
        for fn in files:
            identifier = fn.lower()
            try:
                h1 = emu.hashes[identifier]
            except KeyError:
                pass
            else:
                print u'Hashing {}...'.format(identifier)
                fp = os.path.join(root, fn)
                try:
                    h2 = hashlib.md5(open(fp, 'rb').read()).hexdigest()
                except OSError:
                    print u'Error: {}'.format(fp)
                else:
                    if h1 == h2:
                        print u'{} matched'.format(identifier)
                        matches[identifier] = h1
                        del emu.hashes[identifier]
                    else:
                        print u'{} did not match'.format(identifier)
                        mismatches[identifier] = (h1, h2)

    print '-' * 60
    report_only = sorted(emu.hashes.keys())
    if len(report_only):
        print u'The following files were not found along the given path:'
        print ' ' + '\n '.join(report_only)
        print '-' * 60

    n = len(matches)
    m = len(mismatches)
    print u'{:,}/{:,} of the files that were found matched!'.format(n, n+m)
    if len(mismatches):
        print 'Hashes for the following files did not match:'
        print '\n'.join(sorted(mismatches.keys()))

    if delete_verified:
        validator = {'y' : True, 'n' : False}
        if prompt('Delete local copies of verified files?', validator):
            for match in matches:
                fp = imp.local[identifier]
                print u'Deleting {}'.format(fp)
                #os.remove(fp)
    print 'Done!'




def attach_prematched(match_path, catalog_path):
    """Link multimedia records to catalog based on premade list of matches

    Args:
        match_path (str): tab-delimited text file listing of media
            records and their corresponding catalog records. The match
            file contains two fields: "irn" (irn of the multimedia record)
            and "irns" (semicolon-delimited list of catalog irns).
        catalog_path (str): path to EMu report containing catalog records.
            Generate using DMS_MultimediaData for recently modified records.
    """

    lnk = XMu(catalog_path, container=MinSciRecord)
    lnk.links = {}
    lnk.mlinks = {}
    lnk.multimedia = []
    lnk.fast_iter(lnk.summarize_links)

    output = {}
    with open(match_path, 'rb') as f:
        rows = csv.reader(f, delimiter='\t')
        for row in rows:
            try:
                d = dict(zip(keys, row))
            except UnboundLocalError:
                keys = row
            else:
                mm_irn = d['irn']
                for irn in [s.strip() for s in d['irns'].split(';')]:
                    try:
                        mm_irns = lnk.links[irn]
                    except KeyError:
                        mm_irns = []
                    if not mm_irn in mm_irns:
                        try:
                            output[irn]['MulMultiMediaRef_tab'].append(mm_irn)
                        except KeyError:
                            output[irn] = {
                                'irn': irn,
                                'MulMultiMediaRef_tab': [mm_irn]
                            }
    records = []
    for key in output:
        record = output[key].expand()

    lnk.write('update_cat.xml', output.values(), 'ecatalogue')
    print 'Done!'




def mark_attached(multimedia_path, catalog_path):
    """Identify multimedia attachments in catalog

    Args:
        multimedia_path (str): path to EMu report containg info from
            multimedia subset. Generate using DMS_MultimediaDataWithImages.
        catalog_path (str): path to EMu report containing catalog records.
            Generate using DMS_MultimediaData for recently modified records.
    """

    print 'Reading catalog data...'
    cat = XMu(catalog_path, container=MinSciRecord)
    fp = os.path.join(os.path.join('sources', 'catalog.p'))
    try:
        pickled = pickle.load(open(fp, 'rb'))
    except IOError:
        pickled = {'files': [], 'catalog' : {}, 'metadata': {}}
    if cat._files != pickled['files']:
        print 'Processing new files...'
        # Order matters! If a file has been inserted into the sequence,
        # we have to start over. If only new files are found, however,
        # we can get by only processing those. This works by replacing
        # the _files attribute on the catalog object.
        if cat._files[len(pickled['files'])] == pickled['files']:
            cat._files = [fp for fp in cat._files if not fp in pickled['files']]
        cat.gt = GeoTaxa()
        cat.catalog = {}
        cat.metadata = {}
        cat.n = 0
        cat.fast_iter(cat.summarize_catalog)
        # Merge into pickled and update file
        print 'Merging new data with existing...'
        pickled['catalog'] = merge(pickled['catalog'], cat.catalog)
        pickled['metadata'] = merge(pickled['metadata'], cat.metadata)
        pickled['files'] = cat._files
        with open(fp, 'wb') as f:
            pickle.dump(pickled, f)
        cat.files = files
    catalog = pickled['catalog']
    metadata = pickled['metadata']

    cprint(catalog['EET 96311'])
    raw_input()

    lnk = XMu(catalog_path, container=MinSciRecord)
    lnk.links = {}
    lnk.mlinks = {}
    lnk.multimedia = []
    lnk.fast_iter(lnk.summarize_links)

    mul = XMu(multimedia_path, container=MinSciRecord)
    mul.multimedia = list(set(lnk.multimedia))
    mul.update = {}
    # Specifies how to handle updates based on length of the links dict
    # If False, only positives will be updated in the mul functions.
    # FIXME: Only implemented for mark_links so far
    mul.unlink = True
    if len(lnk.links) < 300000:
        print 'Will not update multimedia if no link found'
        mul.unlink = False

    print 'Marking linked multimedia records...'
    mul.n = 0
    mul.fast_iter(mul.mark_links)

    print 'Assigning collections...'
    mul.n = 0
    mul.fast_iter(mul.assign_collections)

    print 'Assigning relations...'
    mul.n = 0
    mul.catalog = catalog
    mul.metadata = metadata
    mul.mlinks = lnk.mlinks
    mul.added = []
    mul.removed = []
    mul.fast_iter(mul.assign_related)
    missing = sorted(list(set(mul.removed) - set(mul.added)))
    if len(missing):
        print u'Missing:'
        print u'\n'.join(missing)
        print ">> Add any terms you'd like to keep to the whitelist and re-run"
        raw_input()

    if len(mul.update):
        handlers = {
            'DetCollectionName_tab': 'overwrite',
            'DetRelation_tab': 'overwrite',
            'DetSubject_tab': 'overwrite'
            }
        xmu.write('update_mm.xml', mul.update.values(), 'emultimedia', handlers)
    else:
        print 'No update required'




def organize_multimedia(multimedia_path, catalog_path):
    """Clean list of multimedia in catalog record

    Args:
        multimedia_path (str): path to EMu report containg info from
            ALL multimedia records. Generate using DMS_MultimediaDataWithImages.
        catalog_path (str): path to EMu report containing catalog records.
            Generate using DMS_MultimediaData for recently modified records.
    """

    mul = XMu(multimedia_path, container=MinSciRecord)
    mul.is_object = {}
    mul.fast_iter(mul.test_object)

    lnk = XMu(catalog_path, container=MinSciRecord)
    lnk.is_object = mul.is_object
    lnk.warning = False
    lnk.update = {}
    lnk.fast_iter(lnk.organize_multimedia)

    if lnk.warning:
        cprint('update_cat.xml not written: {} includes only a subset of'
               ' all multimedia'.format(multimedia_path))
    elif len(lnk.update):
        print '{:,} records to be updated'.format(len(lnk.update))
        #fields = ['irn']
        #grids = [['MulMultiMediaRef_tab']]
        # Update is false here because the entire grid is replaced
        #lnk.write_import('update_cat.xml', lnk.update, fields, grids)
        handlers = {'MulMultiMediaRef_tab' : {}}
        lnk.write('update_cat.xml', lnk.update, fields, handlers)
    print 'Done!'




def match_multimedia(multimedia_path, catalog_path,
                     field='MulTitle', blind=False):
    """Match EMu multimedia to catalog records

    Args:
        multimedia_path (str): path to EMu report containg info from
            multimedia subset. Generate using DMS_MultimediaDataWithImages.
        catalog_path (str): path to EMu report containing catalog records.
            Generate using DMS_MultimediaData for recently modified records.
    """

    print 'Reading catalog data...'
    cat = XMu(catalog_path, container=MinSciRecord)
    fp = os.path.join(os.path.join('sources', 'catalog.p'))
    try:
        pickled = pickle.load(open(fp, 'rb'))
    except IOError:
        pickled = {'catalog' : {}, 'metadata': {}}
    if cat._files != pickled['files']:
        print 'Processing new files...'
        # Order matters! If a file has been inserted into the sequence,
        # we have to start over. If only new files are found, however,
        # we can get by only processing those. This works by replacing
        # the _files attribute on the catalog object.
        if cat._files[len(pickled['files'])] == pickled['files']:
            cat._files = [fp for fp in cat._files if not fp in pickled['files']]
        cat.gt = GeoTaxa()
        cat.catalog = {}
        cat.metadata = {}
        cat.n = 0
        cat.fast_iter(cat.summarize_catalog)
        # Merge into pickled and update file
        print 'Merging new data with existing...'
        pickled['catalog'] = merge(pickled['catalog'], cat.catalog)
        pickled['metadata'] = merge(pickled['metadata'], cat.metadata)
        pickled['files'] = cat._files
        with open(fp, 'wb') as f:
            pickle.dump(pickled, f)
        cat.files = files
    catalog = pickled['catalog']
    metadata = pickled['metadata']

    print 'Finding links between catalog and multimedia...'
    lnk = XMu(catalog_path, container=MinSciRecord)
    lnk.links = {}
    lnk.mlinks = {}
    lnk.multimedia = []
    lnk.fast_iter(lnk.summarize_links)

    print '-' * 60
    print 'Processing multimedia...'
    mul = XMu(multimedia_path, container=MinSciRecord)
    mul.field = field
    mul.links = lnk.links
    mul.catalog = catalog
    mul.results = {}
    mul.n = 0
    if not blind:
        mul.root = Tkinter.Tk()
        mul.root.geometry('640x640+100+100')
        try:
            mul.fast_iter(mul.match_against_catalog)
        except:
            # This is horrible
            print "Fatal error! Writing what you've done so far..."
    else:
        mul.fast_iter(mul.blind_match_against_catalog)

    records = []
    for irn in mul.results:
        record = lnk.container({
            'irn' : irn,
            'MulMultiMediaRef_tab': sorted(mul.results[irn])
            })
        records.append(record.expand())

    xmu.write('update_cat.xml', records, 'ecatalogue')
    print 'Done!'




def organize_and_mark(multimedia_path, catalog_path):
    """Helper function to organize and mark attached multimedia

    Args:
        multimedia_path (str): path to EMu report containg info from
            multimedia records. Generate using DMS_MultimediaDataWithImages.
        catalog_path (str): path to EMu report containing catalog records.
            Generate using DMS_MultimediaData for recently modified records.
    """
    organize_multimedia(multimedia_path, catalog_path)
    mark_attached(multimedia_path, catalog_path)




def match(id_num, catalog, divs=None):
    """Checks catalog for matches against given id number

    Args:
        id_num (str): catalog number or Antarctic meteorite number
        catalog (dict): lookup dictionary
        div (str): specifies division (MET, MIN, or PET), if known

    Returns:
        List of [irn, summary] for matches
    """
    id_num = id_num.upper()
    for delim in ('-', ','):
        if delim in id_num:
            stem, suffix = id_num.rsplit(delim, 1)
            break
    else:
        stem = id_num
        suffix = None
    if divs is None:
        divs = ['MET', 'MIN', 'PET']
    else:
        divs = [div.upper() for div in divs]
    cprint(u'Searching for {} in {}...'.format(
        id_num, oxford_comma(divs, False)), VERBOSE)
    cprint(u'Stem is {}, suffix is {}'.format(stem, suffix), VERBOSE)
    matches = []
    if suffix is None:
        cprint(u'Checking stem...', VERBOSE)
        try:
            suffixes = catalog[stem]
        except KeyError:
            pass
        else:
            for suffix in suffixes:
                for irn in catalog[stem][suffix]:
                    matches.append([irn, catalog[stem][suffix][irn]])
    else:
        cprint(u'Checking stem and suffix...', VERBOSE)
        try:
            for irn in catalog[stem][suffix]:
                matches.append([irn, catalog[stem][suffix][irn]])
        except KeyError:
            pass
    s = ''
    if len(matches) != 1:
        s = 'es'
    cprint(u'Found {} match{}!'.format(len(matches), s), VERBOSE)
    if len(divs) < 3:
        temp = []
        for div in divs:
            cprint(u'Checking for matches in {}...'.format(div), VERBOSE)
            temp.extend([m for m in matches if m[1].startswith(div)])
        matches = temp
        s = ''
        if len(matches) != 1:
            s = u'es'
        cprint(u'Found {} match{} in the specified divisions!'.format(
            len(matches), s), VERBOSE)
    if VERBOSE:
        for match in sorted(matches):
            cprint(u' {}'.format(': '.join(match)), VERBOSE)
    cprint('-' * 60, VERBOSE)
    return matches




def merge(a, b, path=None, kill_on_conflict=False):
    """Merges b into a such that b overwrites a for the same key

    Modified from http://stackoverflow.com/questions/7204805/
    """
    # Returns b if a is empty
    if path is None and not len(a) and len(b):
        return b
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass # same leaf value
            else:
                if kill_on_conflict:
                    cpath = '.'.join(path + [str(key)])
                    raise Exception('Conflict at {}'.format(cpath))
                else:
                    a[key] = b[key]
        else:
            a[key] = b[key]
    return a
