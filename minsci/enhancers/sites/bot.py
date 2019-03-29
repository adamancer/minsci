"""Defines a requests session customized to interact with GeoNames"""
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import logging
logger = logging.getLogger(__name__)

from builtins import str
from builtins import range
from past.builtins import basestring
import math
import os
import time
from datetime import datetime

import requests
import requests_cache
from lxml import etree
from requests.structures import CaseInsensitiveDict

from .sitelist import SiteList


class Bot(requests_cache.CachedSession):
    """Methods to handle and retry HTTP requests for georeferencing"""

    def __init__(self, wait, *args, **kwargs):
        self.quiet = kwargs.pop('quiet', False)
        super(Bot, self).__init__(*args, **kwargs)
        self.wait = wait


    def _retry(self, func, *args, **kwargs):
        """Retries failed requests using a simple exponential backoff"""
        for i in range(8):
            try:
                response = func(*args, **kwargs)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                seconds = 30 * 2 ** i
                print('Retrying in {:,} seconds...'.format(seconds))
                time.sleep(seconds)
            else:
                if not response.from_cache:
                    if not self.quiet:
                        print('Resting up for the big push...')
                    time.sleep(self.wait)
                return response
        raise Exception('Maximum retries exceeded')


class SiteBot(Bot):
    """A cacheable requests object customized for GeoNames webservices

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """

    def __init__(self, username, user_id=None, **kwargs):
        wait = kwargs.pop('wait', 3600 / 2000)
        super(SiteBot, self).__init__(wait, cache_name='bot')
        self.username = username
        if user_id is None:
            user_id = username
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })


    def _map_aliases(self, params):
        return params
        try:
            params['countryName'] = self._map_country(params['country'])
        except KeyError:
            pass
        else:
            del params['country']
        try:
            params['adminCode1'] = NAME_TO_ABBR.get(params['state'],
                                                    params['state'])
        except KeyError:
            pass
        else:
            del params['state']
        return params


    @staticmethod
    def _map_country(country):
        if isinstance(country, basestring):
            country = [s.strip() for s in country.split('|')]
        codes = [TO_COUNTRY_CODE.get(c.strip()) for c in country if c]
        codes = [code for code in codes if code is not None]
        if len(codes) != len(country):
            raise ValueError('Unknown country: {}'.format(country))
        return codes


    def _query_geonames(self, url, **params):
        """Generalized method for querying the GeoNames webservices

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
        if not self.quiet:
            logger.info('GeoNames URL: {}'.format(response.url))
        if response.status_code == 200:
            content = response.json()
            status = content.get('status')
            if status is None:
                return content.get('geonames', content)
            elif response.from_cache:
                # If bad response comes from cache, delete that entry and
                # try again
                if status.get('value') not in (15,):
                    print(response.url)
                    print('{message} (code={value})'.format(**status))
                    self.cache.delete_url(response.url)
                    return self._query_geonames(url, **params)
            else:
                # If bad response is live, kill the process
                print(response.url)
                print('{message} (code={value})'.format(**status))
                if status.get('value') in (18, 19, 20):
                    self.cache.delete_url(response.url)
                    raise RuntimeError('Out of credits')
                # If not a credit error, try again in 30 seconds
                if status.get('value') not in (15,):
                    self.cache.delete_url(response.url)
                    time.sleep(30)
                    return self._query_geonames(url, **params)
        raise ValueError('Bad response: {}'.format(response.status_code))


    def get_by_id(self, geoname_id, style='MEDIUM'):
        """Returns feature data for a given GeoNames ID

        Args:
            geoname_id (str): the ID of a feature in GeoNames

        Returns:
            JSON representation of the matching feature
        """
        assert geoname_id
        url = 'http://api.geonames.org/getJSON'
        return self._query_geonames(url, geonameId=geoname_id, style=style)


    def search(self, query, **params):
        """Searches all GeoNames fields for a query string

        Args:
            query (str): query string
            countries (mixed): a list or pipe-delimited string of countries
            features (list): a list of GeoNames feature classes and codes

        Returns:
            JSON representation of matching locations
        """
        url = 'http://api.geonames.org/searchJSON'
        valid = set([
            'adminCode1',
            'adminCode2',
            'country',
            'countryName',
            'state',
            'features'
            ])
        invalid = sorted(list(set(params) - valid))
        if invalid:
            raise ValueError('Illegal params: {}'.format(invalid))
        if query:
            params['name'] = query
            params = self._map_aliases(params)
            try:
                params['featureClass'] = [c for c in params['features'] if len(c) == 1]
                params['featureCode'] = [c for c in params['features'] if len(c) > 1]
                del params['features']
            except KeyError:
                pass
            return self._query_geonames(url, **params)
        else:
            return []


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


    def ocean(self, lat, lng, dec_places=None):
        """Returns basic ocean information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/oceanJSON'
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
            if not isinstance(lat, float):
                lat = float(lat)
            if not isinstance(lng, float):
                lng = float(lng)
            mask = '{0:.' + str(dec_places) + 'f}'
            lat = mask.format(lat)
            lng = mask.format(lng)
        params = {'lat': lat, 'lng': lng}
        return self._query_geonames(url, **params)




def distance_on_unit_sphere(lat1, lng1, lat2, lng2, unit='km'):
    """Calculates the distance in km between two points on a sphere

    From http://www.johndcook.com/blog/python_longitude_latitude/

    Args:
        lat1 (int or float): latitude of first coordinate pair
        lng1 (int or float): longitude of first coordinate pair
        lat2 (int or float): latitude of second coordinate pair
        lng2 (int or float): longitdue of second coordinate pair

    Returns:
        Distance between two points in km
    """
    # Coerce strings to floats
    lat1, lng1, lat2, lng2 = [float(s) if not isinstance(s, float) else s
                              for s in [lat1, lng1, lat2, lng2]]
    # Convert latitude and lngitude to spherical coordinates in radians.
    degrees_to_radians = math.pi / 180.
    phi1 = (90. - lat1) * degrees_to_radians
    phi2 = (90. - lat2) * degrees_to_radians
    # theta = longitude
    theta1 = lng1 * degrees_to_radians
    theta2 = lng2 * degrees_to_radians
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
    units = {
        'km': 6371.
    }
    return arc * units[unit]


def dec2dms(dec, is_lat):
    """Converts decimal degrees to degrees-minutes-seconds

    Args:
        dec (float): a coordinate as a decimal
        is_lat (bool): specifies if the coordinate is a latitude

    Returns:
        Coordinate in degrees-minutes-seconds
    """
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


def _read_countries(fn):
    """Reads ISO country codes from file

    Args:
        fn (str): name of the file containing the country abbreviations

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(os.path.dirname(__file__), 'files', fn), 'r') as f:
        for line in f:
            row = line.split('\t')
            country = row[4]
            code = row[0]
            if code and country:
                abbr_to_name[code] = country
                name_to_abbr[country] = code
    return abbr_to_name, name_to_abbr


def _read_states(fn):
    """Reads U.S. state abbreviations from file

    Args:
        fn (str): the name of the file containing U. S. state abbreviations

    Returns:
        Dictioanaries mapping abbreviatiosn to names and vice versa
    """
    abbr_to_name = CaseInsensitiveDict()
    name_to_abbr = CaseInsensitiveDict()
    with open(os.path.join(os.path.dirname(__file__), 'files', fn), 'r') as f:
        for line in f:
            row = line.split('\t')
            state = row[0]
            abbr = row[3]
            abbr_to_name[abbr] = state
            name_to_abbr[state] = abbr
    return abbr_to_name, name_to_abbr


ABBR_TO_NAME, NAME_TO_ABBR = _read_states('states.txt')
FROM_COUNTRY_CODE, TO_COUNTRY_CODE = _read_countries('countries.txt')
