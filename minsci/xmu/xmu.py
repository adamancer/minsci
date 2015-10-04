# Standard
import csv
import datetime
import getpass
import glob
import io
import os
import re
import sys
import tempfile
import time
from copy import copy
from operator import itemgetter
from textwrap import fill

# Third party
from lxml import etree
from pymongo import MongoClient



class XMu(object):


    def __init__(self, engine='xml', **kwargs):
        # Class-wide switches
        self.engine = engine
        self.verbose = False
        if self.engine == 'mongo':
            self.lower = False
            self.mongo_init(**kwargs)
        elif self.engine == 'xml':
            self.lower = True
            self.xml_init(**kwargs)
        else:
            print 'Error! Invalid engine: ' + self.engine
            sys.exit()

        """Vocabularies"""
        # Maps simplified aliases to path in XML document
        self.paths = {
            'catalog' : {
                'irn' : 'irn',
                'guids' : ['AdmGUIDValue_tab', 'AdmGUIDValue'],
                'prefix' : 'CatPrefix',
                'number' : 'CatNumber',
                'suffix' : 'CatSuffix',
                'division' : 'CatDivision',
                'catalog' : 'CatCatalog',
                'collection' : ['CatCollectionName_tab', 'CatCollectionName'],
                # Minerals
                'min_name' : 'MinName',
                'cut' : 'MinCut',
                'jewelery_type' : 'MinJeweleryType',
                # Meteorites
                'met_name' : 'MetMeteoriteName',
                'met_type' : 'MetMeteoriteType',
                'find/fall' : 'MetFindFall',
                # Geologic age
                'era' : ['AgeGeologicAgeEra_tab', 'AgeGeologicAgeEra'],
                'period' : ['AgeGeologicAgeSystem_tab', 'AgeGeologicAgeSystem'],
                'epoch' : ['AgeGeologicAgeSeries_tab', 'AgeGeologicAgeSeries'],
                'age' : ['AgeGeologicAgeStage_tab', 'AgeGeologicAgeStage'],
                # Stratigraphy
                'formation' : ['AgeGeologicAgeEra_tab', 'AgeGeologicAgeEra'],
                'group' : ['AgeGeologicAgeEra_tab', 'AgeGeologicAgeEra'],
                'member' : ['AgeGeologicAgeEra_tab', 'AgeGeologicAgeEra'],
                # Locality
                'species' : ['IdeTaxonRef_tab', 'ClaSpecies'],
                'country' : ['BioEventSiteRef', 'LocCountry'],
                'state' : ['BioEventSiteRef', 'LocProvinceStateTerritory'],
                'county' : ['BioEventSiteRef', 'LocDistrictCountryShire'],
                'ocean' : ['BioEventSiteRef', 'LocOcean'],
                'sea/gulf' : ['BioEventSiteRef', 'LocSeaGulf'],
                'bay/sound' : ['BioEventSiteRef', 'LocBaySound'],
                'archipelago' : ['BioEventSiteRef', 'LocArchipelago'],
                'island_group' : ['BioEventSiteRef', 'LocIslandGrouping'],
                'island' : ['BioEventSiteRef', 'LocIslandName'],
                'mine_district' : ['BioEventSiteRef', 'LocMiningDistrict'],
                'mine' : ['BioEventSiteRef', 'LocMineName'],
                'volcano' : ['BioEventSiteRef', 'VolVolcanoName'],
                'volcano_number' : ['BioEventSiteRef', 'VolVolcanoNumber'],
                'precise_locality' : ['BioEventSiteRef', 'LocPreciseLocaltion'],
                'geolocation' : ['BioEventSiteRef',
                                 'LocGeomorphologicalLocation'],
                'latitude' : ['BioEventSiteRef',
                              'LatLatitudeDecimal_nesttab',
                              'LatLatitudeDecimal_nesttab_inner',
                              'LatLatitudeDecimal'],
                'longitude' : ['BioEventSiteRef',
                              'LatLongitudeDecimal_nesttab',
                              'LatLongitudeDecimal_nesttab_inner',
                              'LatLongitudeDecimal'],
                # Specimen location
                'current1' : ['LocLocationRef_tab', 'LocLevel1'],
                'current2' : ['LocLocationRef_tab', 'LocLevel2'],
                'current3' : ['LocLocationRef_tab', 'LocLevel3'],
                'current4' : ['LocLocationRef_tab', 'LocLevel4'],
                'current5' : ['LocLocationRef_tab', 'LocLevel5'],
                'current6' : ['LocLocationRef_tab', 'LocLevel6'],
                'current7' : ['LocLocationRef_tab', 'LocLevel7'],
                'current8' : ['LocLocationRef_tab', 'LocLevel8'],
                # Multimedia
                'multimedia' : ['MulMultiMediaRef_tab', 'irn']
                },
            'events' : {
                'country' : 'LocCountry',
                'state' : 'LocProvinceStateTerritory',
                'county' : 'LocDistrictCountryShire',
                'township' : 'LocTownship',
                'precise_locality' : 'LocPreciseLocaltion',
                'geolocation' : 'LocGeomorphologicalLocation',
                },
            'multimedia' : {
                'irn' : 'irn',
                'path' : 'Multimedia',
                'spath' : ['Supplementary_tab', 'Supplementary'],
                'title' : 'MulTitle',
                'description': 'MulDescription',
                'creator' : ['MulCreator_tab', 'MulCreator'],
                'identifier' : 'MulIdentifier',
                'guids' : ['AdmGUIDValue_tab', 'AdmGUIDValue'],
                'guid_types' : ['AdmGUIDType_tab', 'AdmGUIDType']
                },
            'narratives' : {
                'irn' : 'irn',
                'title' : 'NarTitle',
                'narrative' : 'NarNarrative',
                'catirn' : ['ObjObjectsRef_tab', 'irn'],
                'person' : ['ParPartiesRef_tab', 'NamFullName'],
                'organization' : ['ParPartiesRef_tab', 'NamOrganisation'],
                'role' : []
                }
            }
        self.module = None

        # List of aliases for fields on import spreadsheet
        self.aliases = {
            'CatIrn' : 'irn',
            'CatCurIrn' : 'LocLocationRef',
            'CatDatIrn' : 'CatCatalogedByRef',
            'CatPrmIrn' : 'LocPermanentLocationRef',
            'CatTaxIrn' : 'IdeTaxonRef',
            'CatTraIrn' : 'AcqTransactionsRef'
            }

        # List of atomic fields by module
        self.atoms = {
            'catalog' : [
                'irn',
                'CatCatalog',
                'CatDivision',
                'CatNumber',
                'CatObjectType',
                'CatPrefix',
                'CatSuffix',
                'CatSpecimenCount',
                'CatWholePart',
                'MinCut',
                'MinXRayed',
                'BioEventSiteRef',
                'CatCatalogedByRef',
                'LocPermanentLocationRef',
                'SecRecordStatus'
                ],
            'events' : [
                'irn',
                'AquBottomDepthDetermination',
                'AquBottomDepthFromFath',
                'AquBottomDepthFromFt',
                'AquBottomDepthFromMet',
                'AquBottomDepthFromModifier',
                'AquBottomDepthToFath',
                'AquBottomDepthToFt',
                'AquBottomDepthToMet',
                'AquBottomDepthToModifier',
                'AquCruiseNumber',
                'AquDepthDetermination',
                'AquDepthFromFath',
                'AquDepthFromFt',
                'AquDepthFromMet',
                'AquDepthFromModifier',
                'AquDepthToFath',
                'AquDepthToFt',
                'AquDepthToMet',
                'AquDepthToModifier',
                'AquVerbatimBottomDepth',
                'AquVerbatimDepth',
                'AquVesselName',
                'ColCollectionMethod',
                'ColDateVisitedConjunction',
                'ColDateVisitedFrom',
                'ColDateVisitedFromModifier',
                'ColDateVisitedTo',
                'ColDateVisitedToModifier',
                'ColParticipantEtAl',
                #'ColParticipantString',
                #'ColParticipantStringAuto',
                'DepSourceOfSample',
                'ExpCompletionDate',
                'ExpExpeditionName',
                'ExpProjectNumber',
                'ExpStartDate',
                'LocArchipelago',
                'LocBaySound',
                #'LocContinent',
                'LocCountry',
                'LocDistrictCountyShire',
                'LocGeologicSetting',
                'LocGeomorphologicalLocation',
                'LocIslandGrouping',
                'LocIslandName',
                'LocJurisdiction',
                'LocMineName',
                'LocMiningDistrict',
                'LocNoFurtherLocalityData',
                'LocOcean',
                'LocPreciseLocation',
                'LocProvinceStateTerritory',
                'LocQUAD',
                'LocRecordClassification',
                'LocSeaGulf',
                'LocSiteNumberSource',
                'LocSiteParentRef',
                'LocSiteStationNumber',
                'LocTownship',
                'MapCoords',
                'MapName',
                'MapNumber',
                'MapOriginalCoordinateSystem',
                'MapScale',
                'MapType',
                'MetTotalSurfaceAreaUnit',
                'MetTotalSurfaceAreaValue',
                'TerElevationDetermination',
                'TerElevationFromFt',
                'TerElevationFromMet',
                'TerElevationFromModifier',
                'TerElevationToFt',
                'TerElevationToMet',
                'TerElevationToModifier',
                'TerVerbatimElevation',
                'VolHolocene',
                'VolRegionName',
                'VolRegionNumber',
                'VolSubRegionName',
                'VolSubRegionNumber',
                'VolVolcanoName',
                'VolVolcanoNumber',
                'SecRecordStatus'
                ]
            }

        # List of grids by module
        self.grids = {
            'catalog' : [
                ['AcqTransactionsRef_tab'],
                ['AdmGUIDIsPreferred_tab','AdmGUIDType_tab','AdmGUIDValue_tab'],
                ['CatOtherCountsType_tab', 'CatOtherCountsValue_tab'],
                ['CatOtherNumbersType_tab', 'CatOtherNumbersValue_tab'],
                ['IdeTaxonRef_tab', 'IdeNamedPart_tab',
                 'IdeTextureStructure_tab','IdeComments_tab'],
                ['LocLocationRef_tab', 'LocMovementNotes_tab',
                 'LocDateMoved0', 'LocMovedByRef_tab'],
                ['MeaType_tab',
                 'MeaVerbatimValue_tab','MeaVerbatimUnit_tab',
                 'MeaStandardizedValue_tab','MeaStandardizedUnit_tab'],
                ['MinColor_tab'],
                ['MulMultiMediaRef_tab'],
                ['NotNmnhText0','NotNmnhType_tab'],
                ['StaInventoryStatus_tab', 'StaInventoryRecordedByRef_tab',
                 'StaInventoryDate0', 'StaInventoryRemarks_tab'],
                ['ZooPreparation_tab','ZooPreparationCount_tab']
                ],
            'events' : [
                ['ColSiteVisitNumbers_tab'],
                ['LocSiteName_tab'],
                ['LocSiteOwnerRef_tab'],
                ['VolVolume_tab','VolVolumeUncertainty_tab'],
                ['ColTimeVisitedFrom0',
                 'ColTimeVisitedFromModifier_tab',
                 'ColTimeVisitedConjunction_tab',
                 'ColTimeVisitedTo0',
                 'ColTimeVisitedToModifier_tab'],
                ['ColParticipantRef_tab','ColParticipantRole_tab'],
                ['LatLatitude_nesttab',
                 'LatLongitude_nesttab',
                 'LatLatitudeDecimal_nesttab',
                 'LatLongitudeDecimal_nesttab',
                 'LatLatitudeVerbatim_nesttab',
                 'LatLongitudeVerbatim_nesttab',
                 'LatModifier_nesttab',
                 'LatComment_nesttab',
                 'LatDetSource_tab',
                 'LatLatLongDetermination_tab',
                 'LatDeterminedByRef_tab',
                 'LatDetDate0',
                 'LatRadiusVerbatim_tab',
                 'LatRadiusNumeric_tab',
                 'LatGeometry_tab',
                 'LatRadiusProbability_tab',
                 'LatRadiusUnit_tab',
                 'LatDatum_tab',
                 'LatCentroidLatitude0',
                 'LatCentroidLatitudeDec_tab',
                 'LatCentroidLongitude0',
                 'LatCentroidLongitudeDec_tab',
                 'LatDeriveCentroid_tab',
                 'LatCentroidLongitudeDec_tab',
                 'LatGeoreferencingNotes0'],
                ['MapUTMEastingFloat_tab',
                 'MapUTMNorthingFloat_tab',
                 'MapUTMZone_tab',
                 'MapUTMDatum_tab',
                 'MapUTMFalseEasting_tab',
                 'MapUTMFalseNorthing_tab',
                 'MapUTMMethod_tab',
                 'MapUTMDeterminedByRef_tab',
                 'MapUTMComment_tab'],
                ['MapOtherKind_tab',
                 'MapOtherCoordA_tab',
                 'MapOtherCoordB_tab',
                 'MapOtherDatum_tab',
                 'MapOtherSource_tab',
                 'MapOtherMethod_tab',
                 'MapOtherOffset_tab',
                 'MapOtherDeterminedByRef_tab',
                 'MapOtherComment_tab'],
                ['ColContractNumber_tab',
                 'ColContractRecipientRef_tab',
                 'ColContractDescription_tab'],
                ['ColPermitNumber_tab',
                 'ColPermitIssuerRef_tab',
                 'ColPermitDescription_tab'],
                ['NteText0','NteDate0',
                 'NteType_tab',
                 'NteAttributedToRef_nesttab',
                 'NteMetadata_tab'],
                ['MulMultiMediaRef_tab'],
                ['ColBibliographicRef_tab'],
                ['AdmGUIDIsPreferred_tab','AdmGUIDType_tab','AdmGUIDValue_tab']
                ]
            }


    ############################################################################
    # HELPER FUNCTIONS
    ############################################################################


    def assign_defaults(self, d, defaults):
        missing = list(set(defaults.keys()) - set(d.keys()))
        for key in missing:
            d[key] = defaults[key]
        return d




    def search(self, params):
        """Searches current record set for matching records

        Keyword arguments:
        params is a list of dictionaries, each representing a separate
        record
        """
        if self.engine == 'mongo':
            return self.mongo_search(params)
        else:
            return self.xml_search(params)




    def select(self, params):
        if self.engine == 'mongo':
            return self.mongo_search(params)
        else:
            self.xml_search(params, True)




    def find(self, *args):
        """Return data from the current record for give args"""
        if self.engine == 'mongo':
            return self.mongo_find(*args)
        else:
            return self.xml_find(*args)




    def records(self):
        if self.engine == 'mongo':
            return self.search([])
        else:
            return etree.iterparse(self.path, events=['end'], tag='Record', encoding='utf8')





    def count(self, records):
        """Return record count for query"""
        if self.engine == 'mongo':
            return records.count()
        else:
            return len(records)




    def close(self):
        """Close connection to Mongo"""
        if self.engine == 'mongo':
            self.client.disconnect()
            print 'Disconnected from MongoDB'
        else:
            pass




    ############################################################################
    # SHARED FUNCTIONS
    ############################################################################


    def dep_match_samples(self, catnums, attrs={}, default_suffix=False):
        # Look for unique match based on user-provided parameters
        matches = []
        irns = []
        params = []
        for catnum in catnums:
            params += emh.parse_catnum(catnum)
        # Match one by one
        for param in params:
            # Match natural suffix
            irn = self.search([param]).find('irn')
            if len(irn) == 1:
                d = {'irn' : irn[0]}
                matches.append(write_match(d))
                irns.append(irn[0])
                continue
            # Match forcing suffix
            if default_suffix and not 'CatSuffix' in param:
                param['CatSuffix'] = default_suffix
                irn = self.search([param]).find('irn')
                if len(irn) == 1:
                    d = {'irn' : irn[0]}
                    matches.append(write_match(d))
                    irns.append(irn[0])
                    continue
                print param
                del param['CatSuffix']
            # Match without division
            if 'CatDivision' in param:
                del param['CatDivision']
                irn = self.search([param]).find('irn')
                if len(irn) == 1:
                    d = {'irn' : irn[0]}
                    matches.append(write_match(d))
                    irns.append(irn[0])
                    continue
            # Match in EMu
            d = {}
            for key in param:
                if not param[key]:
                    param[key] = ''
                try:
                    d[self.mongo2emu[key]] = str(param[key])
                except:
                    d[key] = str(param[key])
            matches.append(write_match(d))
            irns.append(None)
        self.matches = matches
        self.irns = irns
        return self




    ############################################################################
    # MONGO FUNCTIONS
    ############################################################################


    def mongo_init(self, **kwargs):
        """Initialize MongoDB connection

        Mongo uses the following global variables:
          self.db
          self.module
          self.mongo2emu
          self.global_params
        """
        print 'Initializing MongoDB...'
        # Assign default keywords
        defaults = {
                'db' : 'ms',
                'module' : 'catalog'
                }
        kwargs = self.assign_defaults(kwargs, defaults)
        # Map field names
        self.emu2mongo = {
            'irn' : '_id',
            'CatDivision' : 'catdv',
            'CatPrefix' : 'catnb.catpr',
            'CatNumber' : 'catnb.catnm',
            'CatSuffix' : 'catnb.catsf',
            'MetMeteoriteNumber' : 'metmn',
            'idedn' : 'idedn' # Display name (Mongo only)
            }
        self.mongo2emu = dict(zip(self.emu2mongo.values(),
                                  self.emu2mongo.keys()))
        # Create connection to mongo
        path = ''
        self.client = MongoClient(path)
        while True:
            u = prompt('Username: ', r='[A-z0-9]+', confirm=False)
            p = getpass.findpass('Password: ')
            try:
                self.client.ms.authenticate(u, p)
            except:
                print 'Username or password incorrect!'
            else:
                break
        self.db = self.client[kwargs['db']]
        self.module = self.db[kwargs['module']]
        self.global_params = None




    def mongo_search(self, params):
        # Search Mongo using given plus global parameters
        query = {'$or' : [param for param in self.mongo_prep_query(params)]}
        if self.global_params:
            query = {'$and' : [self.global_params, query]}
        self.documents = self.module.find(query)
        return self




    def mongo_get(self, *args):
        """Return value for a given key in the current document"""
        return doc[self.emu2mongo[''.join(*args)]]




    def mongo_prep_query(self, params):
        """Adapts params to Mongo data model"""
        temp = []
        for param in params:
            mg_param = {}
            for key in param.keys():
                val = param[key]
                try:
                    if not key == 'CatSuffix':
                        val = int(val)
                except:
                    pass
                mg_param[self.emu2mongo[key]] = val
            temp.append(mg_param)
        params = temp
        return params


    ############################################################################
    # XML FUNCTIONS
    ############################################################################




    def xml_init(self, **kwargs):
        """Initialize XML instance

        XML instances use the following variables:
          self.fi = path to the EMu export
          self.path = path to the curernt working XML file
            self.full = path to the full XML dataset
            self.subset = path to an XML file containing a subset
        """
        print 'Initializing XML handler...'
        try:
            self.fi = kwargs['fi']
            self.full = kwargs['fo']
        except:
            print fill('Warning: No XML files specified.'
                       ' Many functions are not available.')
        else:
            # Check if user wants to force format. Otherwise reformat the
            # derived XML file only if it is older than the source file.
            try:
                kwargs['force_format']
            except:
                try:
                    open(self.full, 'rb')
                except:
                    print self.full + ' does not exist'
                    self.xml_format(self.fi, self.full)
                else:
                    t1 = time.ctime(os.path.getmtime(self.fi))
                    t2 = time.ctime(os.path.getmtime(self.full))
                    if t1 >= t2:
                        print self.full + ' is older than ' + self.fi
                        self.xml_format(self.fi, self.full)
            else:
                print 'User wants to format the file'
                if kwargs['force_format']:
                    self.xml_format(self.fi, self.full)

            self.subset = None
            self.path = self.full
            self.paths_found = {}  # dictionary tracking paths checked and found
        return self




    def xml_search(self, params, store=False):
        # Search for records matching params
        # Return lxml.etree object of matching records
        # params: list of dicts
        tree = etree.Element('Records')
        for event, element in self.records():
            # Check children against all parameters
            for key in params:
                matches = 0
                try:
                    match = self.find(param) == params[key]
                except:
                    pass
                else:
                    if match:
                        matches += 1
            if matches == len(params):
                tree.append(copy(element))
                break
            element.clear()
        return self




    def recurse_tree(self, element, tags, i=0, n=0):
        try:
            tags[i]
        except:
            pass
        else:
            for child in element:
                if child.tag == tags[i]:
                    if child.text:
                        print child.tag, child.text.strip()
                        n += 1
                    self.recurse_tree(child, tags, i + 1, n)
            print tags, n




    def xml_find(self, *args):
        """Return value for a given key"""
        # Handle aliases from self.paths
        try:
            args = self.paths[self.module][args[0]]
        except:
            pass
        else:
            if not isinstance(args, (list, tuple)):
                args = [args]
        path = '/'.join(args)
        results = []
        for child in self.record.xpath(path):
            if child.text:
                results.append(child.text)
            else:
                results.append('')
        try:
            self.paths_found[path].append(len(results))
        except:
            self.paths_found[path]  = [len(results)]
        if not '_tab' in path and not '_nesttab' in path:
            try:
                results = results[0]
            except:
                results = ''
        return results




    def xml_format(self, fi, fo, nbsp=''):
        """Convert EMu export to functioning XML"""
        print 'Formatting ' + fi + ' as XML...'
        start_time = datetime.datetime.now()
        with open(fo, 'wb') as fw:
            fw.write('<?xml version="1.0" encoding="utf-8"?>\n<Records>\n')
        with open(fi, 'rb') as f:
            delim = '\n  </tuple>\n'
            for s in self._chunk_in(f, ends_at=delim):
                master = etree.Element('Records')
                records = s.split(delim)[:-1]
                for rec in records:
                    root = etree.Element('Record')
                    active = root
                    # Reset variable for each record
                    containers = []  # list of named tables and tuples
                    keymap = {}      # tracks fields found
                    # Process record
                    lines = [s.strip() for s in rec.split('>\n')]
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        # Handle atoms
                        # Suppressing blank lines causes problems w/ grids
                        if line.startswith('<a'):
                            arr = line.split('>',1)
                            tag = arr[0].split('"')[1]
                            text = arr[1]\
                                   .rsplit('<',1)[0]\
                                   .decode('cp1252')
                            if self.verbose:
                                print 'Writing {}...'.format(tag)
                            atom = etree.SubElement(active, tag)
                            atom.text = text
                            # Add key to keymap
                            key = '/'.join(containers)
                            try:
                                keymap[key].append(tag)
                            except:
                                keymap[key] = [tag]
                        # Handle closing containers
                        elif line.startswith('</'):
                            container = containers.pop()
                            if self.verbose:
                                print 'Closing {}...'.format(container)
                            active = active.getparent()
                            # Skip table if next
                            try:
                                next_line = lines[i+1]
                            except:
                                pass
                            else:
                                if line.startswith('</tu')\
                                   and next_line.startswith('</ta'):
                                    i += 1
                                elif line.startswith('</tu')\
                                   and next_line.startswith('<tu'):
                                    containers.append(container)
                        # Handle opening containers
                        elif line.startswith('<t') and not '"e' in line:
                            try:
                                # Get name if table
                                container = line.split('>',1)[0].split('"')[1]
                            except IndexError:
                                # Tuples are unnamed, so they inherit
                                # the name of the container
                                if len(containers):
                                    if self.verbose:
                                        print 'Opening {}...'.format(container)
                                    active = etree.SubElement(active, container)
                            else:
                                if self.verbose:
                                    print 'Opening {}...'.format(container)
                                active = etree.SubElement(active, container)
                                containers.append(container)
                                # Skip tuple if next
                                next_line = lines[i+1]
                                if next_line.startswith('<tu'):
                                    i += 1
                        elif line.startswith('<!'):
                            containers = []
                        i += 1
                    # Check for missing fields in Ref_tabs
                    del keymap['']
                    for key in keymap:
                        tags = key.split('/')
                        elements = [root]
                        while len(tags):
                            tag = tags.pop(0)
                            new = []
                            for element in elements:
                                for child in element:
                                    if child.tag == tag:
                                        new.append(child)
                            elements = new
                        for element in elements:
                            for tag in keymap[key]:
                                for child in element:
                                    if child.tag == tag:
                                        break
                                else:
                                    if self.verbose:
                                        print 'Adding {} to {}...'\
                                              .format(tag, element.tag)
                                    etree.SubElement(element, tag)
                    master.append(root)
                # Write out at end of chunk
                output = ['  ' + etree.tostring(rec, pretty_print=True,
                                                encoding='utf8')\
                                 .replace('>\n', '>\n  ')\
                                 .rstrip(' ')
                          for rec in master.findall('Record')]
                with open(fo, 'ab') as fw:
                    fw.write(''.join(output))
        with open(fo, 'ab') as fw:
            fw.write('\n</Records>\n')
        print fo + ' written!'
        return self




    def xml_format3(self, fi, fo, nbsp=''):
        """Convert EMu export to functioning XML"""
        print 'Formatting ' + fi + ' as XML...'
        start_time = datetime.datetime.now()
        with open(fo, 'wb') as fw:
            fw.write('<?xml version="1.0" encoding="utf-8"?>\n<Records>\n')
        with open(fi, 'rb') as f:
            delim = '\n  </tuple>\n'
            for s in self._chunk_in(f, ends_at=delim):
                output = []
                records = s.split(delim)[:-1]
                for rec in records:
                    # Reset variable for each record
                    containers = [] # list of named tables and tuples
                    fields = {}
                    ind = ''        # indent
                    # Process record
                    lines = [s.strip() for s in rec.split('>\n')]
                    rec = []
                    for line in lines:
                        # Handle atoms
                        """Suppressing blank lines causes problems w/ grids"""
                        #if line.startswith('<a') and not '></' in line:
                        if line.startswith('<a'):
                            arr = line.split('>',1)
                            fld = arr[0].split('"')[1]
                            val = arr[1].rsplit('<',1)[0].decode('cp1252').encode('utf8')
                            rec.append('%s<%s>%s</%s>' % (ind,fld,val,fld))
                            # Get keys
                            keys = [containers[i]
                                    for i in xrange(0, len(containers))
                                    if not containers[i] in containers[:i]]
                            try:
                                fields['/'.join(keys)].append(fld)
                            except:
                                fields['/'.join(keys)] = [fld]
                        # Handle closing containers
                        elif line.startswith('</'):
                            try:
                                container = containers.pop()
                            except:
                                pass
                            else:
                                rec.append('%s</%s>' % (ind,container))
                        # Handle opening containers
                        elif line.startswith('<t') and not '"e' in line:
                            try:
                                # Process named container
                                container = line.split('>',1)[0].split('"')[1]
                            except IndexError:
                                # Process tuples
                                if len(containers):
                                    container = containers[len(containers)-1]
                                    containers.append(container)
                                    rec.append('%s<%s>' % (ind,container))
                            else:
                                containers.append(container)
                                rec.append('%s<%s>' % (ind,container))
                        elif line.startswith('<!'):
                            # Handle comment
                            containers = []
                            fields = {}
                        # Handle repeated fields
                        try:
                            if rec[-1] == rec[-2]:
                                rec.pop()
                        except:
                            pass
                    # Add placeholder to empty tables
                    i = 0
                    insert = {}
                    while i < len(rec):
                        try:
                            that = rec[i + 1]
                        except:
                            pass
                        else:
                            this = rec[i].strip('<>')
                            # Check for empty tables
                            if this == that.strip('<>/')\
                               and that.startswith('</'):
                                s ='<Placeholder></Placeholder>'
                                if this.endswith('_nesttab'):
                                    s = ('<{0}_inner>{1}'
                                         '</{0}_inner>').format(this, s)
                                insert[i] = s
                            # Check for ref_tabs that have multiple values
                            if this.endswith(('_inner', 'Ref_tab')):
                                n = 0
                            elif this.startswith('<atom'):
                                if n:
                                    print 'ERROR'
                                else:
                                    n += 1
                        i += 1
                    for i in sorted(insert.keys())[::-1]:
                        rec.insert(i + 1, insert[i])
                    print '\n'.join(rec)
                    # Make sure tables have all the proper fields
                    root = etree.fromstring('<Record>' +
                                            ''.join(rec).strip() +
                                            '</Record>')
                    for key in [fld for fld in fields if bool(fld)]:
                        for fld in fields[key]:
                            element = copy(root)
                            tags = key.split('/') + [fld]
                            i = 0
                            while i < len(tags):
                                tag = tags[i]
                                for child in element:
                                    if child.tag == tag:
                                        element = child
                                        break
                                else:
                                    path = '/'.join(tags[:i] + ['Placeholder'])
                                    tree = root.find(path)
                                    try:
                                        parent = tree.getparent()
                                    except:
                                        print 'SERIOUS PROBLEM'
                                        print '\n'.join(rec)
                                        print '-' * 60
                                        print '/'.join(tags)
                                        print 'KEY', key
                                        print 'FLD', fld
                                        print 'PTH', path
                                        raise
                                    else:
                                        #print 'Added {} to {}'.format(
                                        #    tag,
                                        #    parent.tag)
                                        etree.SubElement(parent, tag)
                                i += 1
                    # Remove placeholders
                    for element in root.xpath('//Placeholder'):
                        element.getparent().remove(element)
                    rec = ['<' + s + '>' for s
                           in etree.tostring(root).split('><')]
                    rec[0] = '<Record>'
                    rec.pop()
                    rec.append('</Record>')
                    output += rec
                with open(fo, 'ab') as fw:
                    fw.write('\n'.join(output))
        with open(fo, 'ab') as fw:
            fw.write('\n</Records>\n')
        print fo + ' written!'
        return self




    def xml_format2(self, fi, fo, nbsp=''):
        """Convert EMu export to functioning XML"""
        print 'Formatting ' + fi + ' as XML...'
        start_time = datetime.datetime.now()
        with open(fo, 'wb') as fw:
            fw.write('<?xml version="1.0" encoding="utf-8"?>\n<Records>\n')
        with open(fi, 'rb') as f:
            delim = '\n  </tuple>\n'
            for s in self._chunk_in(f, ends_at=delim):
                output = []
                records = s.split(delim)[:-1]
                for rec in records:
                    # Reset variable for each record
                    containers = [] # list of named tables and tuples
                    ind = ''        # indent
                    # Process record
                    output.append('%s<Record>' % '')
                    lines = [s.strip() for s in rec.split('>\n')]
                    for line in lines:
                        # Handle atoms
                        """Suppressing blank lines causes problems w/ grids"""
                        #if line.startswith('<a') and not '></' in line:
                        if line.startswith('<a'):
                            arr = line.split('>',1)
                            fld = arr[0].split('"')[1]
                            val = arr[1].rsplit('<',1)[0].decode('cp1252').encode('utf8')
                            output.append('%s<%s>%s</%s>' % (ind,fld,val,fld))
                        # Handle closing containers
                        elif line.startswith('</'):
                            try:
                                container = containers.pop()
                            except:
                                pass
                            else:
                                output.append('%s</%s>' % (ind,container))
                        # Handle opening containers
                        elif line.startswith('<t') and not '"e' in line:
                            try:
                                # Process named container
                                container = line.split('>',1)[0].split('"')[1]
                            except IndexError:
                                # Process tuples
                                if len(containers):
                                    container = containers[len(containers)-1]
                                    containers.append(container)
                                    output.append('%s<%s>' % (ind,container))
                            else:
                                containers.append(container)
                                output.append('%s<%s>' % (ind,container))
                        elif line.startswith('<!'):
                            # Handle comment
                            containers = []
                        # Handle repeated fields
                        try:
                            if output[-1] == output[-2]:
                                output.pop()
                        except:
                            pass
                    output.append('%s</Record>' % '')
                # Clean empty containers
                temp = []
                x = 0
                while x < len(output):
                    print output[x]
                    raw_input()
                    try:
                        s1 = output[x]
                        s2 = output[x+1]
                    except:
                        temp.append(s1)
                    else:
                        if s1 == s2:
                            temp.append(s1)
                            x += 1
                        elif s1.strip('</>') != s2.strip('</>'):
                            temp.append(s1)
                        elif s1.startswith('</') and not s2.startswith('</'):
                            temp.append(s1)
                        else:
                            x += 1
                    x += 1
                with open(fo, 'ab') as fw:
                    fw.write('\n'.join(temp))
        with open(fo, 'ab') as fw:
            fw.write('\n</Records>\n')
        print fo + ' written!'
        return self




    def fast_iter(self, func):
        context = self.records()
        for event, element in context:
            result = func(element)
            element.clear()
            while element.getprevious() is not None:
                del element.getparent()[0]
            if not result and not result == None:
                break
        del context
        # Notify user paths checked and found
        print 'Path information:'
        for key in sorted(self.paths_found):
            val = self.paths_found[key]
            print key + ': ', max(val)




    ############################################################################
    # Helper functions
    ############################################################################


    def fill_grid(self, grids):
        """Test grids to assure that they are the proper length

        EMu does not export a blank cell for any empty cell in a
        column below the last populated cell, even if other cells
        are populated in lower rows. This function appends blank
        values at the list for any grid that has too few entries,
        including blanks.

        Empty cells above the last populated cell are included as
        blanks in the export.

        @list grids (list of lists)
        """

        n = max([len(grid) for grid in grids])
        return [grid + [''] * (n - len(grid)) for grid in grids]





    def find_all_fields(self):
        # Get list of all fields
        all_fields = []
        for key in self.atoms:
            all_fields += self.atoms[key]
        for key in self.grids:
            for lst in self.grids[key]:
                all_fields += [s.split('_')[0].rstrip('0') for s in lst]
        for key in self.aliases:
            all_fields.append(key)
        return set(all_fields)




    def write_match(self, d, indent='', fields=[], tables=[]):
        if not len(fields):
            fields = d.keys()
        arr = self.write_import(None, {0:d}, fields,
                                tables, update=True)[2:-2][0]\
                                .replace(' row="+"','').split('\n')
        s = '\n'.join([indent + s for s in arr]) + '\n'
        regex = re.compile(' group="tab\d\d\d"')
        s = regex.sub('', s)
        return s




    def write_import(self, fp, d, fields, tables=[],
                     encoding='utf-8', module='ecatalogue',
                     update=False):
        arr = []
        arr.append('<?xml version="1.0" encoding="{}" ?>\n' \
                    '<table name="{}">'.format(encoding, module))
        i = 1
        for key in sorted(d.keys()):
            rec = d[key]
            arr.append('\n  <!--Row {} -->\n  <tuple>'.format(i))
            s = ''
            for fld in fields:
                try:
                    s += self.atom(rec, fld, update=update)
                except:
                    print 'Error: {0}: {1}={2}'.format(key, fld, rec[fld])
                    print self.atom(rec, fld, update=update)
                    print s
            for tab in tables:
                # Each tab is a set of related grids
                n = 0
                for t in tab:
                    fld = t.split('_')[0].rstrip('0')
                    if fld in rec:
                        if n and n != len(rec[fld]):
                            print rec
                            raw_input('Grid mismatch ({0}): {1}'\
                                      .format(key, '; '.join(tab)))
                        n = len(rec[fld])
                for t in tab:
                    s += self.grid(rec, t, update=update)
            arr.append(s.rstrip())
            arr.append('  </tuple>')
            i += 1
        arr.append('</table>')
        if fp:
            with open(fp, 'wb') as f:
                chunked = self._chunk_out(arr, 1024)
                while chunked:
                    try:
                        f.write('\n'.join(next(chunked)))
                    except StopIteration:
                        break
            print '{} written!'.format(fp)
        else:
            return arr





    def atom(self, d, fld, n=4, encoding='utf-8', update=False):
        # Write atomic field
        try:
            d[fld]
        except:
            return ''
        else:
            # Suppress blank fields if update is false
            if not len(d[fld]) and not update:
                return ''
            # Handle references
            elif fld.endswith('Ref'):
                # Handle dictionaries
                if isinstance(d[fld], dict):
                    atoms = []
                    for key in d[fld]:
                        # Warn user if d[fld] is not a string
                        if not isinstance(d[fld][key], str) \
                           and not isinstance(d[fld][key], unicode):
                            raw_input('Error: ' + fld + ' contains illegal data!')
                        # Handle illegal entities
                        d[fld][key] = self.handle_entities(d[fld][key])
                        atoms.append('<atom name="'+ key + '">' +\
                                     d[fld][key] + '</atom>')
                    s = self.nbsp(n) + '<tuple name="' + fld + '">\n' +\
                        self.nbsp(n+2) + ('\n' + self.nbsp(n+2)).join(atoms) + '\n' +\
                        self.nbsp(n) + '</tuple>\n'
                # Handle preformatted content (HACKY HACKY HACK HACK)
                elif '/atom' in d[fld]:
                    s = self.nbsp(n) + '<tuple name="' + fld + '">\n' +\
                    self.nbsp(0) + d[fld] +\
                    self.nbsp(n) + '</tuple>\n'
                # Handle strings (assumes field is irn)
                else:
                    try:
                        d[fld] = self.handle_entities(d[fld])
                    except:
                        print 'Fatal error on the following data:'
                        raw_input(d)
                        sys.exit()
                    else:
                        if len(d[fld]) > 8:
                            print 'Field is too long to be irn:\n"' +\
                                  d[fld][:70] + '"'
                    s = self.nbsp(n) + '<tuple name="' + fld + '">\n' +\
                        self.nbsp(n+2) + '<atom name="irn">' + d[fld] + '</atom>\n' +\
                        self.nbsp(n) + '</tuple>\n'
                return s
            # Handle strings
            else:
                # Warn user if d[fld] is not a string
                if not isinstance(d[fld], str) and not isinstance(d[fld], unicode):
                    raw_input('Error: ' + fld + ' is not a string!')
                # Handle illegal entities
                d[fld] = self.handle_entities(d[fld])
                # Write atomic field
                s = self.nbsp(n) + '<atom name="' + fld + '">' + d[fld] + '</atom>\n'
                # Encode as specified
                try:
                    s = s.encode(encoding)
                except:
                    for c in s:
                        try:
                            c.encode(encoding)
                        except:
                            print 'Error: Could not encode "{}" as utf8!'\
                                  .format(c)
                return s




    def grid(self, d, tab, n=4, encoding='utf-8', update=False):
        # Write grid
        # Get field from table name
        fld = tab.split('_')[0].rstrip('0')
        try:
            d[fld]
        except:
            return ''
        else:
            # Suppress empty tables if update is false
            if not bool(d[fld]) and not update:
                return ''
            else:
                # Warn user if d[fld] is not a list
                if not isinstance(d[fld], list):
                    raw_input('Error: ' + fld + ' is not a list!')
                # Write output string
                s = ''
                s += self.nbsp(n) + '<table name="' + tab + '">\n'
                i = 1
                for val in d[fld]:
                    # Set group
                    group = ''
                    if update and 'nesttab' in tab:
                        group = ' group="ntab{:0>3d}"'.format(i)
                    elif update:
                        group = ' group="tab{:0>3d}"'.format(i)
                    # Detect irns. Used a separate variable because
                    # grids go screwy when an irn is placed between
                    # text records.
                    row = fld
                    try:
                        int(val)
                    except:
                        pass
                    else:
                        if tab.endswith('Ref_tab') and 7 <= len(val) <= 8:
                            row = 'irn'
                    temp = { row : val }
                    if update:
                        s += self.nbsp(n+2) + '<tuple row="+"' + group + '>\n'
                    else:
                        s += self.nbsp(n+2) + '<tuple' + group + '>\n'
                    if tab.endswith('_nesttab'):
                        s += self.nbsp(n+4) + '<table name="' + tab + '_inner">\n'
                        s += self.nbsp(n+6) + '<tuple>\n'
                        s += self.atom(temp, row, n+8, encoding=encoding,
                                       update=update)
                        s += self.nbsp(n+6) + '</tuple>\n'
                        s += self.nbsp(n+4) + '</table>\n'
                    else:
                        val = self.atom(temp, row, n+4, encoding=encoding,
                                        update=update)
                        # Strip tuple tags and normalize indentation for references
                        if tab.endswith('Ref_tab'):
                            arr = val.split('\n')
                            # Strip tuple tags, if present
                            if val.strip().startswith('<tuple'):
                                arr = arr[1:-2]
                            indent = ''
                            for val in arr:
                                if '<atom' in val:
                                    indent = ' ' * (len(val) - len(val.lstrip()))
                                    break
                            val = '\n'.join([self.nbsp(n+4) +
                                             val.replace(indent,'',1)
                                             for val in arr])
                        #if tab.endswith('Ref_tab'):
                        #    val = '\n'.join(val.split('\n')[1:-2]) + '\n'
                        # Normalize indentation
                        #if val.strip().startswith('<tuple'):
                        #    val = '\n'.join([self.nbsp(n+4) + val.strip() for val
                        #                     in val.rstrip().split('\n')[1:][:-1]])
                        #    val += '\n'
                        s += val
                    s = s.rstrip() + '\n'
                    s += self.nbsp(n+2) + '</tuple>\n'
                    i += 1
                s += self.nbsp(n) + '</table>\n'
                return s




    def link_module(self, module, indent='  ',
                    encoding='cp1252', active_only=True):
        d = {}
        # Process atoms
        for key in self.atoms[module]:
            try:
                d[key] = rec[key]
            except:
                pass
            else:
                del rec[key]
        # Add empty fields
        found = []
        for key in self.atoms[module]:
            try:
                d[key]
            except:
                d[key] = ''
            else:
                found.append(key)
        for lst in self.grids[module]:
            for key in lst:
                key = key.split('_')[0].rstrip('0')
                try:
                    d[key]
                except:
                    d[key] = []
        # Force active
        if active_only:
            d['SecRecordStatus'] = 'Active'
        # Write and return decoded string
        s = self.write_match(d, indent, self.atoms[module], self.grids[module])
        return s.decode(encoding)




    ############################################################################
    # Audit module functions
    ############################################################################


    def auditor(self, xml, fo, criteria, show_all=False):
        print 'Processing audits...'
        # Pop field criteria, if exists
        try:
            field_criteria = {'field' : criteria.pop('field')}
        except:
            field_criteria = {'field' : {'not' : []}}
        # Check for audits matching criteria
        rows = []
        context = etree.iterparse(xml, tag='Record')
        for event,element in context:
            self.record = element
            # Get audit information
            audit_params = {
                'irn' : self.find('irn'),
                'module' : self.find('AudTable'),
                'operation' : self.find('AudOperation'),
                'program' : self.find('AudProgram'),
                'user' : self.find('AudUser'),
                'date' : self.find('AudDate'),
                'time' : self.find('AudTime'),
                'key' : self.find('AudKey')
                }
            # Only include record if it matches criteria
            if self._check_params(audit_params, criteria):
                new = self._process_audit(field_criteria,
                                          'AudNewValue_tab', 'AudNewValue')
                old = self._process_audit(field_criteria,
                                          'AudOldValue_tab', 'AudOldValue')
                # Combine new and old
                keys = list(set(new.keys() + old.keys()))
                for key in keys:
                    try:
                        new[key]
                    except:
                        new[key] = []
                    try:
                        old[key]
                    except:
                        old[key] = []
                if len(new) >= len(old):
                    for fld in new:
                        while len(old[fld]) < len(new[fld]):
                            old[fld].append('')
                else:
                    for fld in old:
                        while len(new[fld]) < len(old[fld]):
                            new[fld].append('')
                # Append row
                for fld in new:
                    values = zip(new[fld], old[fld])
                    if not show_all:
                        values = [val for val in values if val[0] != val[1]]
                    i = 1
                    for val in values:
                        row = [
                            audit_params['key'],
                            fld,
                            str(i),
                            self.handle_entities(val[1], False),
                            self.handle_entities(val[0], False),
                            audit_params['date'],
                            audit_params['time'],
                            audit_params['user'],
                            audit_params['program'],
                            audit_params['module'],
                            audit_params['operation'],
                            audit_params['irn']
                            ]
                        rows.append(row)
                        i += 1
        if len(rows):
            # Sort by module IRN, then reversed audit IRN
            rows = sorted(rows, key=itemgetter(0))
            sorted(rows, key=itemgetter(10), reverse=True)
            keys = [
                'IRN',
                'Field',
                'Row',
                'Old Value',
                'New Value',
                'Date',
                'Time',
                'User',
                'Program',
                'Module',
                'Operation',
                'IRN (Audit)'
                ]
            while True:
                try:
                    open(fo, 'wb')
                except:
                    raw_input(fill('{} is open! Please close it and press ' \
                                   'any key to continue.'.format(fo)))
                else:
                    break
            with open(fo, 'wb') as f:
                w = csv.writer(f, delimiter=',', quotechar='"',
                               quoting=csv.QUOTE_ALL)
                w.writerow(keys)
                for row in rows:
                    row = [s.encode('cp1252') for s in row]
                    w.writerow(row)
            print fill('{} written!'.format(fo))
        else:
            print fill('No data from {} matched your criteria!'.format(xml))




    def _check_params(self, params, criteria):
        # Run through criteria
        #  params is a dict read from the audit record
        #  criteria is a dict formatted as follows:
        #   d[key]['is'] = []
        #   d[key]['not'] = []
        for key in criteria:
            # Processes is. Fails if param NOT in criteria
            try:
                criteria[key]['is']
            except:
                pass
            else:
                if not params[key] in criteria[key]['is']:
                    break
            # Processes not. Fails if param IS in criteria
            try:
                criteria[key]['not']
            except:
                pass
            else:
                if params[key] in criteria[key]['not']:
                    break
        else:
            # Returns True if function never breaks
            return True
        # Returns False if function hits break
        return False




    def _process_audit(self, criteria, *args):
        # Process values from an audit record
        values = self.find(*args)
        d = {}
        if bool(values):
            if not isinstance(values, list):
                values = [values]
            for val in values:
                fld, val = [s.strip() for s in val.split(':', 1)]
                if self._check_params({'field' : fld}, criteria):
                    d[fld] = []
                    for v in val.split('</tuple>'):
                        try:
                            v = v.rsplit('<', 1)[0].rsplit('<atom>', 1)[1]
                        except:
                            pass
                        else:
                            d[fld].append(v)
        return d




    ############################################################################
    # Helper functions
    ############################################################################


    def _chunk_in(self, f, size=2**25, ends_at=''):
        while True:
            data = f.read(size)
            if not data:
                break
            if len(ends_at):
                i = 0
                while not data.endswith(ends_at):
                     data += f.read(1)
                     i += 1
                     if i > 10000:
                         break
            yield data




    def _chunk_out(self, arr, n):
        for i in xrange(0, len(arr), n):
            yield arr[i:i+n]




    def nbsp(self, n, sp=' '):
        return sp * n




    def write_emu_search(self, data, field, indent='\t'):
        # Writes search that can be pasted into the EMu Show Search
        s1 = '{0}(\n{0}{0}{1}='.format(indent, field)
        s2 = '\n{0})\n'.format(indent)
        s3 = '{0}or\n'.format(indent)
        j = '{1}{2}{0}'.format(s1, s2, s3)
        return '{0}{1}{2}'.format(s1, j.join(data), s2)




    def handle_entities(self, s, decode=True):
        # Encode/decode entities from XML
        entities = {
            '&' : '&amp;',
            '<' : '&lt;',
            '>' : '&gt;'
            }
        order = ['&', '<', '>']
        for key in order:
            val = entities[key]
            if decode:
                s = s.replace(key, val)
            else:
                s = s.replace(val, key)
        return s




    def find_dupes(self, xml, fo='', exclude=[]):
        # Hash records to find duplicates
        print 'Checking for duplicates...'
        hashes = {}
        context = etree.iterparse(xml, tag='Record')
        for event,element in context:
            # Clean up record
            rec = xmltodict.parse(etree.tostring(element))['Record']
            irn = rec.pop('irn')
            for field in exclude:
                try:
                    rec.pop(field)
                except:
                    pass
            # Hash and store by irn
            h = hashlib.sha256(json.dumps(rec).lower()).hexdigest()
            try:
                hashes[h].append(irn)
            except:
                hashes[h] = [irn]
            if not len(hashes) % 10000:
                print '{:,} unique records found!'.format(len(hashes))
        # Write duplciates to file if path specified
        print '{:,} unique records found!'.format(len(hashes))
        if bool(fo):
            with open(fo, 'wb') as f:
                for key in hashes:
                    irns = hashes[key]
                    if len(irns) > 5:
                        irns = sorted(irns)
                        fn = '{}.txt'.format(irns[0])
                        with open(os.path.join('searches', fn), 'wb') as fw:
                            fw.write(self.write_search(irns, 'irn'))
                    elif len(irns) > 1:
                        f.write('%s\n' % ','.join(irns))
        return hashes
