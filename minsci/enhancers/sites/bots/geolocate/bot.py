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

from ..bot import Bot
from ...sitelist import SiteList


class GEOLocateBot(Bot):
    """A cacheable requests object customized for the GEOLocate webservice

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """

    def __init__(self, username, user_id=None, **kwargs):
        wait = kwargs.pop('wait', 3600 / 2000)
        cache_name = os.path.join('cache', 'geolocate')
        try:
            os.mkdir('cache')
        except OSError:
            pass
        super(GEOLocateBot, self).__init__(wait, cache_name=cache_name)
        self.username = username
        if user_id is None:
            user_id = username
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })


    def glcwrap(self, locality, country, state=None, county=None, **params):
        url = ('http://www.museum.tulane.edu/webservices/'
               'geolocatesvcv2/glcwrap.aspx')
        params['locality'] = locality
        params['country'] = country
        if state:
            params['state'] = state
        if county:
            params['county'] = county
        response = self._retry(self.get, url, params=defaults)
        if not self.quiet:
            logger.info('GEOLocate URL: {}'.format(response.url))
        if response.status_code == 200:
            return response.json()
        raise ValueError('Bad response: {}'.format(response.status_code))


    def match(self, jsondict):
        features = jsondict.get('resultset', {}).get('features', [])
        matches = []
        for feature in features:
            parse_pattern = feature['properties']['parsePattern']
            pattern = ('Distance (N(orth)?|S(outh)?|E(ast)?|W(est)?){1,3}'
                       ' of %?[A-Z ]+%?')
            if re.match(pattern, parse_pattern, flags=re.I):
                matches.append(matches)
        return matches
