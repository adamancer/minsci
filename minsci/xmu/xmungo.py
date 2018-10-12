"""Reads data from NMNH MongoDB collections database"""
from __future__ import print_function
from __future__ import unicode_literals

from builtins import input
from builtins import str
from builtins import range
from builtins import object
import time

import getpass
import json
from datetime import datetime

import pymongo
from pymongo.operations import ReplaceOne, DeleteOne

from .xmu import XMu, XMuRecord
from ..helpers import cprint


class MongoBot(object):
    """Contains methods to connect and interact with NMNH MongoDB"""

    def __init__(self, username, password, instance=None, container=None):
        self.username = username
        self.password = password
        self.instances = {
            'production': {
                'host': 'nmnh-rcismngo01-int,nmnh-rcismngo02-int',
                'login_db': 'admin',
                'db': 'cs',
                'collections': ['catalog', 'narrative']
                },
            #'development': {
            #    'host': 'nmnh-rcisdev2:27017',
            #    'login_db': 'ms',
            #    'db': 'ms',
            #    'collections': ['catalog', 'narrative']
            #    }
        }
        self.jsonpath = 'xmungo.json'
        self.connections = {}
        for nickname in self.instances:
            self.connect(nickname)
        self.collection = None
        if instance is not None and container is not None:
            self.collection = self.set_collection(instance, container)


    def connect(self, nickname):
        """Store connection to a server in a dict"""
        instance = self.instances[nickname]
        host = instance['host']
        login_db = instance['login_db']
        collections = instance['collections']
        login_server = '/'.join([host.rstrip('/'), login_db.strip('/')])
        client = pymongo.MongoClient('mongodb://{}'.format(login_server))
        while True:
            print('Connecting to {}...'.format(login_server))
            # User credentials
            if self.password is None:
                print('Username: ' + self.username)
                self.password = getpass.getpass('Password: ')
            try:
                client[login_db].authenticate(self.username, self.password)
            except (ValueError, pymongo.errors.OperationFailure):
                print('Invalid password!')
            else:
                break
        client_db = client[instance['db']]
        connection = {}
        for collection in collections:
            connection[collection] = client_db[collection]
        self.connections[nickname] = connection


    def set_collection(self, instance, collection):
        """Selects the collection to use"""
        self.collection = self.connections[instance][collection]


    @staticmethod
    def change_password(username, database):
        """Changes password on db"""
        np1 = getpass.getpass('New password    : ')
        np2 = getpass.getpass('Confirm password: ')
        if np1 == np2:
            database.add_user(username, np1)


    def sync(self, sync_from, sync_to, collection, query=None):
        """Synchronizes development server to production"""
        if sync_to == 'production' and sync_from == 'development':
            raise Exception('Sync is going the wrong way!')
        print('Syncing {} in {} to {}...'.format(collection, sync_to, sync_from))
        src = self.connections[sync_from][collection]
        dst = self.connections[sync_to][collection]
        queue = []
        checked = 0
        updated = 0
        # Set up query
        if query is None:
            query = {}
        query.update({'catdp': 'ms'})
        # Update records based on changes in production
        cursor = src.find(query)
        print((' {:,} records matching {} have'
               ' been found!').format(cursor.count(), query))
        for sdoc in cursor:
            irn = sdoc['_id']
            try:
                ddoc = dst.find({'_id': irn})[0]
            except IndexError:
                ddoc = None
            if sdoc != ddoc:
                queue.append(ReplaceOne({'_id': irn}, sdoc, True))
                if len(queue) == 500:
                    dst.bulk_write(queue)
                    updated += len(queue)
                    queue = []
            checked += 1
            if not checked % 1000:
                print((' {:,} records updated'
                       ' ({:,} checked)').format(updated, checked))
        if len(queue):
            dst.bulk_write(queue)
            updated += len(queue)
            queue = []
        # Look for records that have been deleted from production
        deleted = 0
        print('Looking for records deleted from {}...'.format(sync_from))
        sirns = [doc['_id'] for doc in src.find(query, [])]
        print(' {:,} irns found in {}'.format(len(sirns), sync_from))
        dirns = [doc['_id'] for doc in dst.find(query, [])]
        print(' {:,} irns found in {}'.format(len(dirns), sync_to))
        irns = set(dirns) -set(sirns)
        queue = []
        for irn in irns:
            queue.append(DeleteOne({'_id': irn}))
            if len(queue) == 1000:
                dst.bulk_write(queue)
                deleted += len(queue)
                queue = []
        if len(queue):
            dst.bulk_write(queue)
            deleted += len(queue)
            queue = []
        print(' {:,} records deleted ({:,} checked)'.format(deleted,
                                                            len(dirns)))


class MongoDoc(dict):
    """Dict sublass with methods supporting Mongo-style paths"""

    def __init__(self, *args, **kwargs):
        super(MongoDoc, self).__init__(*args, **kwargs)
        self._convert_children(self)


    def __call__(self, path):
        """Shorthand to retrieve data from a Mongo path"""
        return self.getpath(path)


    def getpath(self, path, default=None):
        """Retrieves value from Mongo-style path"""
        keys = path.split('.')
        doc = self
        for key in keys:
            doc = doc.get(key, {})
        return doc if doc != {} else default


    def pprint(self):
        """Pretty prints the dict"""
        cprint(self)


    def _convert_children(self, obj):
        """Converts nested dictionaries to MongoDoc"""
        if isinstance(obj, dict):
            if not isinstance(obj, MongoDoc):
                MongoDoc(obj)
            for key in list(obj.keys()):
                self._convert_children(obj[key])
        elif isinstance(obj, list):
            for i in range(len(obj)):
                self._convert_children(obj[i])


class XMungo(MongoBot):
    """Contains methods to interact with Mongo data using XMu tools"""

    def __init__(self, *args, **kwargs):
        self._skip = kwargs.pop('skip', 0)
        container = kwargs.pop('container', XMuRecord)
        if container.geotree is None:
            raise AttributeError('Set container.geotree = get_tree()')
        module = kwargs.pop('module')
        super(XMungo, self).__init__(*args, **kwargs)
        # Create a private xmudata attribute so XMungo can use write XML
        self._xmudata = XMu(None, module=module, container=container)
        self.from_json = False
        self.keep = []          # populated using set_keep() method


    def parse(self, doc):
        """Converts Mongo document to XMu dictionary"""
        return mongo2xmu(doc, self.container)


    def container(self, *args):
        """Wraps dict in custom container with attributes needed for export"""
        return self._xmudata.container(*args)


    def iterate(self, element):
        """Placeholder for iteration method"""
        raise Exception('No iterate method is defined for this subclass')


    def finalize(self):
        """Placeholder for finalize method run at end of iteration"""
        pass


    def _fast_iter(self, query=None, func=None, report=0, skip=0, limit=0,
                   callback=None, **kwargs):
        if func is None:
            func = self.iterate
        if report:
            starttime = datetime.now()
        # Forumulate and run query
        _query = {'catdp': 'ms'}
        if query is None:
            query = {}
        _query.update(query)
        if skip:
            self._skip = skip
        if self._skip:
            print('Skipping first {:,} records...'.format(self._skip))
            cursor = self.collection.find(_query, skip=self._skip)
        else:
            cursor = self.collection.find(_query)
        cursor.batch_size(500)
        print('{:,} matching records found!'.format(cursor.count()))
        # Process documents using func
        n_success = 0
        for doc in cursor:
            self._skip += 1
            result = func(doc, **kwargs)
            if result is False:
                break
            elif result is not True:
                n_success += 1
            if report and not self._skip % report:
                now = datetime.now()
                elapsed = now - starttime
                starttime = now
                print(('{:,} records processed! ({:,}'
                       ' successful, t={}s)').format(self._skip, n_success,
                                                     elapsed))
            if limit and not self._skip % limit:
                break
        print('{:,} records processed! ({:,} successful)'.format(self._skip,
                                                                 n_success))
        if callback is not None:
            callback()
        self.finalize()
        return True


    def fast_iter(self, query=None, func=None, report=0, skip=0, limit=0,
                  callback=None, **kwargs):
        """Use function to iterate through a MongoDB record set

        This method reproduces most (but not all) of the functionality of
        the XMu.fast_iter() method.

        Args:
            func (function): name of iteration function
            report (int): number of records at which to report
                progress. If 0, no progress report is made.
            limit (int): number of record at which to stop
            callback (function): name of function to run upon completion

        Returns:
            Boolean indicating whether the entire record set was processed
            successfully.
        """
        # Wrapper in a while loop to catch cursor errors
        self._skip = kwargs.pop('skip', 0)
        num_retries = 0
        skipped = 0  # used to track consecutive failures
        while True:
            try:
                return self._fast_iter(query, func, report, skip, limit,
                                       callback, **kwargs)
            except pymongo.errors.CursorNotFound:
                if num_retries > 8:
                    raise
                # Try to reconnect after backoff
                backoff = 30 * 2 ** num_retries
                print(('Cursor not found! Retrying'
                       ' in {} seconds...').format(backoff))
                time.sleep(backoff)
                num_retries += 1
                # Reset counter if additional records have been processed
                if skipped != self._skip:
                    num_retries = 0


    def save(self):
        """Save attributes listed in the self.keep as json"""
        print('Saving data to {}...'.format(self.jsonpath))
        data = {key: getattr(self, key) for key in self.keep}
        json.dump(data, open(self.jsonpath, 'wb'))


    def load(self):
        """Load data from json file created by self.save"""
        print('Reading data from {}...'.format(self.jsonpath))
        data = json.load(open(self.jsonpath, 'rb'))
        for attr, val in data.items():
            setattr(self, attr, val)
        self.from_json = True


    def set_keep(self, fields):
        """Sets the attributes to load/save when using JSON functions"""
        self.keep = fields


    def set_skip(self, skip):
        """Sets the attributes to load/save when using JSON functions"""
        self._skip = skip


def mongo2xmu(doc, container):
    """Maps Mongo document to EMu XML format

    Args:
        doc (dict): sample data from mongodb

    Returns:
        Sample data as container
    """
    doc = MongoDoc(doc)
    cat = container({
        'irn': doc.getpath('_id'),
        'CatPrefix': doc.getpath('catnb.catpr'),
        'CatNumber': doc.getpath('catnb.catnm'),
        'CatSuffix': doc.getpath('catnb.catsf'),
        'CatDivision': doc.getpath('catdv'),
        'CatCatalog': doc.getpath('catct'),
        'CatCollectionName_tab': doc.getpath('catcn', []),
        'CatSpecimenCount': str(int(doc.getpath('darin'))),
        'MinName': doc.getpath('minnm'),
        'MinJeweleryType': doc.getpath('minjt'),
        'MetMeteoriteName': doc.getpath('metnm'),
        'MetMeteoriteType': doc.getpath('metmt'),
        'PetEruptionDate': doc.getpath('peted'),
        'PetLavaSource': doc.getpath('petls'),
        'MeaCurrentWeight': doc.getpath('meacw'),
        'MeaCurrentUnit': doc.getpath('meacu'),
        'AdmGUIDType_tab': ['EZID'],
        'BioEventSiteRef': container({
            'LocSiteNumberSource': doc.getpath('bions'),
            'LocSiteStationNumber': doc.getpath('biosn'),
            'LocCountry': doc.getpath('darct'),
            'LocProvinceStateTerritory': doc.getpath('darst'),
            'LocDistrictCountyShire': doc.getpath('darcy'),
            'LocTownship': doc.getpath('biotw'),
            'LocOcean': doc.getpath('biooc'),
            'LocSeaGulf': doc.getpath('biosg'),
            'LocIslandName': doc.getpath('daris'),
            'LocMineName': doc.getpath('biomn'),
            'LocMiningDistrict': doc.getpath('biomt'),
            'LocGeologicSetting': doc.getpath('biogs'),
            'LocPreciseLocation': doc.getpath('biopl'),
            'VolVolcanoName': doc.getpath('biovl'),
            'VolVolcanoNumber': doc.getpath('biovm'),
            'ColCollectionMethod': doc.getpath('biocm'),
            'ColParticipantRole_tab': doc.getpath('biorl', []),
            'ExpExpeditionName': doc.getpath('bioex'),
            'AquVesselName': doc.getpath('biovn'),
            'TerElevationFromMet': doc.getpath('darm1'),
            'LatGeoreferencingNotes0': doc.getpath('latgn', [])
        }),
        'LocPermanentLocationRef': container({
            'SummaryData': doc.getpath('locpl')
        })
    })
    if doc.getpath('biopr') and '(' in doc.getpath('biopr'):
        input(doc.getpath('biopr'))
    # Format EZID
    guid = doc['admuu']  # this HAS to be present, so use the basic lookup
    guid = '-'.join([guid[:8], guid[8:12], guid[12:16], guid[16:20], guid[20:]])
    cat['AdmGUIDValue_tab'] = [guid]
    # Map nested tables
    lat = doc.getpath('darlt')
    if lat:
        cat['BioEventSiteRef']['LatLatitudeDecimal_nesttab'] = [[lat]]
    lng = doc.getpath('darln')
    if lng:
        cat['BioEventSiteRef']['LatLongitudeDecimal_nesttab'] = [[lng]]
    # Map complex arrays
    for caton in doc.getpath('caton', []):
        catnt = caton.get('catnt', '')
        catnv = caton.get('catnv', '')
        cat.setdefault('CatOtherNumbersType_tab', []).append(catnt)
        cat.setdefault('CatOtherNumbersValue_tab', []).append(catnv)
    for agega in doc.getpath('agega', []):
        agaid = agega.get('agaid', '')
        #ageaa = agega.get('ageaa', '')
        ageae = agega.get('ageae', '')
        ageay = agega.get('ageay', '')
        ageas = agega.get('ageas', '')
        ageat = agega.get('ageat', '')
        cat.setdefault('AgeGeologicAgeAuthorityRef_tab', []).append(agaid)
        #cat.setdefault('AgeGeologicAgeAuthorityRef_tab.SummaryData', []).append(ageaa)
        cat.setdefault('AgeGeologicAgeEra_tab', []).append(ageae)
        cat.setdefault('AgeGeologicAgeSystem_tab', []).append(ageay)
        cat.setdefault('AgeGeologicAgeSeries_tab', []).append(ageas)
        cat.setdefault('AgeGeologicAgeStage_tab', []).append(ageat)
    for agest in doc.getpath('agest', []):
        asaid = agest.get('asaid', '')
        #agesa = agest.get('agesa', '')
        agesf = agest.get('agesf', '')
        agesg = agest.get('agesg', '')
        agesm = agest.get('agesm', '')
        cat.setdefault('AgeStratigraphyAuthorityRef_tab', []).append(asaid)
        #cat.setdefault('AgeStratigraphyAuthorityRef_tab.SummaryData', []).append(agesa)
        cat.setdefault('AgeStratigraphyFormation_tab', []).append(agesf)
        cat.setdefault('AgeStratigraphyGroup_tab', []).append(agesg)
        cat.setdefault('AgeStratigraphyMember_tab', []).append(agesm)
    for zoopp in doc.getpath('zoopp', []):
        zoopr = zoopp.get('zoopr', '')
        zoopc = zoopp.get('zoopc', '')
        cat.setdefault('ZooPreparation_tab', []).append(zoopr)
        cat.setdefault('ZooPreparationCount_tab', []).append(str(zoopc))
    for taxon in doc.getpath('ideil', []):
        cat.setdefault('IdeTaxonRef_tab', []).append(
            #container({'ClaSpecies': taxon.get('idetx')})
            #container({'ClaOtherValue_tab': [{
            #    'ClaOtherValue': taxon.get('idetx')
            #}]})
            container({'ClaScientificName': taxon.get('idetx')})
        )
    # Set collector(s)
    parties = doc.getpath('biopr', [])
    cat['BioEventSiteRef']['ColParticipantRef_tab'] = [
        container({'SummaryData': party}) for party in parties
    ]
    # Map datestamp
    modtime = doc.getpath('admdm')
    cat['AdmDateModified'] = modtime.strftime('%Y-%m-%d')
    cat['AdmTimeModified'] = modtime.strftime('%H:%M:%S')
    #cat.pprint()
    cat.expand()
    #cat.pprint(True)
    return cat
