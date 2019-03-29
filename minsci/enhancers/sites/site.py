from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import logging
logger = logging.getLogger(__name__)

import csv
import json
import os
import pprint as pp
import re
from collections import namedtuple

from titlecase import titlecase
from yaml import load

from .bot import SiteBot, distance_on_unit_sphere
from .sitelist import SiteList
from ...standardizer import LocStandardizer



AdminDiv = namedtuple('AdminDiv', ['name', 'code', 'level'])


def _read_config(dirpath):
    config = load(open(os.path.join(dirpath, 'files', 'config.yaml'), 'r'))
    codes = {}
    classes = {}
    with open(os.path.join(dirpath, 'files', 'codes.csv'), 'r', encoding='utf-8-sig') as f:
        rows = csv.reader(f, dialect='excel')
        keys = next(rows)
        for row in rows:
            rowdict = {k: v for k, v in zip(keys, row)}
            try:
                rowdict['SizeIndex'] = int(rowdict['SizeIndex'][:-3])
            except ValueError:
                pass
            code = rowdict['FeatureCode']
            codes[code] = rowdict
            classes.setdefault(rowdict['FeatureClass'], []).append(code)
    # Map features classes to related feature codes
    for attr, classes_and_codes in config['codes'].items():
        codes_ = []
        for code in classes_and_codes:
            try:
                expanded = classes[code]
            except KeyError:
                codes_.append(code)
            else:
                for keyword in ['CONT', 'OCN']:
                    try:
                        expanded.remove(keyword)
                    except ValueError:
                        pass
                codes_.extend(expanded)
        config['codes'][attr] = codes_
    return config, codes



class Site(dict):
    config, codes = _read_config(os.path.dirname(__file__))
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
        'site_names',
        'synonyms'
    ]
    _code_to_attr = config['code_to_attribute']
    _attr_to_code = config['attribute_to_codes']
    bot = None
    localbot = None


    def __init__(self, data=None):
        super(Site, self).__init__()
        self.orig = data
        if not data or not any(data):
            pass
        elif 'location_id' in data:
            for key, val in data.items():
                setattr(self, key, val)
        elif 'irn' in data:
            self.from_emu(data)
        elif isinstance(data, list) and 'countryCode' in data[0]:
            self.from_geonames(data[0])
        elif 'geonameId' in data:
            self.from_geonames(data)
        elif 'recordNumber' in data:
            self.from_dwc(data)
        else:
            raise ValueError('Unrecognized data format: {}'.format(data))
        self.strict = False
        self.std = LocStandardizer()
        self.name = None


    def __getattr__(self, attr):
        try:
            return super(Site, self).__getattr__(attr)
        except AttributeError:
            return u''


    def __str__(self):
        return pp.pformat({a: getattr(self, a) for a in self._attributes})


    def _repr__(self):
        return pp.pformat({a: getattr(self, a) for a in self._attributes})


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
        self.county = rec.get('adminName2')
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
        #if self.bbox and not (self.latitude or self.longitude):
        #    self.latitude = (self.bbox['east'] + self.bbox['west']) / 2
        #    self.longitude = (self.bbox['north'] + self.bbox['south']) / 2
        #elif self.latitude and self.longitude and not self.bbox:
        #    self.bbox = {
        #        'north': float(self.latitude) + 0.1,
        #        'east': float(self.longitude) + 0.1,
        #        'west': float(self.longitude) - 0.1,
        #        'south': float(self.latitude) - 0.1
        #    }
        # Map site
        self.site_kind = rec.get('fcode')
        self.site_num = rec.get('geonameId')
        self.site_source = u'GeoNames'
        # Map synonyms
        self.synonyms = [s['name'] for s in rec.get('alternateNames', [])]
        # Set name to the first English synonym
        names = [s['name'] for s in rec.get('alternateNames', []) if s.get('lang') == 'en']
        if not names:
            names = [rec.get('name')]
        self.site_names = names


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
        self.water_body = rec('LocBaySound')
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
        self.sea = rec.get('LocSeaGulf')
        self.ocean = rec.get('LocOcean')
        # Map features
        self.features = []
        for key in ['LocGeomorphologicalLocation', 'LocGeologicSetting']:
            vals = [s.strip() for s in re.split(r'[;,]', rec(key)) if s.strip()]
            self.features.extend(vals)
        # Map site info
        self.site_kind = rec('LocRecordClassification')
        self.site_num = rec('LocSiteStationNumber')
        self.site_source = rec('LocSiteNumberSource')
        self.site_names = rec('LocSiteName_tab')
        self.synonyms = []
        # Check if locality string is just a place name
        self._parse_emu_locality()
        # Move directional info to precise locality
        for attr in self._attributes:
            if attr == 'locality':
                continue
            vals = getattr(self, attr)
            if not isinstance(vals, list):
                vals = [vals]
            updated = []
            for val in vals:
                for word in ['m', 'meters', 'km', 'mi', 'mile', 'miles']:
                    if re.search(r'\b{}\b'.format(word), val, flags=re.I):
                        self.locality += '; ' + val
                        logger.info('Moved {} from {} to {}'.format(val, attr, 'locality'))
                        break
                else:
                    updated.append(val)
            if attr in ['features', 'site_names', 'synonyms']:
                setattr(self, attr, updated)
            else:
                setattr(self, attr, '; '.join(updated))
        print(self)


    def from_dwc(self, rec):
        raise AttributeError('from_dwc method not implemented')


    def stripwords(self, val, field):
        val = val.strip('. ')
        words = self.config['stripwords'].get(field, [])
        words.sort(key=len, reverse=True)
        for word in self.config['stripwords'].get(field, []):
            val = re.sub(r'\b{}\b'.format(word), '', val, flags=re.I).strip()
        return val


    def _parse_emu_locality(self):
        """Look for features in locality string from EMu"""
        pattern = r'^[A-Z][a-z]+([ -]([A-Z][a-z]+|of|de|la|le|l\'|d\'))*$'
        val = titlecase(self.locality)
        vals = [s.strip() for s in re.split(r'[;,]', val) if s.strip()]
        for val in vals:
            if val.endswith(' (Near)'):
                val = val[:-7]
            if not re.search(pattern, val):
                break
        else:
            self.features.extend(vals)
            self.locality = ''
        return self


    def get_admin_codes(self):
        """Maps names of admin divisions to codes used by GeoNames"""
        self.country_code = self.bot._map_country(self.country)
        admin = {'country': self.country_code}
        val = self.state_province
        if val:
            self.admin_div_1 = self.get_admin_code(val, 'ADM1')
            self.admin_code_1 = self.admin_div_1.code
            admin['adminCode1'] = self.admin_code_1
        val = self.county.replace(' Co.', '')
        if val:
            self.admin_div_2 = self.get_admin_code(val, 'ADM2')
            self.admin_code_2 = self.admin_div_2.code
            admin['adminCode2'] = self.admin_code_2
        return admin


    def most_specific_feature(self):
        for field in self.config['ordered']:
            name = getattr(self, field)
            if isinstance(name, list) and len(name) == 1:
                return name[0], field
            elif name:
                return name, field
        return None, None


    def find_synonyms(self):
        site = self.__class__(self.bot.get_by_id(self.site_num))
        self.synonyms = sorted(list(set(self.synonyms + site.synonyms)))


    def summarize(self, mask='{name}{higher_loc} ({url})'):
        """Summarizes site info for a GeoNames record as a string"""
        name = self.site_names[0]
        county = self.county
        if self.country == 'United States' and not county.endswith('Co.'):
            county += ' Co.'
        loc = [s for s in [county, self.state_province, self.country] if s]
        higher_loc = ', '.join(loc)
        if higher_loc == self.site_names[0]:
            higher_loc = ''
        else:
            higher_loc = ', ' + higher_loc
        url = 'http://geonames.org/{}'.format(self.site_num)
        info = {
            'name': name,
            'higher_loc': higher_loc,
            'url': url
        }
        return mask.format(**info)


    @staticmethod
    def oxford_comma(vals, delim=', '):
        if len(vals) <= 2:
            return ' and '.join(vals)
        return delim.join(vals[:-1]) + ', and ' + vals[-1]


    def compare(self, other):
        """Checks if two sites are equivalent"""
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


    def polygon(self, dec_places=4):
        """Converts bounding coordinates to a polygon"""
        polygon = [
            (self.bbox['west'], self.bbox['north']),
            (self.bbox['east'], self.bbox['north']),
            (self.bbox['east'], self.bbox['south']),
            (self.bbox['west'], self.bbox['south']),
            (self.bbox['west'], self.bbox['north']),
        ]
        if dec_places is not None:
            mask = '{{0:.{}f}}'.format(dec_places)
            for i, coords in enumerate(polygon):
                polygon[i] = [mask.format(c) for c in coords]
        return polygon


    def verify(self):
        """Verifies higher political geography in a GeoNames match"""
        eqs = []
        if self.site_num:
            gnsite = self.bot.get_by_id(self.site_num)
            for attr in ['country', 'state_province', 'country']:
                attr1 = getattr(site, attr)
                attr2 = getattr(gnsite, attr)
                eqs.append('==' if attr1 == attr2 else '!=')
                print('{}: {} {} {}').format(attr, attr1, eqs[-1], attr2)
        return '!=' not in eqs



    def synonymize(self, attr):
        for attr in ['country', 'state_province', 'country']:
            if attr == attr:
                break


    def get_admin_name(self, *args, **kwargs):
        kwargs['search_name'] = True
        return self.get_admin_div(*args, **kwargs)


    def get_admin_code(self, *args, **kwargs):
        try:
            assert self.admin_codes
        except AssertionError:
            self.read_admin_codes()
        kwargs['search_name'] = False
        return self.get_admin_div(*args, **kwargs)


    def get_admin_div(self, term, level, search_name=None, suffixes='HD'):
        term_ = self.std(term)
        try:
            country_code = self.bot._map_country(self.country)[0]
        except IndexError as e:
            logger.error('Unrecognized country', exc_info=True)
            raise
        try:
            val = self.admin_codes[country_code][level][term_]
        except KeyError:
            for level in [level + s for s in suffixes]:
                try:
                    val = self.admin_codes[country_code][level][term_]
                except KeyError:
                    pass
                else:
                    break
            else:
                level = level.rstrip(suffixes)
                raise ValueError('Unknown {}: {}, {}'.format(level, term, self.country))
        # If searching a name, look up the official name as well
        if len(val) < len(term) or search_name:
            try:
                name = self.admin_codes[country_code][level][self.std(val)]
            except KeyError:
                raise KeyError('Unknown {}: {}, {}'.format(level, val, self.country))
            return AdminDiv(name, val, level)
        return AdminDiv(val, term, level)


    def read_admin_codes(self, standardize=False):
        """Reads and if necessary formats the list of admin codes"""
        print('Loading admin codes...')
        fp = os.path.join(os.path.dirname(__file__), 'files', 'admin_codes_std.json')
        # Standardize keys
        if standardize:
            orig = os.path.join(os.path.dirname(__file__), 'files', 'admin_codes.json')
            admin_codes = json.load(open(orig, 'r', encoding='utf-8'))
            print('Standardizing keys...')
            for country, levels in admin_codes.items():
                print('Processing {}...'.format(country))
                for level, names in levels.items():
                    for key, code in list(names.items()):
                        if self.std(key) != key:
                            names[self.std(key)] = code
                            del names[key]
            json.dump(admin_codes,
                      open(fp, 'w', encoding='utf-8'),
                      indent=2,
                      sort_keys=True)
        else:
            admin_codes = json.load(open(fp, 'r', encoding='utf-8'))
        self.__class__.admin_codes = admin_codes
        print('Loaded codes!')
        return admin_codes




SiteList.itemclass = Site
