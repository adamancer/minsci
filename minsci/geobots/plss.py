import re

import requests


class Box(object):

    def __init__(self, *points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.x1, self.y1 = min(xs), min(ys)
        self.x2, self.y2 = max(xs), max(ys)
        self.xc, self.yc =  (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2
        self.width = self.x2 - self.x1
        self.height = self.y2 - self.y1
        self.parents = []


    def __str__(self):
        return '({:.3f}, {:.3f}), ({:.3f}, {:.3f})'.format(self.x1, self.y1,
                                                           self.x2, self.y2)


    def centroid(self):
        return self.xc, self.yc


    def subsection(self, direction):
        if not re.match('[NEWS23]{1,2}', direction):
            raise ValueError('Illegal direction: {}'.format(direction))
        divisor = 3. if '3' in direction else 2.
        # Get longitudes/x coordinates
        xs = self.x1, self.x2
        if direction[-1] == 'E':
            xs = self.xc, self.xc + self.width / divisor
        elif direction [-1] == 'W':
            xs = self.xc, self.xc - self.width / divisor
        x1, x2 = sorted(xs)
        # Get latitudes/y coordinates
        ys = self.y1, self.y2
        if direction[0] == 'N':
            ys = self.yc, self.yc + self.height / divisor
        elif direction[0] == 'S':
            ys = self.yc, self.yc - self.height / divisor
        y1, y2 = sorted(ys)
        # Create a new subclass of the current box based on the new points
        box = self.__class__((x1, y1), (x2, y2))
        box.parents = self.parents + [self]
        return box


    def supersection(self):
        return self.parents[-1]


    def polygon(self):
        """Returns a closed polygon describing the section"""
        return [
            (self.x1, self.y1),
            (self.x1, self.y2),
            (self.x2, self.y2),
            (self.x2, self.y2),
            (self.x1, self.y1)
        ]




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
        params = {k: v[:] for k, v in self.defaults.iteritems()}
        params.update({
            'where': mask.format(**sql_params),
            'outFields': 'PLSSID,STATEABBR,TWNSHPNO,TWNSHPDIR,RANGENO,RANGEDIR'
        })
        response = requests.get(url, params=params)
        if response.status_code == 200:
            result = response.json()
            features = [r.get('attributes', {}) for r in result.get('features', [])]
            return features[0]['PLSSID']


    def find_section(self, plss_id, sec):
        url = 'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2/query'
        sql_params = {'plss_id': plss_id, 'sec': str(sec.lower()).strip('sec. ')}
        mask = ("PLSSID='{plss_id}'"
                " AND FRSTDIVNO='{sec}'"
                " AND FRSTDIVTYP='SN'")
        params = {k: v[:] for k, v in self.defaults.iteritems()}
        params.update({
            'where': mask.format(**sql_params),
            'outFields': 'FRSTDIVNO',
            'returnGeometry': 'true'
        })
        response = requests.get(url, params=params)
        boxes = []
        if response.status_code == 200:
            result = response.json()
            features = result.get('features', [])
            for feature in features:
                polygons = feature.get('geometry', {}).get('rings', [])
                for polygon in polygons:
                    boxes.append(Box(*polygon))
                    break
        return boxes




class PLSS(object):

    def __init__(self):
        # Define patterns used to identify and parse PLSS patterns
        bad_prefixes = '((loc)|(hole)|(hwy)|(quads?:?)|(us)|#)'
        centers = '(cen\.?(ter)?)'
        corners = '(([NS][EW] *((1?/4)|(cor\.?(ner)?))?( of)?)(?![c0-9]))'
        halves = '([NSEW] *((1?/[23])|half))'
        townships = '(((T(ownship)?\.? *)?[0-9]{1,3} *[NS])(?![NSEW]))'
        ranges = '(((R(ange)?\.? *)?[0-9]{1,3} *[EW])(?![NSEW]))'
        sections = ('((?<!/)(((((s(ection)?)|(se?ct?s?))\.? *)'
                    '|\\b)[0-9]{1,3})(?!(-\d+[^NEWS]|\.\d)))')
        # Define quarter section
        qtr = ('\\b((((N|S|E|W|NE|SE|SW|NW)[, \-]*)'
               '((cor\.?|corner|half|(1?/[234]))[, /\-]*(of *)?)?)+)\\b')
        qtr_sections = ('((|[0-9]+){0}|{0}(?:(sec|[0-9]+[, /\-]'
                        '|T[0-9]|R[0-9])))').format(qtr)
        # Create full string baed on patterns
        pattern = [
            bad_prefixes,
            centers,
            corners,
            halves,
            townships,
            ranges,
            sections
            ]
        full = ('\\b((' + '|'.join(['(' + s + '[,;: /\.\-]*' + ')'for s in pattern]) + ')+)\\b')
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
            twp = self._format_township(match)
            rng = self._format_range(match)
            sec = self._format_section(match)
            qtr = self._format_quarter_section(match)
            return twp, rng, sec, qtr


    def _format_township(self, match):
        sre_match = self.townships.search(match)
        if sre_match is not None:
            match = sre_match.group(0)
            twp = u'T' + match.strip('., ').upper().lstrip('TOWNSHIP. ')
            return twp
        raise ValueError('Township error: {}'.format(match))


    def _format_range(self, match):
        sre_match = self.ranges.search(match)
        if sre_match is not None:
            match = sre_match.group(0)
            rng = u'R' + match.strip('., ').upper().lstrip('RANGE. ')
            return rng
        raise ValueError('Township error: {}'.format(match))


    def _format_section(self, match):
        # Format section. This regex catches some weird stuff sometimes.
        matches = self.sections.findall(match)
        if matches:
            sec = sorted([val[0] for val in matches], key=len, reverse=True)[0]
            sec = u'Sec. ' + sec.strip('., ').upper().lstrip('SECTION. ')
            return sec
        raise ValueError('Section error: {}'.format(match))


    def _format_quarter_section(self, match):
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
                          .replace(' ', '')
                          .replace(',', '')
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
                          .replace('.', ''))
                # Check for illegal characters
                if not qtr.strip('NEWS23'):
                    return qtr
            raise ValueError('Quarter section error: {}'.format(match))
        return ''




class TRS(object):
    plss = PLSS()
    bot = PLSSBot()

    def __init__(self, verbatim, state):
        if len(state) != 2 or not state.isupper():
            raise ValueError('State must be a two-letter abbreviation')
        self.verbatim = verbatim
        self.state = state
        self.twp, self.rng, self.sec, self.qtr = self.plss.parse(verbatim)


    def __str__(self):
        return u' '.join([self.twp, self.rng, self.sec, self.qtr]).strip()


    def find(self):
        plss_id = self.bot.find_township(self.state, self.twp, self.rng)
        boxes = []
        for box in self.bot.find_section(plss_id, self.sec):
            for div in [self.qtr[i:i + 2] for i in range(0, len(self.qtr), 2)]:
                box = box.subsection(div)
            # Round lat/long to three decimal places
            box
            boxes.append(box)
        return boxes


    def describe(self, boxes=None):
        mask = ('Polygon determined based on PLSS locality string "{}" for'
                ' state={} using BLM webservices available at'
                ' https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer')
        if boxes and len(boxes) > 1:
            mask += '. Multiple coordinates matched this string.'
        if self.qtr:
            mask += ('. Result was refined to the given quarter section(s)'
                     ' using a custom Python script.')
        return mask.format(self.verbatim, self.state)
