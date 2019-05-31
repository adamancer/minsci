"""Defines methods for parsing and geolocating PLSS localities"""

from __future__ import unicode_literals
from __future__ import division
from builtins import str
from builtins import range
from builtins import object
import os
import re

import pyproj
import requests
import requests_cache

from .helpers import get_distance, get_size


cache_name = os.path.join('cache', 'bot')
try:
    os.mkdir('cache')
except OSError:
    pass
requests_cache.install_cache(cache_name)


class Box(object):
    """Determines bounding box and subsectionsfor a set of coordinates"""

    def __init__(self, *points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.x1, self.y1 = min(xs), min(ys)
        self.x2, self.y2 = max(xs), max(ys)
        self.xc, self.yc = (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2
        self.width = self.x2 - self.x1
        self.height = self.y2 - self.y1
        self.parents = []
        # Construct the NSEW bounding box
        self.bbox = {
            'north': self.y2,
            'south': self.y1,
            'east': self.x2,
            'west': self.x1,
        }
        self.radius = self.get_radius()
        self.name = None


    def __str__(self):
        return '({:.3f}, {:.3f}), ({:.3f}, {:.3f})'.format(self.y1, self.x1,
                                                           self.y2, self.x2)


    def __repr__(self):
        return str(self)


    def __iter__(self):
        return iter([(self.y1, self.x1), (self.y2, self.x2)])


    def get_centroid(self):
        """Returns the centroid of the box"""
        return self.yc, self.xc


    def get_radius(self):
        """Returns center-to-corner distance of the bounding box"""
        return get_distance(self.yc, self.xc, self.y1, self.x1)


    def get_size(self):
        """Returns the dimensions in km of the box"""
        return get_size(self.polygon())


    def subsection(self, direction):
        """Calculates a subsection of a PLSS section"""
        if not re.match('[NEWS23]{1,2}', direction):
            raise ValueError('Illegal direction: {}'.format(direction))
        divisor = 3. if '3' in direction else 2.
        # Get longitudes/x coordinates
        xs = self.x1, self.x2
        if direction[-1] == 'E':
            xs = self.xc, self.xc + self.width / divisor
        elif direction[-1] == 'W':
            xs = self.xc, self.xc - self.width / divisor
        x1, x2 = sorted(xs)
        # Get latitudes/y coordinates
        ys = self.y1, self.y2
        if direction[0] == 'N':
            ys = self.yc, self.yc + self.height / divisor
        elif direction[0] == 'S':
            ys = self.yc, self.yc - self.height / divisor
        y1, y2 = sorted(ys)
        # Create a new subclass of the current box based on the new point
        box = self.__class__((x1, y1), (x2, y2))
        box.name = '{} {}'.format(direction, self.name)
        box.parents = self.parents + [self]
        return box


    def supersection(self):
        """Returns the parent of a subsection"""
        return self.parents[-1]


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


    def site(self, site):
        """Create a site record for this PLSS division"""
        site = site.__class__({
            'country': site.country,
            'state_province': site.state_province,
            'county': site.county,
            'latitude': self.yc,
            'longitude': self.xc,
            'site_names': [self.name]
        })
        site.bbox = self.bbox
        return site




class PLSSBot(object):
    defaults = {
        'ext': '',
        'objectIds': '',
        'time': '',
        'geometry': '',
        'geometryType': 'esriGeometryEnvelope',
        'inSR': '',
        'spatialRel': 'esriSpatialRelIntersects',
        'relationParam': '',
        'outFields': '',
        'returnGeometry': 'false',
        'returnTrueCurves': 'false',
        'maxAllowableOffset': '',
        'geometryPrecision': '',
        'outSR': '',
        'returnIdsOnly': 'false',
        'returnCountOnly': 'false',
        'orderByFields': '',
        'groupByFieldsForStatistics': '',
        'outStatistics': '',
        'returnZ': 'false',
        'returnM': 'false',
        'gdbVersion': '',
        'returnDistinctValues': 'false',
        'resultOffset': '',
        'resultRecordCount': '',
        'f': 'json'
    }


    def find_township(self, state, twp, rng):
        """Finds a township and range using BLM webservices"""
        url = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/1/query'
        # Get params
        sql_params = {
            'state': state,
            'twp_no': twp.strip('TNS'),
            'twp_dir': twp[-1],
            'rng_no': rng.strip('REW'),
            'rng_dir': rng[-1]
        }
        # Write where clause
        mask = ("STATEABBR='{state}'"
                " AND TWNSHPNO LIKE '%{twp_no}'"
                " AND TWNSHPDIR='{twp_dir}'"
                " AND RANGENO LIKE '%{rng_no}'"
                " AND RANGEDIR='{rng_dir}'")
        params = {k: v[:] for k, v in self.defaults.items()}
        params.update({
            'where': mask.format(**sql_params),
            'outFields': 'PLSSID,STATEABBR,TWNSHPNO,TWNSHPDIR,RANGENO,RANGEDIR'
        })
        response = requests.get(url, params=params)
        if response.status_code == 200:
            result = response.json()
            features = [r.get('attributes', {})
                        for r in result.get('features', [])]
            if features:
                return features[0]['PLSSID']


    def find_section(self, plss_id, sec):
        """Finds a specific section using BLM webservices"""
        if plss_id is None:
            return []
        url = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2/query'
        sql_params = {'plss_id': plss_id, 'sec': str(sec.lower()).strip('sec. ')}
        mask = ("PLSSID='{plss_id}'"
                " AND FRSTDIVNO='{sec}'"
                " AND FRSTDIVTYP='SN'")
        params = {k: v[:] for k, v in self.defaults.items()}
        params.update({
            'where': mask.format(**sql_params),
            'outFields': 'FRSTDIVNO',
            'returnGeometry': 'true'
        })
        response = requests.get(url, params=params)
        boxes = []
        if response.status_code == 200:
            result = response.json()
            # Get the spatial reference
            wkid = 'epsg:{}'.format(result['spatialReference']['latestWkid'])
            proj_in = pyproj.Proj(init=wkid)
            proj_out = pyproj.Proj(init='epsg:4326')
            features = result.get('features', [])
            for feature in features:
                polygons = feature.get('geometry', {}).get('rings', [])
                for polygon in polygons:
                    lngs = [c[0] for c in polygon]
                    lats = [c[1] for c in polygon]
                    polygon = pyproj.transform(proj_in, proj_out, lngs, lats)
                    boxes.append(Box(*zip(polygon[0], polygon[1])))
                    break
        return boxes




class PLSSParser(object):
    """Parses and formats PLSS locality from a string"""

    def __init__(self):
        # Define patterns used to identify and parse PLSS patterns
        bad_prefixes = '((loc)|(hole)|(hwy)|(quads?:?)|(us)|#)'
        centers = '(cen\.?(ter)?)'
        corners = '(([NS][EW] *((1?/4)|(cor\.?(ner)?))?( of)?)(?![c0-9]))'
        quarters = '(([NS][EW] *((1?/4)|(q(uarter)?))?( of)?)(?![c0-9]))'
        halves = '([NSEW] *((1?/[23])|half))'
        townships = '(((T(ownship)?\.? *)?[0-9]{1,3} *[NS])(?![NSEW]))'
        ranges = '(((R(ange)?\.? *)?[0-9]{1,3} *[EW])(?![NSEW]))'
        sections = ('((?<!/)(((((s(ection)?)|(se?ct?s?))\.? *)'
                    '|\\b)[0-9]{1,3})(?!(-\d+[^NEWS]|\.\d)))')
        # Define quarter section
        qtr = ('\\b((((N|S|E|W|NE|SE|SW|NW)[, \-]*)'
               '((cor\.?|corner|half|q(uarter)?|(1?/[234]))'
               '[, /\-]*(of *)?)?)+)\\b')
        qtr_sections = ('((|[0-9]+){0}|{0}(?:(sec|[0-9]+[, /\-]'
                        '|T[0-9]|R[0-9])))').format(qtr)
        # Create full string baed on patterns
        pattern = [
            bad_prefixes,
            centers,
            corners,
            quarters,
            halves,
            townships,
            ranges,
            sections
            ]
        full = ('\\b((' +
                '|'.join(['(' + s + '[,;: /\.\-]*' + ')' for s in pattern]) +
                ')+)\\b')
        # Define class attributes
        self.sec_twn_rng = re.compile(full, re.I)
        self.townships = re.compile(townships, re.I)
        self.ranges = re.compile(ranges, re.I)
        self.sections = re.compile(sections + '[^\d]', re.I)
        self.quarter_sections = re.compile(qtr_sections, re.I)
        self.bad_prefixes = re.compile(bad_prefixes + ' ?[0-9]+', re.I)


    def parse(self, s):
        """Parse section-townshup-range from a string

        Args:
            s (str): a string

        Returns:
            Tuple containing the derived TRS string, an error string,
            and a copy of the original string with the longest substring
            marked in <strong> tags.
        """
        matches = [m[0] for m in self.sec_twn_rng.findall(s)
                   if 'n' in m[0].lower() or 's' in m[0].lower()]
        msg = None
        first_match = None
        # Iterate through matches, longest to shortest
        for match in sorted(matches, key=lambda s:len(s), reverse=True):
            errors = []
            # Strip bad prefixes (hwy, loc, etc.) that can be mistaken for
            # section numbers
            match = self.bad_prefixes.sub('', match)
            verbatim = self._format_verbatim(match)
            twp = self._format_township(match)
            rng = self._format_range(match)
            sec = self._format_section(match)
            qtr = self._format_quarter_section(match)
            return verbatim, twp, rng, sec, qtr


    def _format_verbatim(self, match):
        """Formats the verbatim string containing a PLSS locality"""
        cleaned = self.townships.sub('', match)
        cleaned = self.ranges.sub('', cleaned)
        matches = self.sections.findall(match)
        if matches:
            sec = sorted([val[0] for val in matches], key=len, reverse=True)[0]
            cleaned = cleaned.replace(sec, '')
        cleaned = self.quarter_sections.sub('', cleaned)
        cleaned = cleaned.strip(' ,;.')
        return match.replace(cleaned, '').strip(' ,;.')


    def _format_township(self, match):
        """Formats township as T4N"""
        sre_match = self.townships.search(match)
        val = None
        if sre_match is not None:
            val = sre_match.group(0)
            twp = u'T' + val.strip('., ').upper().lstrip('TOWNSHIP. ')
            return twp
        raise ValueError('Township error: {}'
                         ' (verbatim="{}")'.format(val, match))


    def _format_range(self, match):
        """Formats range as R4W"""
        sre_match = self.ranges.search(match)
        val = None
        if sre_match is not None:
            val = sre_match.group(0)
            rng = u'R' + val.strip('., ').upper().lstrip('RANGE. ')
            return rng
        raise ValueError('Range error: {}'
                         ' (verbatim="{}")'.format(val, match))


    def _format_section(self, match):
        """Formats section as Sec. 30"""
        # Format section. This regex catches some weird stuff sometimes.
        matches = self.sections.findall(match)
        sec = None
        if matches:
            sec = sorted([val[0] for val in matches], key=len, reverse=True)[0]
            sec = u'Sec. ' + sec.strip('., ').upper().lstrip('SECTION. ')
            return sec
        raise ValueError('Section error: {}'
                         ' (verbatim="{}")'.format(sec, match))


    def _format_quarter_section(self, match):
        """Formats quarter section as NW SE NE"""
        matches = self.quarter_sections.findall(match)
        if matches:
            qtrs_1 = [val[0] for val in matches if val[0]]
            qtrs_2 = [val for val in matches if '/' in val]
            qtrs = [qtrs for qtrs in (qtrs_1, qtrs_2) if len(matches) == 1]
            try:
                qtr = qtrs[0][0]
            except IndexError:
                # Not an error. Quarter section is not required
                pass
            else:
                # Clean up strings that sometimes get caught by this regex
                qtr = (qtr.upper()
                          #.replace(' ', '')
                          .replace(',', '')
                          .replace('QUARTER', '')
                          .replace('CORNER', '')
                          .replace('COR', '')
                          .replace('HALF', '2')
                          .replace('SEC', '')
                          .replace('1/4', '')
                          .replace('1/', '')
                          .replace('/2', '2')
                          .replace('/3', '3')
                          .replace('/4', '')
                          .replace('OF', '')
                          .replace('Q', '')
                          .replace('.', ''))
                # Check for illegal characters
                if not qtr.strip('NEWS23 '):
                    return qtr.strip().split(' ')
            raise ValueError('Quarter section error: {}'
                             ' (verbatim="{}")'.format(qtrs, match))
        return ''




class SectionTownshipRange(object):
    """Calculates properties of a PLSS locality in a string"""
    plss = PLSSParser()
    bot = PLSSBot()

    def __init__(self, orig, state):
        if len(state) != 2 or not state.isupper():
            raise ValueError('State must be a two-letter abbreviation')
        self.orig = orig
        self.state = state
        parsed = self.plss.parse(orig)
        self.verbatim, self.twp, self.rng, self.sec, self.qtr = parsed
        self.find()


    def __str__(self):
        qtr = ' '.join(self.qtr)
        return ' '.join([qtr, self.sec, self.twp, self.rng]).strip()


    def find(self):
        """Finds a given PLSS locality"""
        plss_id = self.bot.find_township(self.state, self.twp, self.rng)
        boxes = []
        for box in self.bot.find_section(plss_id, self.sec):
            box.name = ' '.join([self.sec, self.twp, self.rng]).strip()
            boxes.append(box)
            # Quarter sections increase in specificity from right to left,
            # so reverse the order for calculating subsections
            for div in self.qtr[::-1]:
                box = box.subsection(div)
                boxes.append(box)
        self.boxes = boxes
        if boxes:
            self.latitude =[c[0] for c in self.boxes[-1]]
            self.longitude = [c[1] for c in self.boxes[-1]]
        return boxes


    def sites(self, site):
        """Gets a list of sites describing a PLSS locality and subsections"""
        sites = []
        for box in self.boxes:
            sites.append(box.site(site))
        return sites


    def get_coords(self, *args, **kwargs):
        """Determines the coordinates for the most specific subsection"""
        return self.polygon(*args, **kwargs)


    def get_centroid(self, *args, **kwargs):
        """Determines the centroid for the most specific subsection"""
        return self.boxes[-1].polygon(*args, **kwargs)


    def polygon(self, *args, **kwargs):
        """Determines the coordinates for the most specific subsection"""
        return self.boxes[-1].polygon(*args, **kwargs)


    def get_radius(self, *args, **kwargs):
        """Determines center-to-corner distance for most specific subsection"""
        return self.boxes[-1].get_radius(*args, **kwargs)


    def describe(self, boxes=None):
        """Describes how the PLSS locality was determined"""
        mask = ('Polygon determined based on PLSS locality string "{}" for'
                ' state={} using BLM webservices at'
                ' https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer')
        if boxes and len(boxes) > 1:
            mask += '. Multiple localities matched this string.'
        if self.qtr:
            s = 's'
            mask += ('. The coordinates were refined to the given quarter'
                    ' section{} using situate.py.'.format(s))
        return mask.format(str(self), self.state)
