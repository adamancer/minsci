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

from ..helpers.py import cprint



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
                    t1 = os.path.getmtime(self.fi)
                    t2 = os.path.getmtime(self.full)
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
                text = unicode(child.text)
                results.append(self.handle_entities(text, False))
            else:
                results.append(u'')
        try:
            self.paths_found[path].append(len(results))
        except:
            self.paths_found[path]  = [len(results)]
        if not '_tab' in path and not '_nesttab' in path:
            try:
                results = results[0]
            except:
                results = u''
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
                rec_num = 0
                for rec in records:
                    try:
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
                    except:
                        # Print the record that killed the formatter,
                        # then throw an error
                        print 'Fatal error: Could not process record'
                        print rec
                        raw_input('Press any key for traceback')
                        raise
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




    def read_fields(self):
        """Reads paths to fields from schema in EMu XML export"""
        fields = []
        schema = []
        with open(self.fi, 'rb') as f:
            for line in f:
                schema.append(line.rstrip())
                if line.strip() == '?>':
                    break
        schema = schema[schema.index('<?schema')+1:-1]
        containers = ['schema']
        for field in schema:
            kind, field = [s.strip() for s in field.rsplit(' ', 1)]
            if kind in ('table', 'tuple'):
                containers.append(field)
                continue
            if field == 'end':
                containers.pop()
            else:
                fields.append('/'.join(containers[2:] + [field]))
        return fields[1:-1]




    def read_schema(self, fp):
        """Reads EMu schema file to dictionary

        The EMu schema file includes (but is not limted to) these fields:
         ColumnName: Name of field, table, or reference in current module
         DataKind: One of the following:
           dkAtom
           dkNested
           dkTable
           dkTuple
         DataType: One of the following:
           Currency
           Date
           Float
           Integer
           Latitude
           Longitude
           String
           Text
           Time
           UserId
           UserName
         ItemName: Field name in current module
         RefLink: Name with Ref
         RefKey: Field used to link with other module
         LookupName: Name of lookup list. Appears only in highest field
          in a given lookup hierarchy.
         LookupParent: The name of next highest field in a lookup hierarchy.
        """

        print 'Reading EMu schema from {}...'.format(fp)
        # These regexes are used to split the .pl file into
        # modules and fileds
        re_module = re.compile('\te[a-z]+ =>.*?\{.*?\n\t\}', re.DOTALL)
        re_field = re.compile('"[A-z].*?\},', re.DOTALL)
        re_lines = re.compile('[A-z].*,', re.DOTALL)
        try:
            with open(fp, 'rb') as f:
                modules = re_module.findall(f.read())
        except OSError:
            print '.pl file not found'
            raise
        schema = {}
        for module in modules:
            module_name = module.split('\n')[0].strip().split(' ')[0]
            schema[module_name] = {}
            fields = re_field.findall(module)
            for field in fields:
                d = {}
                lines = [s.strip() for s in field.split('\n')
                         if bool(s.strip())]
                field_name = lines[0].split(' ')[0].strip('"')
                lines = lines[2:len(lines)-1]
                for line in lines:
                    try:
                        key, val = [s.strip('",') for s in line.split(' => ')]
                    except:
                        pass
                    else:
                        d[key] = val
                schema[module_name][field_name] = d
        return schema




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
        #print 'Path information:'
        #for key in sorted(self.paths_found):
        #    val = self.paths_found[key]
        #    print key + ': ', max(val)




    ############################################################################
    # Helper functions
    ############################################################################


    def fill_grid(self, grids):
        """Test grids to assure that they are the proper length

        EMu does not export a blank cell for any empty cell in a
        column below the last populated cell, even if other cells
        in the same table are populated in lower rows. This
        function appends blank values at the list for any grid
        that has too few entries.

        Empty cells above the last populated cell are included
        in the export.

        Args:
            grids (list): list of values for all fields in one table

        Returns:
            List of values padded to the length of the longest list
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
        """Writes formatted string used to match record in another module

        Basically just a wrapper for the write_import function set
        to return a string instead of writing to a file.

        Args:
            fp (str): path to import file. If None, returns record as list.
            d (dict): record keyed to EMu field names
            indent (str): string to prepend to each line
            fields (list): atomic fields to include in import
            tables (list): lists of fields in the same tables

        Returns:
            Formatted record suitable for matching to another module
            during import.
        """
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
        """Write an XML import for EMu

        By default, creates new records. Blank fields are excluded.
        If irn specified, will overwrite existing record. The exact
        behavior of the update depends on the update flag. If True, all
        fields in d are included (even blanks) and data in grids will
        be appended to the appropriate table. If False, blanks will be
        excluded and tables will be overwritten by the new rows.

        Args:
            fp (str): path to import file. If None, returns record as list.
            d (dict): record keyed to EMu field names
            fields (list): atomic fields to include in import
            tables (list): lists of fields in the same tables
            encoding (str): encoidng of import file
            module (str): EMu name for module
            update (bool): controls behavior of update

        Returns:
            If fp is None, returns a list containing the lines of the
            import record. Otherwise returns None.
        """
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
                            raw_input('Grid mismatch ({0}): {1}'\
                                      .format(key, '; '.join(tab)))
                        n = len(rec[fld])
                for t in tab:
                    s += self.grid(rec, t, update=update)
            arr.append(s.rstrip())
            arr.append('  </tuple>')
            i += 1
        arr.append('</table>')
        # Warn user if tables are at risk of being overwritten. Typically,
        # updates are flagged rows are appended to the table. However, the
        # update flag doesn't actually control whether or not existing
        # records are modified; that falls to whether the irn field is
        # populated or not. If the irn is populated and update is not set
        # to True, existing tables will be OVERWRITTEN. This may be the
        # desired behavior, so this is only a warning.
        if 'irn' in fields and len(tables) and update == False:
            cprint('Warning: irn in fields and update is False.'
                   ' The following tables may be overwritten:'
            for table in tables:
                print ', '.join(table)
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
        """Writes atomic field

        Args:
            d (dict): record keyed to EMu field names
            fld (str): name of atomic field
            n (int): number of spaces with which to prefix line
            encoding (str): encoding of the import file
            update (bool): controls behavior of update as described
                in the comment on the write_import function

        Returns:
            String as <FieldName>Value</FieldName>. If d[fld] is
            empty, returns empty string unless update is True.
        """
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
        """Writes table based on list of fields

        Individual fields in a given table are padded to match the
        longest list for that table. Handles tables and nested tables.

        Args:
            d (dict): record keyed to EMu field names
            tab (list): fields in a given table
            n (int): number of spaces with which to prefix line
            encoding (str): encoding of the import file
            update (bool): controls behavior of update as described
                in the comment on the write_import function

        Returns:
            String containing the properly formatted table
        """
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
                    if update:
                        group = ' group="grp{:0>3d}"'.format(i)
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
    # Helper functions
    ############################################################################


    def _chunk_in(self, f, size=2**24, ends_at=''):
        while True:
            data = f.read(size)
            if not data:
                break
            if len(ends_at):
                start_length = len(data)
                i = 0
                while not data.endswith(ends_at):
                     data += f.read(1)
                     i += 1
                     # End of file is when read stops returning data
                     if not len(data) == (start_length + i):
                         print 'Reached end of file!'
                         break
                     # Max number of characters to check should be
                     # much greater than a reasonable record length
                     if i > 10**6:
                         print 'Warning: Could not locate complete record'
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
