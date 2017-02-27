"""Defines a requests session customized to interact with GeoNames"""

import math
import time
from datetime import datetime

import requests
import requests_cache
from lxml import etree

from .containers import GeoList, TO_COUNTRY_CODE, NAME_TO_ABBR


class GeoBot(requests_cache.CachedSession):
    """Methods to handle and retry HTTP requests for georeferencing"""

    def __init__(self, wait, *args, **kwargs):
        super(GeoBot, self).__init__(*args, **kwargs)
        self.wait = wait


    def _retry(self, func, *args, **kwargs):
        """Retries failed requests using a simple exponential backoff"""
        for i in xrange(8):
            try:
                response = func(*args, **kwargs)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                seconds = 30 * 2 ** i
                print 'Retrying in {:,} seconds...'.format(seconds)
                time.sleep(seconds)
            else:
                if not response.from_cache:
                    print 'Resting up for the big push...'
                    time.sleep(self.wait)
                return response
        raise Exception('Maximum retries exceeded')


class GeoNamesBot(GeoBot):
    """A cacheable requests object customized for GeoNames webservices

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """

    def __init__(self, username, user_id=None):
        wait = 3600. / 2000.
        super(GeoNamesBot, self).__init__(wait, cache_name='geobots')
        self.username = username
        if user_id is None:
            user_id = username
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })
        # Maps simple names to GeoNames field names
        self._params = {
            'country': 'countryName',
            'state': 'adminName1',
            'county': 'adminName2'
        }


    def _query_geonames(self, url, **params):
        """Basic search function

        Args:
            url (str): the url to query
            params (dict): query parameters

        Returns:
            Result set as JSON
        """
        defaults = {
            'formatted': 'True',
            'style': 'full',
            'username': self.username,
        }
        defaults.update(params)
        # Make and parse query
        response = self._retry(self.get, url, params=defaults)
        if response.status_code == 200:
            #print response.url
            content = response.json()
            status = content.get('status')
            if status is None:
                return GeoList(content.get('geonames', []), **self._params)
            elif response.from_cache:
                # If bad response comes from cache, delete that entry and
                # try again
                self.cache.delete_url(response.url)
                return self._query_geonames(url, **self._params)
            else:
                # If bad response is live, kill the process
                self.cache.delete_url(response.url)
                print '{message} (code={value})'.format(**status)
                if status.get('value') in (18, 19, 20):
                    raise RuntimeError('Out of credits')
                # If not a credit error, try again in 30 seconds
                time.sleep(30)
                return self._query_geonames(url, **self._params)


    def get_by_id(self, geoname_id):
        """Get feature by GeoNames ID

        Args:
            geoname_id (str): the ID of a feature in GeoNames

        Returns:
            JSON representation of the matching feature
        """
        assert geoname_id
        url = 'http://api.geonames.org/getJSON'
        return self._query_geonames(url, geonameId=geoname_id)


    def search(self, query, countries=None, **params):
        """Searches all GeoNames fields for a query string

        Args:
            query (str): query string
            countries (mixed): a list or pipe-delimited string of countries
            featureClass (list)
            featureCode (list)

        Returns:
            JSON representation of matching locations
        """
        url = 'http://api.geonames.org/searchJSON'
        if query:
            params['q'] = query
            if countries is not None:
                if isinstance(countries, basestring):
                    countries = countries.split('|')
                codes = [TO_COUNTRY_CODE.get(c.strip()) for c in countries if c]
                codes = [code for code in codes if code is not None]
                if len(codes) == len(countries):
                    params['country'] = codes
            return self._query_geonames(url, **params)
        else:
            return GeoList([], **self._params)


    def find_nearby(self, lat, lng, dec_places=None):
        """Returns geographical information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/findNearbyJSON'
        return self._find_latlong(url, lat, lng, dec_places)


    def country_subdivision(self, lat, lng, dec_places=None):
        """Returns basic geographical information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/countrySubdivisionJSON'
        return self._find_latlong(url, lat, lng, dec_places)


    def _find_latlong(self, url, lat, lng, dec_places=None):
        """Returns information for a lat-long pair from the given url

        Args:
            url (str): url of webservice. Must accept lat/lng as params.
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        if dec_places is not None:
            mask = '{0:.' + str(dec_places) + 'f}'
            lat = mask.format(lat)
            lng = mask.format(lng)
        params = {'lat': lat, 'lng': lng}
        print 'Populating geography for {}...'.format(params)
        return self._query_geonames(url, **params)




class GEOLocateBot(GeoBot):
    """A cacheable requests object customized for GEOLocate webservices

    FIXME: This whole class needs to be cleaned up and tested
    """


    def search(self, loc_string, country, state, county=None, **kwargs):
        """Use the GeoLocate webservice to geolocate the query string

        Args:
            loc_string (str): a query string
            country (str): name or abbreviation of country
            state (str): name or abbreviation of state or equivalent
            country (str): name of county or equivalent

        Returns:
            Tuple including best match and payload. Best match is a list
            including lat, lng, radius, precision, and score of match. payload
            is a dict of search parameters.
        """
        print u'Geolocating "{}" using GeoLocate...'.format(loc_string)
        url = ('http://www.museum.tulane.edu/webservices'
               '/geolocatesvcv2/geolocatesvc.asmx/Georef2')
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        params = {
            'Country': country,
            'State': state,
            'County': county,
            'LocalityString': loc_string,
            'HwyX': True,
            'FindWaterbody': True,
            'RestrictToLowestAdm': False,
            'doUncert': True,
            'doPoly': False,
            'displacePoly': False,
            'polyAsLinkID': False,
            'LanguageKey': 0
            }
        params.update(kwargs)
        response = self.get(url, headers=headers, params=params)
        if response.status_code == 200:
            if not response.from_cache:
                print u' Caching {}...'.format(response.url)
                time.sleep(3)  # GeoLocate asks for a 3-second gap b/w requests
            nmsp = 'http://www.museum.tulane.edu/webservices/'
            base = '/nmsp:Georef_Result_Set/nmsp:ResultSet'
            # Process results file. Keep only the best match.
            root = etree.fromstring(response.text.encode('utf8'))  # why is encode here
            lat = root.xpath('{}/nmsp:WGS84Coordinate/nmsp:Latitude'.format(base),
                             namespaces={'nmsp': nmsp})
            lng = root.xpath('{}/nmsp:WGS84Coordinate/nmsp:Longitude'.format(base),
                             namespaces={'nmsp': nmsp})
            radius = root.xpath('{}/nmsp:UncertaintyRadiusMeters'.format(base),
                                namespaces={'nmsp': nmsp})
            precision = root.xpath('{}/nmsp:Precision'.format(base),
                                   namespaces={'nmsp': nmsp})
            score = root.xpath('{}/nmsp:Score'.format(base),
                               namespaces={'nmsp': nmsp})
            results = [[s.text for s in row] for row
                       in zip(lat, lng, radius, precision, score)]
            try:
                high_score = max([int(x[4]) for x in results])
            except ValueError:
                return None, params
            try:
                result = [r for r in results if int(r[4]) == high_score][0]
            except IndexError:
                # No match found
                result = None
            result[0] = float(result[0])  # decimalize latitude
            result[1] = float(result[1])  # decimalize longitude
            return result, params
        else:
            raw_input(response.text)


    @staticmethod
    def geolocate_to_emu(result, payload):
        """Create EMu import based on GeoLocate result

        TKTK
        """
        note = (u'Coordinates determined using the GEOLocate'
                ' Georef2 webservice for locality string'
                ' "' + payload['LocalityString'] + '."'
                ' Additional search parameters were: ')
        for key in ('Country',
                    'State',
                    'County',
                    'HwyX',
                    'FindWaterbody',
                    'RestrictToLowestAdm',
                    'doUncert',
                    'doPoly',
                    'displacePoly',
                    'polyAsLinkID',
                    'LanguageKey'):
            val = payload[key]
            if val is True:
                val = 'TRUE'
            elif val is False:
                val = 'FALSE'
            else:
                val = str(val)
            if bool(val):
                note += key + '=' + str(val) + '; '
        note = note.rstrip('; ')
        return {
            'LatLatitudeDecimal': [result[0]],
            'LatLongitudeDecimal': [result[1]],
            'LatComment': [result[3] + ' confidence'],
            'LatGeoreferencingNotes': [note],
            'LatDetSource': ['Georeference'],
            'LatRadiusVerbatim': [result[2] + ' m'],
            'LatRadiusProbability': [result[4]],
            'LatRadiusNumeric': [result[2]],
            'LatRadiusUnit': ['m'],
            'LatDatum': ['WGS84'],
            'LatDeterminedByRef': ['1006206'],
            'LatDetDate': [datetime.now().strftime('%d%m%Y')]
            }





class TownshipGeocoder(GeoBot):
    """A cacheable requests object customized for BLM geocoder webservice"""

    def geocommunicator(self, trs, state, meridian=None):
        """Use the BLM TownshipGeocoder webservice to geolocate TRS

        Args:
            trs (str): well-formed section-township-range
            state (str): name or abbreviation of a U.S. state
            meridian (str): number of principal meridian. This is required to
              geolocate a TRS, but rarely recorded, so the function will try
              out all principal meridians in a state if it is not provided.

        Returns:
            List of lat-lng pairs
        """
        print u'Geolocating "{}" using GeoCommunicator...'.format(trs)
        # Get two-letter abberviation for state
        if len(state) != 2:
            try:
                state = NAME_TO_ABBR[state.lower()]
            except KeyError:
                print u'"{}" is not a valid state'.format(state)
                return []
        # Format TRS following GeoCommunicator guidelines
        twn, rng, sec = trs.upper().split(' ', 2)
        qtr = ''
        if sec.count(' ') > 1:
            sec, qtr = sec.rsplit(' ', 1)
        gc_trs = [
            state,               # two-letter state abbreviation
            None,                # principal meridian (populated before request)
            twn.strip('TNS'),    # township number
            0,                   # township fraction (?)
            twn[-1],             # township direction
            rng.strip('REW'),    # range number
            0,                   # range fraction (?)
            rng[-1],             # range direction
            sec.strip('SEC. '),  # section number
            qtr,                 # quarter section as NW, N2NW, NWNWSW, etc.
            0
            ]
        # Identify prime meridians in the given state if meridian not given
        if meridian is None:
            params = {'StateAbbrev': state}
            url = ('http://www.geocommunicator.gov/TownshipGeocoder'
                   '/TownshipGeocoder.asmx/GetPMList')
            response = self._retry(self.get, url, params=params)
            if response.status_code == 200:
                if not response.from_cache:
                    print u' Caching {}...'.format(response.url)
                    time.sleep(3)
                root = etree.fromstring(response.text.encode('utf8'))
                meridians = root.xpath('/nmsp:TownshipGeocoderResult/nmsp:Data',
                                       namespaces={'nmsp': 'http://www.esri.com/'})
                meridians = [meridian.strip()[:2] for meridian
                             in meridians[0].text.split(',')]
        else:
            meridians = [meridian.zfill(2)]
        # Get coordinates for trs for all principal meridians
        url = ('http://www.geocommunicator.gov/TownshipGeocoder'
               '/TownshipGeocoder.asmx/GetLatLon')
        coordinates = []
        for meridian in meridians:
            gc_trs[1] = meridian
            params = {'TRS': ','.join([str(s) for s in gc_trs])}
            response = self._retry(self.get, url, params=params)
            if response.status_code == 200:
                if not response.from_cache:
                    print u' Caching {}...'.format(response.url)
                    time.sleep(3)
                root = etree.fromstring(response.text.encode('utf8'))
                result = root.xpath('/nmsp:TownshipGeocoderResult/nmsp:Data',
                                    namespaces={'nmsp': 'http://www.esri.com/'})
                if len(result):
                    root = etree.fromstring(result[0].text)
                    point = root.xpath('/rss/channel/item/georss:point',
                                       namespaces={'georss': 'http://www.georss.org/georss'})
                    lng, lat = [float(c) for c in point[0].text.split(' ')]
                    coordinates.append((lat, lng))
        return coordinates



def distance_on_unit_sphere(lat1, long1, lat2, long2):
    """Calculates the distance in km between two points on a sphere

    From http://www.johndcook.com/blog/python_longitude_latitude/

    Args:
        lat1 (int or float): latitude of first coordinate pair
        long1 (int or float): longitude of first coordinate pair
        lat2 (int or float): latitude of second coordinate pair
        long2 (int or float): longitdue of second coordinate pair

    Returns:
        Distance between two points in km
    """

    # Convert latitude and longitude to spherical coordinates in radians.
    degrees_to_radians = math.pi / 180.0

    # phi = 90 - latitude
    phi1 = (90.0 - lat1) * degrees_to_radians
    phi2 = (90.0 - lat2) * degrees_to_radians

    # theta = longitude
    theta1 = long1 * degrees_to_radians
    theta2 = long2 * degrees_to_radians

    # Compute spherical distance from spherical coordinates.
    # For two locations in spherical coordinates
    # (1, theta, phi) and (1, theta', phi')
    # cosine( arc length ) =
    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length
    cos = (math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2) +
           math.cos(phi1) * math.cos(phi2))
    arc = math.acos(cos)

    # Remember to multiply arc by the radius of the earth
    # in your favorite set of units to get length.
    return arc * 6371.


def dec2dms(dec, is_lat=True):
    """Converts decimal degrees to degrees-minutes-seconds"""
    # Force longitude if decimal degrees more than 90
    if is_lat and dec > 90:
        raise ValueError('Invalid latitude: {}'.format(dec))
    # Get degrees-minutes-seconds
    degrees = abs(int(dec))
    minutes = 60. * (abs(dec) % 1)
    seconds = 60. * (minutes % 1)
    minutes = int(minutes)
    if seconds >= 60:
        minutes += 1
        seconds -= 60
    if minutes == 60:
        degrees += 1
        minutes = 0
    if dec >= 0:
        hemisphere = 'N' if is_lat else 'E'
    else:
        hemisphere = 'S' if is_lat else 'W'
    # FIXME: Estimate precision based on decimal places
    mask = '{} {} {} {}'
    return mask.format(degrees, minutes, seconds, hemisphere)
