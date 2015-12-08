"""Contains helper functions for importing, matching, and organizing
multimedia in EMu"""

import cPickle as pickle
import csv
import hashlib
import os
import re
import Tkinter

from lxml import etree
from PIL import Image, ImageTk
from scandir import walk

from ..helpers import cprint, prompt, parse_catnum, format_catnums
from ..geotaxa import GeoTaxa
from .xmu import XMu




class XMu(XMu):


    def verify_from_report(self, element):
        """Reads hashes from EMu report"""
        self.record = element
        identifiers = ([self.find('MulIdentifier')] +
                       self.find('SupIdentifier_tab', 'SupIdentifier'))
        hashes = ([self.find('ChaMd5Sum')] +
                   self.find('SupMD5Checksum_tab', 'SupMD5Checksum'))
        d = dict(zip(identifiers, hashes))
        for identifier in d:
            self.hashes[identifier] = d[identifier]
        return True




    def summarize_catalog_records(self, element):
        """Summarize catalog data to allow matching of multimedia"""
        self.record = element
        #raw_input(etree.tostring(element))
        irn = self.find('irn')
        prefix = self.find('CatPrefix')
        number = self.find('CatNumber')
        suffix = self.find('CatSuffix')
        catnum = u'{}{}-{}'.format(prefix, number, suffix).rstrip('-').upper()
        index = [catnum]

        name = self.find('MetMeteoriteName')
        if bool(name):
            if bool(suffix) and not bool(number):
                try:
                    name = u'{},{}'.format(name, suffix)
                except:
                    print name, type(name)
                    print suffix, type(suffix)
                index = [name]
                catnum = None
            else:
                index.append(name)
        else:
            name = self.find('MinName')

        division = self.find('CatDivision')
        try:
            division = division[:3].upper() + ':'
        except:
            return True

        tags = []

        collection = self.find('CatCollectionName_tab', 'CatCollectionName')
        try:
            if 'polished thin' in collection[0].lower():
                tags.append('PTS')
        except IndexError:
            pass

        location = self.find('LocPermanentLocationRef', 'SummaryData')
        if 'GGM' in location.upper():
            tags.append('GGM')

        taxa = self.find('IdeTaxonRef_tab', 'ClaSpecies')
        try:
            name = self.gt.item_name(taxa, name=name)
        except:
            raw_input(taxa)
            raise

        country = self.find('BioEventSiteRef', 'LocCountry')
        state = self.find('BioEventSiteRef', 'LocProvinceStateTerritory')
        county = self.find('BioEventSiteRef', 'LocDistrictCountyShire')
        locality = [county, state, country]
        locality = ', '.join([s for s in locality if bool(s)])

        summary = [division, name]
        if catnum is not None:
            summary.append(u'({})'.format(catnum))
        if bool(locality):
            try:
                summary.append(u'from {}'.format(locality))
            except:
                pass
        if len(tags):
            summary.append(u'[{}]'.format(','.join(tags)))

        index = '|' + '|'.join([s.lower() for s in index])
        summary = ' '.join(summary)
        self.catalog.append([index, irn, summary])
        if not len(self.catalog) % 25000:
            print u'{:,} records processed'.format(len(self.catalog))
        return True




    def match_against_catalog(self, element):
        """Find catalog records matching data in specified field"""
        self.record = element
        irn = self.find('irn')
        val = self.find(self.field)
        mm = self.find('Multimedia')
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
            except:
                pass
            self.old_panel = self.panel
            self.root.title(val)

        val = self.find(self.field)
        catnums = format_catnums(parse_catnum(val), code=False)
        catirns = []
        n = len(self.field)
        for catnum in catnums:
            other = ['No match']
            if catnum == catnums[0]:
                other = ['No match', 'Write import']
            regex = re.compile('\\b' + catnum + '\\b', re.I)
            matches = [rec for rec in self.catalog if regex.search(rec[0])]
            matches = [m for m in matches if not '-' + catnum in m[0]]
            # Check to see if this irn has already been added. This can
            # happen with Antarctic meteorites when the catnum function
            # finds both a catalog number and meteorite number.
            if len([m for m in matches if m[1] in catirns]):
                print 'Term already matched'
                matches = []
            if len(matches):
                print '-' * 60
                print '{}: {}'.format(self.field, val)
                print 'Term:{} {}'.format(' '*(n-4), catnum)
                notes = self.find('NotNotes').split(';')
                for note in notes:
                    if note.lower().startswith('slide data'):
                        note = u'Note:{} {}'.format(' '*(n-4),
                                                    note.split(':')[1].strip())
                        print ''.join([c if ord(c) <= 128 else '_'
                                       for c in note])
                        break
                options = other + sorted([m[2] for m in matches])
                m = prompt('Select best match:', options)
                try:
                    catirn = [rec[1] for rec in matches if rec[2] == m][0]
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
                        print 'Existing irns: {}'.format(irns)
                        if irn in irns:
                            continue
                    cprint(('Multimedia record {} added to'
                            ' catalog record {}').format(irn, catirn))
                    try:
                        self.results[catirn].append(irn)
                    except KeyError:
                        self.results[catirn] = [irn]
                    self.n += 1
        try:
            os.remove(mm)
        except OSError:
            cprint('Could not remove {}'.format(mm))
        return True





    def find_multimedia(self, element):
        """Find multimedia attachments in catalog"""
        self.record = element
        irn = self.find('irn')
        multimedia = self.find('MulMultiMediaRef_tab', 'irn')
        self.multimedia += multimedia
        self.links[irn] = multimedia




    def record_links(self, element):
        """Record multimedia attachments in catalog in multimedia"""
        self.record = element
        #print etree.tostring(element)
        irn = self.find('irn')
        linked = ''
        if irn in self.multimedia:
            linked = 'Linked: Yes'
        elif not self.unlink:
            return True
        orig = self.find('NotNotes')
        notes = [s.strip() for s in orig.split(';')]
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
            self.update[irn] = {
                'irn' : irn,
                'NotNotes' : notes
            }
        self.n += 1
        if not self.n % 5000:
            print (u'{:,} multimedia records checked'
                    ' ({:,} to be updated)').format(self.n, len(self.update))
        return True




    def test_object(self, element):
        """Test if multimedia record is a specimen photo"""
        self.record = element
        irn = self.find('irn')
        resource_type = self.find('DetResourceType').lower()
        if resource_type != 'specimen/object':
            self.is_object[irn] = False
        else:
            self.is_object[irn] = True




    def organize_multimedia(self, element):
        """Sort specimen images to top of catalog multimedia list"""
        self.record = element
        catirn = self.find('irn')
        orig = self.find('MulMultiMediaRef_tab', 'irn')
        multimedia = []
        bumped = []
        for irn in orig:
            if not irn in multimedia+bumped:
                try:
                    is_object = self.is_object[irn]
                except:
                    pass
                else:
                    if is_object:
                        multimedia.append(irn)
                    else:
                        bumped.append(irn)
            else:
                print 'Duplicate in {}'.format(orig)
        multimedia += bumped
        if multimedia != orig:
            print catirn, multimedia
            self.update[catirn] = {
                'irn': catirn,
                'MulMultiMediaRef': multimedia
                }




def verify_import(path, report_file, delete_verified=False):
    """Verifies imported media by comparing hashes between local and imported

    Arguments:
    import_file (str): path to import file
    report_file (str): path to report file for records created via import.
        Use the VerifyImport report to generate this file.
    """

    fo = os.path.join(os.path.dirname(report_file),
                      'wk' + os.path.basename(report_file))
    emu = XMu(fi=report_file, fo=fo)
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




def attach_prematched(match_file, link_file):
    """Link multimedia records to catalog based on premade list of matches

    Args:
        match_file (str): tab-delimited text file listing of media
            records and their corresponding catalog records. The match
            file contains two fields: "irn" (irn of the multimedia record)
            and "irns" (semicolon-delimited list of catalog irns).
        link_file (str): path to EMu report with attachments to multimedia.
            Generate using DMS_MultimediaLinks.
    """

    fo = os.path.join(os.path.dirname(link_file),
                      'wk' + os.path.basename(link_file))
    lnk = XMu(fi=link_file, fo=fo)
    lnk.links = {}
    lnk.multimedia = []
    lnk.fast_iter(lnk.find_multimedia)

    output = {}
    with open(match_file, 'rb') as f:
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
                            output[irn]['MulMultiMediaRef'].append(mm_irn)
                        except KeyError:
                            output[irn] = {
                                'irn': irn,
                                'MulMultiMediaRef': [mm_irn]
                            }

    fields = ['irn']
    grids = [['MulMultiMediaRef_tab']]
    lnk.write_import('update_cat.xml', output, fields, grids, update=True)
    print 'Done!'




def mark_attached(multimedia_file, link_file):
    """Identify multimedia attachments in catalog

    Args:
        multimedia_file (str): path to EMu report containg info from
            multimedia subset. Generate using DMS_MultimediaDataWithImages.
        link_file (str): path to EMu report with attachments to multimedia.
            Generate using DMS_MultimediaLinks.
    """

    fo = os.path.join(os.path.dirname(link_file),
                      'wk' + os.path.basename(link_file))
    lnk = XMu(fi=link_file, fo=fo)
    lnk.links = {}
    lnk.multimedia = []
    lnk.fast_iter(lnk.find_multimedia)
    #os.remove(fo)

    fo = os.path.join(os.path.dirname(multimedia_file),
                      'wk' + os.path.basename(multimedia_file))
    mul = XMu(fi=multimedia_file, fo=fo)
    mul.multimedia = list(set(lnk.multimedia))
    validator = {'y' : True, 'n' : False}
    mul.unlink = prompt('Update multimedia if no link found?', validator)
    mul.n = 0
    mul.update = {}
    mul.fast_iter(mul.record_links)
    #os.remove(fo)

    if len(mul.update):
        fields = ['irn', 'NotNotes']
        mul.write_import('update_mm.xml', mul.update, fields, update=True)
    else:
        print 'No update required'
    print 'Done!'




def organize_multimedia(multimedia_file, link_file):
    """Clean list of multimedia in catalog record

    Args:
        multimedia_file (str): path to EMu report containg info from
            ALL multimedia records. Generate using DMS_MultimediaDataWithImages.
        link_file (str): path to EMu report with attachments to multimedia.
            Generate using DMS_MultimediaLinks.
    """

    fo = os.path.join(os.path.dirname(multimedia_file),
                      'wk' + os.path.basename(multimedia_file))
    mul = XMu(fi=multimedia_file, fo=fo)
    mul.is_object = {}
    mul.fast_iter(mul.test_object)

    fo = os.path.join(os.path.dirname(link_file),
                      'wk' + os.path.basename(link_file))
    lnk = XMu(fi=link_file, fo=fo)
    lnk.is_object = mul.is_object
    lnk.update = {}
    lnk.fast_iter(lnk.organize_multimedia)

    if len(lnk.update):
        print '{:,} records to be updated'.format(len(lnk.update))
        fields = ['irn']
        grids = [['MulMultiMediaRef_tab']]
        # Update is false here because the entire grid is replaced
        lnk.write_import('update_cat.xml', lnk.update, fields, grids)
    print 'Done!'




def match_multimedia(multimedia_file, catalog_file, link_file, field='MulTitle'):
    """Match EMu multimedia to catalog records

    Args:
        multimedia_file (str): path to EMu report containg info from
            multimedia subset. Generate using DMS_MultimediaDataWithImages.
        catalog_file (str): path to EMu report containing information about
            ALL catalog records. Generate using DMS_MultimediaData.
        link_file (str): path to EMu report with attachments to multimedia.
            Generate using DMS_MultimediaLinks.
    """

    print 'Reading catalog data...'
    try:
        catalog = pickle.load(open(os.path.join('sources','catalog.p'), 'rb'))
    except IOError:
        fo = os.path.join(os.path.dirname(catalog_file),
                          'wk' + os.path.basename(catalog_file))
        cat = XMu(fi=catalog_file, fo=fo)
        cat.gt = GeoTaxa()
        cat.catalog = []
        cat.fast_iter(cat.summarize_catalog_records)
        with open(os.path.join('sources','catalog.p'), 'wb') as f:
            pickle.dump(cat.catalog, f)
        catalog = cat.catalog

    print 'Finding links between catalog and multimedia...'
    fo = os.path.join(os.path.dirname(link_file),
                      'wk' + os.path.basename(link_file))
    lnk = XMu(fi=link_file, fo=fo)
    lnk.links = {}
    lnk.multimedia = []
    #lnk.fast_iter(lnk.find_multimedia)
    #os.remove(fo)

    print '-' * 60
    print 'Processing multimedia...'
    fo = os.path.join(os.path.dirname(multimedia_file),
                      'wk' + os.path.basename(multimedia_file))
    mul = XMu(fi=multimedia_file, fo=fo)
    mul.root = Tkinter.Tk()
    mul.root.geometry('640x640+100+100')
    mul.field = field
    mul.links = lnk.links
    mul.catalog = catalog
    mul.results = {}
    mul.n = 0
    mul.fast_iter(mul.match_against_catalog)
    os.remove(fo)

    output = {}
    for key in mul.results:
        output[key] = {'irn' : key, 'MulMultiMediaRef': mul.results[key]}

    fields = ['irn']
    grids = [['MulMultiMediaRef_tab']]
    mul.write_import('update_cat.xml', output, fields, grids, update=True)
    print 'Done!'


def organize_and_mark(multimedia_file, link_file):
    """Helper function to organize and mark attached multimedia

    Args:
        multimedia_file (str): path to EMu report containg info from
            ALL multimedia records. Generate using DMS_MultimediaDataWithImages.
        link_file (str): path to EMu report with attachments to multimedia.
            Generate using DMS_MultimediaLinks.
    """
    organize_multimedia(multimedia_file, link_file)
    mark_attached(multimedia_file, link_file)
