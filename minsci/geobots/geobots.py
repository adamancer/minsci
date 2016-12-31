"""Defines a requests session customized to interact with GeoNames"""

import math
import time

import requests_cache

from .containers import GeoList


class GeoNamesBot(requests_cache.CachedSession):
    """A cacheable requests object customized for GeoNames webservices

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """

    def __init__(self, username, user_id=None):
        super(GeoNamesBot, self).__init__(cache_name='geobots')
        self.username = username
        if user_id is None:
            user_id = username
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })
        self._params = {
            'country': 'countryName',
            'state': 'adminCode1',
            'county': 'adminCode2'
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
        response = self.get(url, params=defaults)
        if response.status_code == 200:
            content = response.json()
            status = content.get('status')
            if status is None:
                # Enforce a wait between non-cached requests. The time is
                # based on a limit of 2,000 requests per username per hour.
                if not response.from_cache:
                    time.sleep(1.8)
                return GeoList(content.get('geonames', []), **self._params)
            elif response.from_cache:
                # If bad response comes from cache, delete that entry and
                # try again
                self.cache.delete_url(response.url)
                return self._query_geonames(url, **self._params)
            else:
                # If bad response is live, kill the process
                self.cache.delete_url(response.url)
                print status, content.get('message')
                raise Exception('Out of credits')


    def search(self, query, **params):
        """Searches all GeoNames fields for a query string

        Args:
            query (str): query string
            country (str)
            adminCode1 (str)
            adminCode2 (str)
            adminCode3 (str)
            featureClass (list)
            featureCode (list)

        Returns:
            JSON representation of matching locations
        """
        url = 'http://api.geonames.org/searchJSON'
        if query:
            params.update({'q': query})
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


def distance_on_unit_sphere(self, lat1, long1, lat2, long2):
    """Calculates the distance between two points on a sphere

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
