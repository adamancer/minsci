from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from past.utils import old_div
import os
import pprint as pp

from yaml import load

from .bot import SiteBot
from .sitelist import SiteList




class Site(dict):
    config = load(open(os.path.join(os.path.dirname(__file__), 'files', 'config.yaml'), 'rb'))
    _attributes = [
        'location_id',
        'continent',
        'country',
        'state_province',
        'county',
        'municipality',
        'island',
        'island_group',
        'water_body',
        'features',
        'mine',
        'volcano',
        'locality',
        'latitude',
        'longitude',
        'site_kind',
        'site_source',
        'site_num',
        'site_names'
    ]
    _code_to_attr = config['code_to_attribute']
    _attr_to_code = config['attribute_to_codes']
    bot = SiteBot('mansura')


    def __init__(self, data):
        super(Site, self).__init__()
        self.orig = data
        if not data or not any(data):
            pass
        elif 'irn' in data:
            self.from_emu(data)
        elif isinstance(data, list) and 'countryCode' in data[0]:
            self.from_geonames(data[0])
        elif 'countryCode' in data:
            self.from_geonames(data)
        elif 'recordNumber' in data:
            self.from_dwc(data)


    def __getattr__(self, attr):
        try:
            return super(Site, self).__getattr__(attr)
        except AttributeError:
            return u''


    def __str__(self):
        return pp.pformat({a: getattr(self, a) for a in self._attributes})


    def _repr__(self):
        return {a: getattr(self, a) for a in self._attributes}


    def __bool__(self):
        for attr in self._attributes:
            if getattr(self, attr):
                return True
        return False


    def from_geonames(self, rec):
        self.location_id = rec.get('geonameId')
        self.continent = rec.get('continentCode')
        self.country = rec.get('countryName')
        self.state_province = rec.get('adminName1')
        # Map specific site
        self.features = []
        try:
            setattr(self, self._code_to_attr[rec['fcode']], rec.get('name'))
        except KeyError:
            self.features.append(rec.get('name'))
        # Map coordinates from the bounding box
        self.bbox = rec.get('bbox')
        self.latitude = rec.get('lat')
        self.longitude = rec.get('lng')
        if self.bbox and not (self.latitude or self.longitude):
            self.latitude = old_div((self.bbox['east'] + self.bbox['west']), 2.)
            self.longitude = old_div((self.bbox['north'] + self.bbox['south']), 2.)
        elif self.latitude and self.longitude and not self.bbox:
            self.bbox = {
                'north': float(self.latitude) + 0.1,
                'east': float(self.longitude) + 0.1,
                'west': float(self.longitude) - 0.1,
                'south': float(self.latitude) - 0.1
            }
        # Map site
        self.site_kind = rec.get('fcode')
        self.site_num = rec.get('geonameId')
        self.site_source = u'GeoNames'
        self.site_names = rec.get('name')
        # Map synonyms
        self.synonyms = [s['name'] for s in rec.get('alternateNames', [])]


    def from_emu(self, rec):
        self.location_id = rec('irn')
        # Map to DwC field names
        self.continent = rec('LocContinent')
        self.country = rec('LocCountry')
        self.state_province = rec('LocProvinceStateTerritory')
        self.county = rec('LocDistrictCountyShire')
        self.municipality = rec('LocTownship')
        self.island = rec('LocIslandName')
        self.island_group = rec('LocIslandGrouping')
        self.water_body = rec('LocSeaGulf') or rec('LocBaySound')
        self.locality = rec('LocPreciseLocation')
        latitude = rec('LatLatitudeDecimal_nesttab')
        if any(latitude):
            self.latitude = latitude[0][0]
        longitude = rec('LatLongitudeDecimal_nesttab')
        if any(longitude):
            self.longitude = longitude[0][0]
        # Map to additional fields
        self.mine = rec('LocMineName')
        self.volcano = rec('VolVolcanoName')
        # Map features
        self.features = []
        for key in ['LocGeomorphologicalLocation']:
            val = rec(key)
            if val:
                self.features.append(val)
        # Map site info
        self.site_kind = rec('LocRecordClassification')
        self.site_num = rec('LocSiteStationNumber')
        self.site_source = rec('LocSiteNumberSource')
        self.site_names = rec('LocSiteName_tab')


    def from_dwc(self, rec):
        self.location_id = rec.get('irn')
        # Map to DwC field names
        self.continent = rec.get('LocContinent')
        self.country = rec.get('country')
        self.state_province = rec.get('stateProvince')
        self.county = rec.get('county')
        self.municipality = rec.get('municipality')
        self.island = rec.get('island')
        self.island_group = rec.get('LocIslandGrouping')
        self.water_body = rec.get('LocSeaGulf') or rec.get('LocBaySound')
        self.features = [rec.get('LocGeomorphologicalLocation')]
        self.locality = rec.get('locality')
        self.latitude = rec.get('LatLatitudeDecimal_nesttab')
        self.longitude = rec.get('LatLongitudeDecimal_nesttab')
        # Map to additional fields
        self.mine = rec.get('LocMineName')
        self.volcano = rec.get('VolVolcanoName')
        # Map site info
        self.site_kind = rec.get('LocRecordClassification')
        self.site_num = rec.get('LocSiteStationNumber')
        self.site_source = rec.get('LocSiteNumberSource')
        self.site_names = rec.get('LocSiteName_tab')



    def match(self, field=None, **kwargs):
        most_specific = True
        rows = self._attr_to_code
        if field is not None:
            rows = [row for row in rows if row['field'] == field]
            if not rows:
                raise ValueError('Unknown field: {}'.format(field))
        for row in rows:
            val = getattr(self, row['field'])
            if val:
                matches = SiteList(self.bot.search(val, features=row['codes'], **kwargs))
                #matches.best_match(val, self)
                if matches:
                    return matches[0]
                else:
                    most_specific = False


    def match_all(self, **kwargs):
        matches = {}
        for row in self._attr_to_code[::-1]:
            match = self.match(row['field'], **kwargs)
            if match:
                import re
                key = re.sub('_([a-z])', lambda m: m.group(1).upper(), row['field'])
                print(key)
                matches[key] = match
                if row['field'] == 'country':
                    kwargs['countryCode'] = match.orig['countryCode']
                elif row['field'] == 'stateProvince':
                    kwargs['adminCode1'] = match.orig['adminCode1']
        return matches


    def compare(self, other):
        n = max([len(attr) for attr in self._attributes])
        for attr in self._attributes:
            val1 = getattr(self, attr)
            val2 = getattr(other, attr)
            if val1 or val2 and val1 != val2:
                print(u'{}: {} <=> {}'.format(attr.ljust(n), val1, val2))


    def country_subdivision(self):
        return self.__class__(self.bot.country_subdivision(self.latitude,
                                                           self.longitude,
                                                           2))


    def get_by_id(self):
        if self.site_source == 'GeoNames' and self.site_num:
            return self.__class__(self.bot.get_by_id(self.site_num))


    def find_nearby(self):
        return self.__class__(self.bot.find_nearby(self.latitude,
                                                   self.longitude,
                                                   2))


    def key(self, val):
        val = unidecode(val)




SiteList.itemclass = Site
