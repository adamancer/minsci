"""Defines a requests session customized to interact with GeoNames"""
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from builtins import str
from builtins import range
from past.builtins import basestring
import functools
import json
import math
import os
import re
import time
from datetime import datetime

import pandas as pd
import requests
import requests_cache
from lxml import etree
from requests.structures import CaseInsensitiveDict

from .bot import GeoNamesBot, ABBR_TO_NAME, NAME_TO_ABBR, FROM_COUNTRY_CODE, TO_COUNTRY_CODE
from .sitelist import SiteList
from ...standardizer import Standardizer



class LocalBot(GeoNamesBot):
    """Modifies bot to use local GeoNames data for search and id queries

    Attributes:
        username (str): a valid username for GeoNames
        headers (dict): headers data for requests

    """

    def __init__(self, fp, username, user_id=None):
        super(LocalBot, self).__init__(username, user_id=user_id)
        cols = [
            'geonamesid',
            'name',
            'asciiname',
            'alternatenames',
            'latitude',
            'longitude',
            'feature class',
            'feature code',
            'country code',
            'cc2',
            'admin1 code',
            'admin2 code',
            'admin3 code',
            'admin4 code',
            'population',
            'elevation',
            'dem',
            'timezone',
            'modification date'
        ]
        dtype = {
            'admin1 code': str,
            'admin2 code': str,
            'admin3 code': str,
            'admin4 code': str,
            'cc2': str
        }
        pkl = os.path.splitext(fp)[0] + '.pkl'
        try:
            self.df = pd.read_pickle(pkl)
            print('Loaded pickled dataframe')
        except OSError:
            print('Reading {}...'.format(fp))
            self.df = pd.read_csv(fp,
                                  sep='\t',
                                  header=None,
                                  names=cols,
                                  dtype=dtype,
                                  keep_default_na=False)
            self.df.set_index(['name',
                               'alternatenames',
                               'country code',
                               'admin1 code',
                               'feature code',
                               'feature class'])
            self.df.to_pickle(pkl)
        fp = os.path.join(os.path.dirname(__file__), 'files', 'admin_codes.json')
        try:
            raise
            self.admin = json.load(open(fp, 'r', encoding='utf-8'))
        except:
            self.admin = self._map_admin()
            json.dump(self.admin, open(fp, 'w', encoding='utf-8'), indent=2, sort_keys=True, ensure_ascii=False)
        self.std = Standardizer()


    def as_json(self, row):
        jsondict = {
            'countryCode': row['country code'],
            'geonameId': row['geonamesid'],
            'fcode': row['feature code'],
            'lat': row['latitude'],
            'lng': row['longitude'],
            'toponymName': row['name']
        }
        altnames = []
        if not isinstance(row['alternatenames'], float):
            altnames = [{'name': n} for n in row['alternatenames'].split(',')]
        jsondict['alternateNames'] = altnames
        jsondict['countryName'] = FROM_COUNTRY_CODE[row['country code']]
        jsondict.update(self._get_admin_names(row))
        return jsondict


    def get_names(self, row):
        names = []
        for key in ['name', 'asciiname', 'alternatenames']:
            if key == 'alternatenames':
                try:
                    names.extend([s.strip() for s in row[key].split(',')])
                except AttributeError:
                    pass
            else:
                names.append(row[key])
        return names

        names = row['name']



    def _map_admin(self):
        print('Mapping administrative codes...')
        admin = {}
        rows = self.df.loc[self.df['feature class'] == 'A']
        last = None
        for idx, row in rows.iterrows():
            feature_code = row['feature code']
            try:
                i = feature_code[-1]
                admin_key = 'admin{} code'.format(i)
                admin_code = row[admin_key]
            except IndexError:
                pass
            except (KeyError, TypeError):
                pass
            else:
                country_code = row['country code']
                if country_code != last:
                    print(country_code)
                    last = country_code
                for i, code in enumerate([country_code,
                                          feature_code,
                                          admin_code]):
                    if not isinstance(code, str):
                        print('{}: {} ({}, {})'.format(i + 1, code, admin_key, idx))
                        break
                else:
                    admin.setdefault(country_code, {}) \
                               .setdefault(feature_code, {}) \
                               .setdefault(admin_code, row['name'])
                    # Also store names. Unlike admin codes, names are not stored
                    # exactly as they appear in the db and are instead formatted
                    # to be easier to match.
                    for key in [self.std(n) for n in self.get_names(row)]:
                        if key and len(key) > 2:
                            admin[country_code][feature_code][key] = admin_code
        return admin


    def _map_id(self):
        print('Mapping administrative codes...')
        admin = {}
        rows = self.df.loc[self.df['feature class'] == 'A']
        for idx, row in rows.iterrows():
            feature_code = row['feature code']



    def _get_admin_names(self, row):
        admin = {}
        country_code = row['country code']
        for i in range(1, 5):
            admin_code = row['admin{} code'.format(i)]
            if admin_code:
                feature_code = 'ADM{}'.format(i)
                try:
                    name = self.get_admin_code(country_code, feature_code, admin_code)
                except KeyError:
                    pass
                else:
                    admin['adminCode{}'.format(i)] = admin_code
                    admin['adminName{}'.format(i)] = name
        return admin


    def get_admin_code(self, country_code, feature_code, val):
        val = self.std(val)
        if isinstance(country_code, list):
            country_code = country_code[0]
        try:
            return self.admin[country_code][feature_code][val]
        except KeyError:
            keys = []
            if val:
                keys = self.admin[country_code][feature_code]
                keys = [k for k in keys if k.startswith(val)]
            raise KeyError('{} => {}'.format(val, keys))


    def _map_aliases(self, params):
        try:
            params['country code'] = self._map_country(params['country'])
        except KeyError:
            pass
        else:
            del params['country']
        if params.get('state'):
            try:
                code = self.get_admin_code(params['country code'],
                                           'ADM1', params['state'])
            except KeyError:
                pass
            else:
                params['admin1 code'] = code
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


    def get_by_id(self, geoname_id, **kwargs):
        """Returns feature data for a given GeoNames ID

        Args:
            geoname_id (str): the ID of a feature in GeoNames

        Returns:
            JSON representation of the matching feature
        """
        assert geoname_id
        rows = self.df[self.df['geonamesid'] == int(geoname_id)]
        for _, row in rows.iterrows():
            return self.as_json(row)
        return {}


    def search(self, query, **params):
        """Searches all GeoNames fields for a query string

        Args:
            query (str): query string
            countries (mixed): a list or pipe-delimited string of countries
            features (list): a list of GeoNames feature classes and codes

        Returns:
            JSON representation of matching locations
        """
        valid = set(['country', 'state', 'features'])
        invalid = sorted(list(set(params) - valid))
        if invalid:
            raise ValueError('Illegal params: {}'.format(invalid))
        if query:
            params['name'] = query
            params = self._map_aliases(params)
            try:
                params['feature class'] = [c for c in params['features'] if len(c) == 1]
                params['feature code'] = [c for c in params['features'] if len(c) > 1]
                del params['features']
            except KeyError:
                pass
            # Build query from params
            conditions = []
            for key, val in params.items():
                if key == 'name':
                    pat = val
                    #print(' ', key, '==', val, 'or alternatenames like', pat)
                    cond = [
                        self.df['name'] == val,
                        self.df['alternatenames'].str.contains(pat, na=False, regex=False)
                    ]
                    conditions.append(self.or_(*cond))
                elif not isinstance(val, list) or len(val) == 1:
                    if len(val) == 1:
                        val = val[0]
                    #print(' ', key, '==', val)
                    conditions.append(self.df[key] == val)
                elif val:
                    #print(' ', key, 'in', val)
                    conditions.append(self.df[key].isin(val))
            rows = self.df[self.and_(*conditions)]
            # Limit to strong matches
            name = params['name']
            rows = [r for _, r in rows.iterrows()]
            #print(' Found {} potential matches'.format(len(rows)))
            rows = [r for r in rows if name in self.get_names(r)]
            #print(' Found {} matches'.format(len(rows)))
            return [self.as_json(r) for r in rows]
        else:
            return []


    @staticmethod
    def and_(*conditions):
        return functools.reduce(pd.np.logical_and, conditions)

    @staticmethod
    def or_(*conditions):
        return functools.reduce(pd.np.logical_or, conditions)
