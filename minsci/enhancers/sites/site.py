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

from shapely.geometry import Polygon, Point
from titlecase import titlecase

from .helpers import (
    AdminParser,
    DirectionParser,
    PLSSParser,
    get_circle,
    get_distance,
    get_point,
    get_point_from_box,
    get_size,
    is_directions,
    read_config)
from .sitelist import SiteList
from ...standardizer import LocStandardizer




class Site(dict):
    config, codes = read_config()
    _attributes = {
        'location_id': '',
        'continent': '',
        'country': '',
        'state_province': '',
        'county': '',
        'municipality': '',
        'island': '',
        'island_group': '',
        'water_body': '',
        'features': [],
        'mine': '',
        'mining_district': '',
        'volcano': '',
        'sea': '',
        'ocean': '',
        'maps': [],
        'locality': '',
        'latitude': '',
        'longitude': '',
        'site_kind': '',
        'site_source': '',
        'site_num': '',
        'site_names': [],
        'synonyms': []
    }
    _code_to_attr = config['code_to_attribute']
    _attr_to_code = config['attribute_to_codes']
    adm_parse = AdminParser()
    dir_parse = DirectionParser()
    gl_bot = None
    gn_bot = None
    localbot = None


    def __init__(self, data=None):
        super(Site, self).__init__()
        self.verbatim = data
        self.strict = False
        self.std = LocStandardizer()
        self.name = None
        self._polygon = None
        self.directions_from = []
        # Define attributes for admin divisions
        self.country_code = None
        self.admin_div_1 = None
        self.admin_code_1 = None
        self.admin_div_2 = None
        self.admin_code_2 = None
        # Parse record
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
            self.from_site(data)


    def __str__(self):
        return self.summarize()


    def __repr__(self):
        return pp.pformat({a: getattr(self, a) for a in self._attributes})


    def __bool__(self):
        for attr in self._attributes:
            if getattr(self, attr):
                return True
        return False


    def html(self):
        html = []
        for attr in self._attributes:
            val = getattr(self, attr)
            if val:
                if isinstance(val, list):
                    val = '; '.join(val)
                key = attr.title().replace('_', ' ').replace('Id', 'ID')
                html.append('<strong>{}:</strong> {}'.format(key, val))
        return '<br />'.join(html)


    def fill(self):
        """Fills out required attributes in a site record"""
        for attr, val in self._attributes.items():
            try:
                getattr(self, attr)
            except AttributeError:
                setattr(self, attr, val)
        return self


    def clone(self, data, copy_missing_fields=False):
        """Clones the current site"""
        site = self.__class__(data)
        site.gl_bot = self.gl_bot
        site.gn_bot = self.gn_bot
        # Copy missing data from source record
        if copy_missing_fields:
            # Copy verbatim data if no other data provided
            if not data:
                site.verbatim = self.verbatim
            for attr in self._attributes:
                try:
                    this = getattr(site, attr)
                except AttributeError:
                    setattr(site, attr, getattr(self, attr))
                else:
                    if not this:
                        setattr(site, attr, getattr(self, attr))
        site.fill()
        # If basic info is populated and the cloned site includes admin
        # codes, regenerate those here
        if data or copy_missing_fields:
            try:
                self.admin_div_1
            except AttributeError:
                pass
            else:
                site.get_admin_codes()
        return site


    def simplify(self, whitelist=None, blacklist=None):
        """Simplifies a site for display"""
        if whitelist is not None:
            data = {k: getattr(self, k) for k in whitelist}
        else:
            data = {k: getattr(self, k) for k in self._attributes}
        if blacklist is not None:
            data = {k: v for k, v in data.items() if k not in blacklist}
        return self.__class__(data)



    def from_geonames(self, rec):
        """Constructs a site from a GeoNames record"""
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
        # Map site
        self.site_kind = rec.get('fcode')
        self.site_num = rec.get('geonameId')
        self.site_source = u'GeoNames'
        # Map synonyms
        self.synonyms = [s['name'] for s in rec.get('alternateNames', [])]
        # Set name to the first English synonym
        names = [s['name'] for s in rec.get('alternateNames', [])
                 if s.get('lang') == 'en']
        if not names:
            names = [rec.get('name')]
        self.site_names = names
        # Manually set attributes not populated from this source
        self.classification = 'site'
        self.municipality = ''
        self.water_body = ''
        self.island = ''
        self.island_group = ''
        self.mine = ''
        self.mining_district = ''
        self.volcano = ''
        self.sea = ''
        self.ocean = ''
        self.maps = []
        self.locality = ''
        # Identify ocean or search
        if self.site_kind in self.config['codes']['undersea']:
            result = self.gn_bot.ocean(self.latitude, self.longitude, 2)
            try:
                ocean_sea = result['ocean']['name']
            except KeyError:
                pass
            else:
                if ocean_sea.endswith(' Ocean'):
                    self.ocean = ocean_sea
                else:
                    self.sea = ocean_sea
        # Validate that all required attributes are present
        self.classification = self.classify()
        self._check_attributes()


    def from_emu(self, rec):
        """Constructs a site from an EMu Collections Event record"""
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
        # Latitude and longitude use the centroid
        self.latitude = ''
        self.longitude = ''
        self.bbox = None
        cols = [
            'LatLatitudeDecimal_nesttab',
            'LatLongitudeDecimal_nesttab',
            'LatCentroidLatitudeDec_tab',
            'LatCentroidLongitudeDec_tab',
            'LatPreferred_tab'
        ]
        grid = rec.grid(cols)
        row = None
        for row in grid.rows():
            if row['LatPreferred_tab'] == 'Yes':
                break
        if row is not None:
            try:
                self.latitude = float(row['LatCentroidLatitudeDec_tab'])
                self.longitude = float(row['LatCentroidLongitudeDec_tab'])
            except ValueError:
                if (len(row['LatLatitudeDecimal_nesttab']) == 1
                    and len(row['LatLongitudeDecimal_nesttab']) == 1):
                        self.latitude = float(row['LatLatitudeDecimal_nesttab'][0])
                        self.longitude = float(row['LatLongitudeDecimal_nesttab'][0])
            if len(row['LatLatitudeDecimal_nesttab']) == 5:
                try:
                    lats = [float(c) for c in row['LatLatitudeDecimal_nesttab']]
                    lngs = [float(c) for c in row['LatLongitudeDecimal_nesttab']]
                    self.bbox = {
                        'north': max(lats),
                        'south': min(lats),
                        'east': max(lngs),
                        'west': min(lngs)
                    }
                except ValueError:
                    pass
        # Map section-township-range to locality
        labels = [s.lower() for s in rec('MapOtherKind_tab')]
        if 'section' in labels and 'township range' in labels:
            # Check if locality already has a PLSS string
            try:
                parsed = PLSSParser().parse(self.locality)
            except ValueError:
                parsed = None
            if parsed is None:
                labels = [lbl.split(' ')[0] for lbl in labels]
                rows = zip(labels, rec('MapOtherCoordA_tab'))
                plss = {lbl: val for lbl, val in rows}
                rows = zip(labels, rec('MapOtherCoordB_tab'))
                plss['range'] = {lbl: val for lbl, val in rows}['township']
                mask = '{quarter} Sec. {section} {township} {range}'
                div = mask.format(**plss)
                self.locality = '{}; {}'.format(self.locality.rstrip('; '), div)
        # Map to additional fields
        self.mine = rec('LocMineName')
        self.mining_district = rec('LocMiningDistrict')
        self.volcano = rec('VolVolcanoName')
        self.sea = rec.get('LocSeaGulf')
        self.ocean = rec.get('LocOcean')
        self.maps = [rec(k) for k in ['LocQUAD', 'MapName'] if rec(k)]
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
            vals = getattr(self, attr)
            if vals is None:
                vals = ''
            if (attr in ['latitude', 'locality', 'longitude']
                or isinstance(vals, (float, int))):
                    continue
            if not isinstance(vals, list):
                vals = [vals]
            updated = []
            for val in vals:
                for word in ['ft', 'm', 'meters', 'km', 'mi', 'mile', 'miles']:
                    if re.search(r'\b{}\b'.format(word), val, flags=re.I):
                        self.locality += '; ' + val
                        logger.info('Moved {} from {} to {}'.format(val, attr, 'locality'))
                        break
                else:
                    updated.append(val)
            if attr in ['maps', 'features', 'site_names', 'synonyms']:
                setattr(self, attr, [s for s in updated if s])
            else:
                setattr(self, attr, '; '.join(updated))
        # Check if site is an event
        self.classification = self._classify_emu_record(rec)
        # Validate that all required attributes are present
        self._check_attributes()


    def from_geolocate(self, rec, params):
        """Constructs a site from a GEOLocate result"""
        self.site_kind = rec.get('type', '')
        coords = rec.get('geometry', {}).get('coordinates', ['', ''])
        self.latitude, self.longitude = coords
        self.locality = params.get('locality', '')
        self.country = params.get('country', '')
        self.state_province = params.get('state', '')
        self.county =  params.get('county', '')
        # Manually set attributes not populated from this source
        self.classification = 'specific'
        self.site_source = 'GEOLocate'
        self.site_names = []
        self.municipality = ''
        self.island = ''
        self.island_group = ''
        self.water_body = ''
        self.features = []
        self.mine = ''
        self.volcano = ''
        self.sea = ''
        self.ocean = ''
        self.maps = []
        # Validate that all required attributes are present
        self._check_attributes()


    def from_dwc(self, rec):
        """Constructs a site from a Simple Darwin Core record"""
        for key, val in rec.items():
            key = re.sub('([A-Z]+)', r'_\1', key).lower() \
                    .replace('decimal', '') \
                    .strip('_')
            if key not in self._attributes:
                pass
            setattr(self, key, val)
        self.location_id = rec['occurrenceID'].split('/')[-1]
        try:
            self.latitude = float(self.latitude)
            self.longitude = float(self.longitude)
        except (TypeError, ValueError):
            pass
        self.bbox = []
        self.fill()
        self.classification = self.classify()
        self._check_attributes()


    def from_site(self, rec):
        """Constructs a simple site record from data already so formatted"""
        for key, val in rec.items():
            if key not in self._attributes:
                raise AttributeError('Unknown attribute: {}'.format(key))
            setattr(self, key, val)
        self.bbox = []
        self.fill()
        self.classification = self.classify()
        self._check_attributes()


    def get_admin_codes(self):
        """Maps names of admin divisions to codes used by GeoNames

        Antarctica (country_code=AQ) is excluded from admin mapping because
        its primary divisions are not coded as states in GeoNames.
        """
        # Reset admin codes
        self.country_code = ''
        self.admin_div_1 = ''
        self.admin_code_1 = ''
        self.admin_div_2 = ''
        self.admin_code_2 = ''
        # Exclude ocean records from admin code checks
        if (self.ocean or self.sea) and not self.country:
            return {}
        if self.country is None:
            raise ValueError('Unknown country/ocean/sea')
        map_archaic = self.adm_parse.map_archaic
        mapped = map_archaic(self.country,
                             keys=['countries'],
                             callback=self.adm_parse.get_country_code)
        name, code = mapped
        if not isinstance(name, dict):
            self.country, self.country_code = name, code
        else:
            self.update_from_dict(name)
            return self.get_admin_codes()
        admin = {'country': self.country_code}
        # Map archaic state names
        val = self.state_province
        if val and self.country_code != 'AQ':
            mapped = map_archaic(val,
                                 keys=['states', self.country],
                                 callback=self.adm_parse.get_admin_code,
                                 level='ADM1',
                                 country=self.country)
            name, code = mapped
            if not isinstance(name, dict):
                self.state_province, self.admin_code_1 = name, code
                try:
                    self.admin_code_1 = self.admin_code_1.code
                except AttributeError:
                    self.admin_code_1 = [c.code for c in self.admin_code_1]
            else:
                name.setdefault('state_province', '')
                self.update_from_dict(name)
                return self.get_admin_codes()
            admin['adminCode1'] = self.admin_code_1
        # Check county name
        val = self.county.replace(' Co.', '')
        if val and self.country_code != 'AQ':
            mapped = map_archaic(val,
                                 keys=['counties',
                                       self.country,
                                       self.state_province],
                                 callback=self.adm_parse.get_admin_code,
                                 level='ADM2',
                                 country=self.country)
            name, code = mapped
            if not isinstance(name, dict):
                self.county, self.admin_code_2 = name, code
            else:
                name.setdefault('county', '')
                self.update_from_dict(name)
                return self.get_admin_codes()
            admin['adminCode2'] = self.admin_code_2
        return admin


    def update_from_dict(self, dct):
        """Updates site from a dictionary"""
        for key, val in dct.items():
            if key.endswith('+') or key in ['features', 'water_body']:
                orig = getattr(self, key, val)
                if isinstance(orig, list):
                    setattr(self, key, orig + [val])
                else:
                    setattr(self, key, orig.rstrip('; ') + '; ' + val)
            elif key in ['features', 'site_names']:
                setattr(self, key, val)
            else:
                setattr(self, key, val)


    def get_radius(self, from_bounding_box=False):
        """Calculates a radius for this site"""
        # Check if site a feature code that can be used to estiamte the radius.
        # Force a check of the bounding box if not.
        try:
            radius = self.codes[self.site_kind]['SizeIndex']
        except KeyError:
            from_bounding_box = True
            radius = 25
        # Get the center-to-corner distance of the bounding box
        if from_bounding_box:
            try:
                diameter = get_distance(self.bbox['north'], self.bbox['west'],
                                        self.bbox['south'], self.bbox['east'])
            except (AttributeError, KeyError, TypeError, ValueError):
                pass
            else:
                radius = diameter / 2
        return radius


    def most_specific_feature(self):
        """Determines the most specific feature named in this site"""
        for field in self.config['ordered']:
            name = getattr(self, field)
            if isinstance(name, list) and len(name) == 1:
                return name[0], field
            elif name:
                return name, field
        return None, None


    def get_size(self):
        return get_size(self.polygon())


    def polygon(self, dec_places=4, for_plot=False):
        """Converts bounding coordinates to a polygon"""
        if not self.bbox:
            return None
        polygon = [
            (self.bbox['north'], self.bbox['east']),
            (self.bbox['south'], self.bbox['east']),
            (self.bbox['south'], self.bbox['west']),
            (self.bbox['north'], self.bbox['west']),
            (self.bbox['north'], self.bbox['east'])
        ]
        # Reverse order for XY plotting (e.g., for Shapely)
        if for_plot:
            polygon = [(c[1], c[0]) for c in polygon]
        if dec_places is not None:
            mask = '{{0:.{}f}}'.format(dec_places)
            for i, coords in enumerate(polygon):
                polygon[i] = [mask.format(c) if isinstance(c, float) else c
                              for c in coords]
        return polygon


    def find_synonyms(self):
        """Finds synonyms for this site using GeoNames"""
        try:
            site = self.__class__(self.gn_bot.get_by_id(self.site_num))
        except AssertionError:
            self.synonyms = []
        else:
            self.synonyms = sorted(list(set(self.synonyms + site.synonyms)))


    def is_synonym_for(self, name):
        std = SiteList()._std_to_field
        keys = ['asciiName', 'name', 'toponymName']
        primary = [std(self.verbatim.get(''), None) for k in keys]
        synonyms = [std(s, None) for s in self.synonyms]
        stname = std(name, None)
        return stname not in '|'.join(primary) and stname in '|'.join(synonyms)


    def summarize(self, mask='{name}{higher_loc} ({url})', feature=''):
        """Summarizes site info for a GeoNames record as a string"""
        if self.site_kind == '_DIRS':
            name = self.locality
        else:
            name = self.site_names[0] if self.site_names else 'Unnamed'
        # Prepare higher locality info
        country = self.country
        state_province = self.state_province
        county = self.county
        if (county
            and self.country == 'United States'
            and not county.endswith('Co.')):
                county += ' Co.'
        # Limit higher locality based on the feature that was matched
        loc = [county, state_province, country]
        if feature == 'district/county' or re.match(r'^ADM[2345]', feature):
            loc = loc[1:]
            if self.country == 'United States' and not name.endswith('Co.'):
                name += ' Co.'
        elif feature == 'state/province' or feature.startswith('ADM1'):
            loc = loc[2:]
        elif feature == 'country' or feature.startswith('PCL'):
            loc = []
        higher_loc = ', '.join([s for s in loc if s])
        delim = ' in ' if '"{name}"' in mask else ', '
        if higher_loc == name:
            higher_loc = ''
        elif higher_loc:
            higher_loc = delim + higher_loc
        url = ''
        if self.site_num:
            gid = str(self.site_num).lstrip('d')
            url = 'http://geonames.org/{}'.format(gid)
        info = {
            'name': name,
            'higher_loc': higher_loc,
            'url': url,
            'site_kind': self.site_kind
        }
        return mask.format(**info).replace(',  (', ' (') \
                                  .replace('()', '') \
                                  .strip()


    def verify_coordinates(self, country_only=False):
        """Tests if coordinates fall into the bounding box"""
        if not self.country:
            return
        try:
            self.get_admin_codes()
        except (KeyError, ValueError):
            try:
                map_archaic = self.adm_parse.map_archaic
                mapped = map_archaic(self.country,
                                     keys=['countries'],
                                     callback=self.adm_parse.get_country_code)
                self.country, self.country_code = mapped
            except (KeyError, ValueError):
                logging.debug('Could not match country or admin info')
                return
        # Get admin codes for the current coordinates. This will raise an
        # error if the coordinates fall in the middle of the ocean.
        try:
            codes = self.country_subdivision()
        except ValueError as e:
            codes = {}
        # Test country (required)
        country = False
        if codes.get('countryCode') and self.country_code:
            country = codes.get('countryCode') == self.country_code
        if not country and self.country_code:
            try:
                site = self.gn_bot.get_country(self.country, self.country_code)
            except IndexError:
                pass
            else:
                site = Site(site)
                country = site.contains(lat=self.latitude, lng=self.longitude)
        # Test ADM1
        adm1 = None
        if codes.get('adminCode1') and self.admin_code_1:
            adm1 = codes.get('adminCode1') == self.admin_code_1
        if not adm1 and self.admin_code_1:
            try:
                site = self.gn_bot.get_state(self.state_province,
                                             self.country_code)
            except IndexError:
                pass
            else:
                site = Site(site)
                adm1 = site.contains(lat=self.latitude, lng=self.longitude)
            site = self.__class__()
        if country_only:
            return country or adm1
        return country and (adm1 is None or adm1)


    def fix_coordinates(self):
        verified = self.verify_coordinates()
        if not verified:
            # Only try to fix sites more than 1 degree from the prime meridian
            if abs(self.latitude) > 1 and abs(self.longitude) > 1:
                site = self.clone({}, copy_missing_fields=True)
                # Test -lat, lng
                site.latitude *= -1
                if site.verify_coordinates():
                    return site
                # Test -lat, -lng
                site.longitude *= -1
                if site.verify_coordinates():
                    return site
                # Test lat, -lng
                site.latitude *= -1
                if site.verify_coordinates():
                    return site
            raise ValueError('Could not fix coordinates')


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



    def country_subdivision(self):
        """Queries the GeoNames countrySubdivision webservice"""
        return self.gn_bot.country_subdivision(self.latitude, self.longitude, 2)


    def get_by_id(self):
        """Queries the GeoNames get webservice"""
        if self.site_source == 'GeoNames' and self.site_num:
            return self.__class__(self.gn_bot.get_by_id(self.site_num))


    def find_nearby(self):
        """Queries the GeoNames findNearby webservice"""
        return SiteList(self.gn_bot.find_nearby(self.latitude,
                                                self.longitude,
                                                2))


    def compare(self, other):
        """Checks if two sites are equivalent"""
        n = max([len(attr) for attr in self._attributes])
        for attr in self._attributes:
            val1 = getattr(self, attr)
            val2 = getattr(other, attr)
            if val1 or val2 and val1 != val2:
                print(u'{}: {} <=> {}'.format(attr.ljust(n), val1, val2))


    def contains(self, other=None, lat=None, lng=None, check_radius=False):
        """Checks if this site contains another site or point"""
        # FIXME: This will fail on the international dateline
        assert other or (lat and lng)
        result = False
        # If this is an admin div, compare its name to the other site
        if other and self.site_kind.startswith(('ADM', 'PCL')):
            # Look for the official names of the state and county
            names = set(self.site_names + self.synonyms)
            #admin = set([other.country, other.state_province, other.county])
            #if names & admin:
            #    result = True
            if (self.site_kind.startswith('PCL')
                and other.country in names):
                    result = True
            elif (self.site_kind == 'ADM1'
                and other.state_province in names):
                    result = True
            elif (self.site_kind == 'ADM2'
                  and other.county in names):
                    result = True
        # Check if the other site falls within this site's uncertainty
        polygon = self.polygon(dec_places=None, for_plot=True)
        if (not result
            and not polygon
            and (check_radius
                 or self.site_kind.startswith(('ADM', 'PCL')))):
            radius = self.get_radius()
            circle = get_circle(self.latitude, self.longitude, radius)
            # Reverse order to lng-lat
            polygon = [(lng_, lat_) for lat_, lng_ in circle]
        # Check if the other site falls within this site's bounding box. We
        # don't need to worry about whether the site is an admin div here.
        if polygon and not result:
            polygon = Polygon(polygon)
            try:
                shape = Polygon(other.polygon(dec_places=None, for_plot=True))
            except TypeError:
                shape = Point(float(other.longitude), float(other.latitude))
            except AttributeError:
                shape = Point(lng, lat)
            result = polygon.contains(shape)
        if other is None:
            other = '({}, {})'.format(lat, lng)
        if result:
            logger.debug('{} contains {}'.format(self, other))
        else:
            logger.debug('{} does not contain {}'.format(self, other))
        return result


    def within(self, other):
        """Checks if this site is contained by another site"""
        return other.contains(self)


    def is_close_to(self, other=None, lat=None, lng=None, distance_km=1):
        """Checks if site is within a distance of another site or point"""
        return (self.contains(other)
                or other.contains(self)
                or self.distance_from(other) < distance_km)


    def is_nsew_of(self, other, bearing, distance_km=100):
        pass


    def get_point(self, distance_km, bearing,
                  err_degrees=None, err_distance=None):
        """Calculates a point and error radius at a distance along a bearing"""
        polygon = self.polygon(dec_places=None)
        if polygon:
            coords = polygon
            logger.debug('Calculating point from polygon')
        else:
            coords = (self.latitude, self.longitude)
            logger.debug('Calculating point from lat-lng')
        return get_point(coords,
                         distance_km,
                         bearing,
                         err_degrees,
                         err_distance)


    def distance_from(self, other=None, lat=None, lng=None):
        """Calculates distance in kilometers between sites or points"""
        assert other or (lat and lng)
        if other:
            lat, lng = other.latitude, other.longitude
        return get_distance(self.latitude, self.longitude, lat, lng)


    def stripwords(self, val, field):
        """Strips field-specific words from the given value"""
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
        if val.lower().startswith('locality key:'):
            val = val.split(':', 1)[1]
            self.locality = val
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


    def classify(self):
        # Checks if fields contain directional info instead of just place names
        for attr in self._attributes:
            if attr == 'site_names':
                continue
            if is_directions(getattr(self, attr)):
                return 'specific'
        return 'site'


    def _classify_emu_record(self, rec):
        """Classifies EMu records based on specificity of locality info"""
        classifications = {
            'collection event': [
                'ColDateVisitedFrom',
                'ColDateVisitedFromModifier',
                'ColDateVisitedConjunction',
                'ColDateVisitedTo',
                'ColDateVisitedToModifier',
                'ColTimeVisitedFrom0',
                'ColTimeVisitedFromModifier_tab',
                'ColTimeVisitedConjunction_tab',
                'ColTimeVisitedTo0',
                'ColTimeVisitedToModifier_tab',
                'ColVerbatimDate',
                'ColParticipantRef_tab',
                'ColParticipantRole_tab',
                'ColParticipantEtAl'
            ],
            'expedition': [
                'ExpExpeditionName',
                'AquVesselName',
                'AquCruiseNumber',
                'ExpStartDate',
                'ExpCompletionDate',
                'ExpProjectNumber',
                'ColCollectionMethod'
            ],
            'specific': [
                # Depth
                'AquDepthFromMet',
                'AquDepthFromFt',
                'AquDepthFromFath',
                'AquDepthFromModifier',
                'AquDepthToMet',
                'AquDepthToFt',
                'AquDepthToFath',
                'AquDepthToModifier',
                'AquDepthDetermination',
                'AquVerbatimDepth',
                'AquBottomDepthFromMet',
                'AquBottomDepthFromFt',
                'AquBottomDepthFromFath',
                'AquBottomDepthFromModifier',
                'AquBottomDepthToMet',
                'AquBottomDepthToFt',
                'AquBottomDepthToFath',
                'AquBottomDepthToModifier',
                'AquBottomDepthDetermination',
                'AquVerbatimBottomDepth',
                'DepSourceOfSample',
                # Elevation
                'TerElevationFromMet',
                'TerElevationFromFt',
                'TerElevationFromModifier',
                'TerElevationToMet',
                'TerElevationToFt',
                'TerElevationToModifier',
                'TerElevationDetermination',
                'TerVerbatimElevation',
                'DepSourceOfSample',
                # UTM/other coordinates
                'MapUTMEastingFloat_tab',
                'MapUTMNorthingFloat_tab',
                'MapUTMZone_tab',
                'MapUTMDatum_tab',
                'MapUTMFalseEasting_tab',
                'MapUTMFalseNorthing_tab',
                'MapUTMMethod_tab',
                'MapUTMDeterminedByRef_tab',
                'MapUTMComment_tab',
                'MapOtherKind_tab',
                'MapOtherCoordA_tab',
                'MapOtherCoordB_tab',
                'MapOtherDatum_tab',
                'MapOtherSource_tab',
                'MapOtherMethod_tab',
                'MapOtherOffset_tab',
                'MapOtherDeterminedByRef_tab',
                'MapOtherComment_tab',
                # Map info - maps now included in EMu site
                #'MapType',
                #'MapScale',
                #'MapName',
                #'MapNumber',
                #'MapCoords',
                #'LocQUAD',
                #'MapOriginalCoordinateSystem',
                # Other info
                'ColBibliographicRef_tab',
                'ColContractNumber_tab',
                'ColContractRecipientRef_tab',
                'ColContractDescription_tab',
                'ColPermitNumber_tab',
                'ColPermitIssuerRef_tab',
                'ColPermitDescription_tab',
                'NteText0',
                'NteDate0',
                'NteType_tab',
                'NteAttributedToRef_nesttab',
                'NteMetadata_tab',
                'MulMultiMediaRef_tab'
            ]
        }
        # Exclude certain notes from consideration
        cols = [
            'NteText0',
            'NteDate0',
            'NteType_tab',
            'NteAttributedToRef_nesttab',
            'NteMetadata_tab'
        ]
        try:
            rec.grid(cols).delete(NteType_tab='Legacy Volcano Data')
        except IndexError:
            pass
        classification = self.classify()
        # Check if site/station number is populated by the collector
        classes =  ['collection event', 'expedition', 'site', 'specific']
        if (self.site_kind and self.site_kind.lower() not in classes
            or self.site_source == 'Collector'):
                return 'station'
        # Check if EMu fields beyond what is integrated into Site have data
        for kind in ['expedition', 'collection event', 'specific']:
            for field in classifications[kind]:
                val = rec(field)
                if any(val):
                    logger.info('Classified as {}'
                                ' ({}="{}")'.format(kind, field, val))
                    return kind
        return classification


    def _check_attributes(self):
        """Verifies that all required attributes have been defined"""
        for attr in self._attributes:
            getattr(self, attr)
        # Fix lat-lngs given as lists
        if isinstance(self.latitude + self.longitude, list):
            lats = [float(lat) for lat in self.latitude]
            lngs = [float(lng) for lng in self.longitude]
            self.bbox = {
                'north': '{:.4f}'.format(max(lats)),
                'south': '{:.4f}'.format(min(lats)),
                'east': '{:.4f}'.format(max(lngs)),
                'west': '{:.4f}'.format(min(lngs))
            }
            self.latitude = '{:.4f}'.format(sum(lats) / len(lats))
            self.longitude = '{:.4f}'.format(sum(lngs) / len(lngs))


SiteList.itemclass = Site
