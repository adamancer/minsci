"""Defines a requests session customized to interact with EarthChem"""
from __future__ import print_function
from __future__ import unicode_literals

from builtins import range
from builtins import object
import math
import re
import time
from datetime import datetime

import requests
from lxml import etree

#from database import Chemistry, Session

try:
    import requests_cache
    BASECLASS = requests_cache.CachedSession
except KeyError:#NameError:
    BASECLASS = requests.Session


class Bot(BASECLASS):
    """Methods to handle and retry HTTP requests for georeferencing"""

    def __init__(self, wait, *args, **kwargs):
        super(Bot, self).__init__(*args, **kwargs)
        self.wait = wait
        self.quiet = True


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
                response.from_cache
                if hasattr(response, 'from_cache') and not response.from_cache:
                    if not self.quiet:
                        print('Resting up for the big push...')
                    time.sleep(self.wait)
                return response
        raise Exception('Maximum retries exceeded')




class ChemBot(Bot):
    """A cacheable requests object customized for EarthChem webservices

    Attributes:
        username (str): a valid username for EarthChem
        headers (dict): headers data for requests

    """

    def __init__(self, user_id, *args, **kwargs):
        wait = 3
        super(ChemBot, self).__init__(wait, *args, **kwargs)
        user_agent = 'MinSciBot/0.2 ({})'.format(user_id)
        self.headers.update({
            'User-Agent': user_agent
            })
        # Maps simple names to EarthChem field names
        self._params = {}


    def _query_earthchem(self, url, **params):
        """Generalized method for querying the EarthChem webservices

        Args:
            url (str): the url to query
            params (dict): query parameters

        Returns:
            Result set as JSON
        """
        defaults = {
            'outputlevel': 'method',
            'outputtype': 'json',
            'searchtype': 'rowdata',
            'standarditems': 'yes',
            'startrow': 0
        }
        defaults.update(params)
        # Make and parse query
        response = self._retry(self.get, url, params=defaults)
        if not self.quiet:
            print('url: {}'.format(response.url))
        if response.status_code == 200:
            if response.text == 'no results found':
                return None
            #self.cache.delete_url(response.url)
            return response


    def get_sample(self, sample_id, doi=None, title=None, author=None):
        """Returns EarthChem data for a given sample id

        Args:
            sample_id (str): a sample identifier
            doi (str): the doi of a publication
            title (str): the title of a publication
            author (str): the last name of the first author of a publication

        Returns:
            JSON representation of the matching sample
        """
        assert sample_id and (doi or title and author)
        url = 'http://ecp.iedadata.org/restsearchservice'
        response = None
        # Search by DOI
        if doi:
            response = self._query_earthchem(url, sampleid=sample_id, doi=doi)
        # Search by title and author
        if not response and title:
            response = self._query_earthchem(url, sampleid=sample_id, title=title, author=author)
        return response


    def get_publication(self, doi=None, title=None, author=None):
        """Returns EarthChem data for a given publication

        Args:
            doi (str): the doi of a publication
            title (str): the title of a publication
            author (str): the last name of the first author of a publication

        Returns:
            JSON representation of the matching sample
        """
        assert doi or title and author
        url = 'http://ecp.iedadata.org/restsearchservice'
        content = ChemTable()
        # Search by DOI
        if doi:
            content = self._query_earthchem(url, doi=doi)
        # Search by title and author
        if not content and title:
            title = ' '.join([w for w in re.split('\W', title) if w])
            content = self._query_earthchem(url, title=title, author=author)
        return content




class ChemTable(object):
    """Contains methods for tabulating chemical data from EarthChem"""

    def __init__(self, response=None):
        try:
            self.rows = response.json()
            keys = [k for k in re.findall('"([a-z0-9_]+)":', response.text)]
            self.keys = [k for i, k in enumerate(keys) if not k in keys[:i]]
        except (AttributeError, ValueError):
            self.rows = []
            self.keys = []
        self.tas_url = 'http://adamancer.pythonanywhere.com/tas/'


    def __iter__(self):
        return iter(self.rows)


    def __bool__(self):
        return self.rows != []


    def append(self, obj):
        for key in obj:
            if not key in self.keys:
                self.keys.append(key)
        return self.rows.append(obj)


    def extend(self, obj):
        if obj and isinstance(obj, ChemTable):
            self.keys += [key for key in obj.keys if key not in self.keys]
            return self.rows.extend(obj.rows)
        for val in object:
            self.append(val)


    def coordinates(self):
        coordinates = []
        for row in self.rows:
            lat = row.get('latitude')
            lng = row.get('longitude')
            if lat and lng:
                coordinates.append((lat, lng))
        return list(set(coordinates))


    def tas_name(self):
        tas = self.tas()
        if tas:
            resp = requests.get(self.tas_url + 'name?' + '&'.join(tas))
            return resp.text
        return ''


    def tas_plot(self):
        tas = list(set(self.tas()))
        if tas:
            return self.tas_url + 'plot?' + '&'.join(tas)
        return None


    def tas(self):
        tas = []
        for row in self.rows:
            sio2 = row.get('sio2')
            na2o = row.get('na2o')
            k2o = row.get('k2o')
            if sio2 and na2o and k2o:
                tas.append('sio2={sio2}&na2o={na2o}&k2o={k2o}'.format(**row))
        return tas


    def tabulate(self):
        # Identify populated cells
        keys = []
        for row in self.rows:
            for key, val in row.items():
                if val:
                    keys.append(key)
        keys = [k for k in self.keys if k in keys]
        # Write table of populated cells only
        table = []
        self.rows.sort(key=lambda row: row['sample_id'])
        for row in self.rows:
            table.append([row.get(key, '') for key in keys])
        if table:
            table.insert(0, keys)
        return table


    def save(self):
        db_rows = []
        for row in self.rows:
            row['as_'] = row['as']
            del row['as']
            for key, val in row.items():
                if not val:
                    row[key] = None
            db_rows.append(Chemistry(**row))
        session = Session()
        session.bulk_save_objects(db_rows)
        session.commit()


    def match_samples(self, sample_ids):
        sample_ids = {self.format_key(k): v for k, v in sample_ids.items()}
        rows = []
        for row in self.rows:
            sample_id = self.format_key(row['sample_id'])
            if sample_id in sample_ids:
                url = ('http://geogallery.si.edu/index.php/portal?guid={}&'
                       'schema=simpledwr&format=json').format(sample_ids[sample_id])
                from requests.compat import quote
                url = '/esper?url=' + quote(url)
                row['sample_id'] = '<a href="{}">{}</a>'.format(url, row['sample_id'])
                rows.append(row)
        self.rows = rows


    @staticmethod
    def format_key(val):
        return val.lower().replace(' ', '-')
