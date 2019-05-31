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

from ..bot import Bot
from ...helpers import AdminParser
from ...sitelist import SiteList




class GeoNamesBot(Bot):
    """A cacheable requests object customized for GeoNames webservices

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """
    adm = AdminParser()

    def __init__(self, username, user_id=None, **kwargs):
        wait = kwargs.pop('wait', 3600 / 2000)
        cache_name = os.path.join('cache', 'bot')
        try:
            os.mkdir('cache')
        except OSError:
            pass
        super(GeoNamesBot, self).__init__(wait, cache_name=cache_name)
        self.username = username
        if user_id is None:
            user_id = username
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })


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
                results = content.get('geonames', content)
                logger.info('Found {} records'.format(len(results)))
                return results
            elif response.from_cache:
                # If bad response comes from cache, delete that entry and
                # try again
                if status.get('value') not in (15,):
                    try:
                        logger.info('{message} (code={value})'.format(**status))
                    except KeyError:
                        logger.info('Unknown error (code={value})'.format(**status))
                    self.cache.delete_url(response.url)
                    return self._query_geonames(url, **params)
            else:
                # If bad response is live, kill the process
                try:
                    logger.info('{message} (code={value})'.format(**status))
                except KeyError:
                    logger.info('Unknown error (code={value})'.format(**status))
                if status.get('value') in (18, 19, 20):
                    self.cache.delete_url(response.url)
                    raise RuntimeError('Out of credits')
                # If not a credit error, try again in 30 seconds
                if status.get('value') not in (15,):
                    self.cache.delete_url(response.url)
                    time.sleep(30)
                    return self._query_geonames(url, **params)
                else:
                    raise ValueError('Bad response:'
                                     ' {} ({})'.format(status, response.url))
        raise ValueError('Bad response: {} ({})'.format(response.status_code,
                                                        response.url))


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
            try:
                params['featureClass'] = [c for c in params['features'] if len(c) == 1]
                params['featureCode'] = [c for c in params['features'] if len(c) > 1]
                del params['features']
            except KeyError:
                pass
            return self._query_geonames(url, **params)
        else:
            return []


    def find_nearby(self, lat, lng, dec_places=None, radius=10):
        """Returns geographical information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/findNearbyJSON'
        return self._find_latlong(url, lat, lng, dec_places, radius)


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


    def ocean(self, lat, lng, dec_places=None, radius=100):
        """Returns basic ocean information for a lat-long pair

        Args:
            lat (float): latitide
            lng (float): longitude
            dec_places (int): decimal places

        Returns:
            JSON representation of point
        """
        url = 'http://api.geonames.org/oceanJSON'
        return self._find_latlong(url, lat, lng, dec_places, radius)


    def _find_latlong(self, url, lat, lng, dec_places=None, radius=10):
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
        if radius is not None:
            params['radius'] = radius
        return self._query_geonames(url, **params)


    def get_state(self, name, country_code):
        results = self.search(name, country=country_code, features=['ADM1'])
        return results[0]


    def get_country(self, name, country_code):
        features = ['PCL', 'PCLD', 'PCLH', 'PCLI', 'PCLIX', 'PCLS']
        results = self.search(name, country=country_code, features=features)
        return results[0]


    @staticmethod
    def _map_country(countries):
        """Maps country name to code"""
        if not isinstance(countries, list):
            countries = [s.strip() for s in countries.split('|')]
        try:
            return [self.adm.to_country_code(c.strip()) for c in country if c]
        except KeyError:
            raise ValueError('Unknown country: {}'.format(country))
