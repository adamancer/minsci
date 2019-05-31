"""Defines methods to recognize and parse directions and bearings"""

import logging
logger = logging.getLogger(__name__)

import re

from titlecase import titlecase

from ....standardizer import LocStandardizer


class DirectionParser(object):
    """Parses a simple direction into its component parts"""

    def __init__(self, min_dist=None, max_dist=None, unit=None,
                 bearing=None, feature=None):
        self._units = {
            r'f(?:oo|ee)?t\b\.?': 'ft',
            r'm(?:et[er]{2})?s?\b\.?': 'm',
            r'k(?:ilo)?m(?:et[er]{2})?s?\b\.?' : 'km',
            r'mi(?:les?)?\b\.?': 'mi',
            r'y(?:ar)?ds?\b\.?': 'yd',
        }
        self._bearings = {
            r'n(?:orth)?\.?': 'N',
            r's(?:outh)?\.?': 'S',
            r'e(?:ast)?\.?': 'E',
            r'w(?:est)?\.?': 'W',
        }
        self._to_km = {
            'ft': 0.0003048,
            'km': 1,
            'm': 0.001,
            'mi': 1.609344,
            'yd': 0.0009144
        }
        # Values used for distance calculations if directions only
        # specify a bearing
        self.defaults = {
            'min_dist_km': None,
            'max_dist_km': None,
            'unit': 'km'
        }
        self.verbatim = None
        self.min_dist = min_dist
        self.max_dist = max_dist
        self.unit = unit
        self.bearing = bearing
        self.feature = feature


    def __str__(self):
        dists = [d for d in [self._min_dist, self._max_dist] if d]
        dist = '-'.join(sorted(list(set(dists))))
        if dist and self.unit and self.bearing and self.feature:
            return '{} {} {} of {}'.format(dist,
                                           self.unit,
                                           self.bearing,
                                           self.feature)
        elif not self.unit and not dist and self.bearing and self.feature:
            return '{} of {}'.format(self.bearing, self.feature)
        raise ValueError('No bearings parsed: {}'.format(repr(self)))


    def __repr__(self):
        return str({
            'verbatim': self.verbatim,
            'min_dist': self.min_dist,
            'max_dist': self.max_dist,
            'unit': self.unit,
            'bearing': self.bearing,
            'feature': self.feature
        })


    @property
    def min_dist(self):
        return self._min_dist


    @min_dist.setter
    def min_dist(self, min_dist):
        self._min_dist = self._format_distance(min_dist)


    @property
    def max_dist(self):
        return self._max_dist


    @max_dist.setter
    def max_dist(self, max_dist):
        self._max_dist = self._format_distance(max_dist)


    @property
    def unit(self):
        return self._unit


    @unit.setter
    def unit(self, unit):
        self._unit = self._format_unit(unit)


    @property
    def bearing(self):
        return self._bearing


    @bearing.setter
    def bearing(self, bearing):
        self._bearing = self._format_bearing(bearing)


    @property
    def feature(self):
        return self._feature


    @feature.setter
    def feature(self, feature):
        self._feature = self._format_feature(feature)


    def avg_distance(self):
        """Calculates the average distance"""
        unit = self.unit if self.unit else self.defaults['unit']
        min_dist = self.min_dist
        max_dist = self.max_dist
        if min_dist is None and max_dist is None:
            min_dist = self.defaults['min_dist_km'] / self._to_km[unit]
            max_dist = self.defaults['max_dist_km'] / self._to_km[unit]
        dists = [float(d) for d in [min_dist, max_dist] if d is not None]
        return sum(dists) / len(dists)


    def avg_distance_km(self):
        """Calculates the average distance in km"""
        unit = self.unit if self.unit else self.defaults['unit']
        return self.avg_distance() * self._to_km[unit]


    def _format_distance(self, dist, dec_places=2):
        """Formats distance to decimal for display"""
        try:
            coefficient, fraction = dist.split(' ')
        except (AttributeError, ValueError):
            return dist
        else:
            numerator, denominator = fraction.split('/')
            val = int(coefficient) + int(numerator) / int(denominator)
            return '{{:.{}f}}'.format(dec_places).format(val)


    def _format_unit(self, unit=None):
        """Formats unit for display"""
        if unit is None:
            try:
                unit = self.unit
            except AttributeError:
                unit = None
        if unit is not None:
            for pattern, preferred in self._units.items():
                if re.match(pattern, unit, flags=re.I):
                    return preferred
            raise KeyError('Unrecognized unit: {}'.format(unit))


    def _format_bearing(self, bearing=None):
        """Formats bearing as N, NW, NNW for display"""
        if bearing is None:
            try:
                bearing = self.bearing
            except AttributeError:
                bearing = None
        if bearing is not None:
            for word in ['north', 'south', 'east', 'west']:
                bearing = bearing.lower().replace(word, word[0])
            return re.sub('[^NSEW\d]', '', bearing.upper())


    def _format_feature(self, feature=None):
        """Formats feature name for display"""
        if feature is None:
            try:
                feature = self.feature
            except AttributeError:
                feature = None
        if feature is not None:
            feature = LocStandardizer().sitify(feature)
            if feature.isupper():
                return titlecase(feature)
            return feature


    def parse(self, text):
        """Parses a simple directional string"""
        self.verbatim = text
        mod1 = r'(?:about|approx(?:\.|imately)|around|ca\.?|collected|found|just)'
        mod2 = r'(?: or so)?'
        num = r'(\d+(?:\.\d+| \d/\d)?)'
        nums = r'{0}(?: ?(?:\-|or|to) ?{0})?'.format(num)
        units = '|'.join(list(self._units.keys()))
        dirs = '|'.join(list(self._bearings.keys()))
        dirs = r'(?:{0}){{1,2}}(?: ?\d* ?(?:{0}))?'.format(dirs)
        mask = r'(?:{mod1} )?(?:{nums}{mod2} ?({units}) )?({dirs})'
        bearing = mask.format(mod1=mod1,
                              nums=nums,
                              mod2=mod2,
                              units=units,
                              dirs=dirs)
        feature = r'((?:mt\.? )?[a-z \-]+)\.?'
        patterns = [
            r'{0} (?:of|from) {1}',
            r'{1} \({0}(?: (?:of|from))?\)',
            r'{1}, {0}(?: (?:of|from))?',
        ]
        mask = r'^(?:{})$'
        pattern = mask.format('|'.join(patterns).format(bearing, feature))
        match = re.search(pattern, text, flags=re.I)
        if match is not None:
            parts = []
            for i in range(1, 17):
                try:
                    parts.append(match.group(i))
                except IndexError:
                    break
            groups = [parts[i: i + 5] for i in range(0, 15, 5)]
            #print([(i, p) for i, p in enumerate(parts)])
            if any(groups[0]):
                self.min_dist = parts[0]
                self.max_dist = parts[1]
                self.unit = parts[2]
                self.bearing = parts[3]
                self.feature = parts[4]
            elif any(groups[1]):
                self.min_dist = parts[6]
                self.max_dist = parts[7]
                self.unit = parts[8]
                self.bearing = parts[9]
                self.feature = parts[5]
            elif any(groups[2]):
                self.min_dist = parts[11]
                self.max_dist = parts[12]
                self.unit = parts[13]
                self.bearing = parts[14]
                self.feature = parts[10]
            else:
                raise ValueError('Could not parse "{}"'.format(text))
        else:
            raise ValueError('Could not parse "{}"'.format(text))
        return self


def is_directions(val):
    """Tests if a string contains specific locality info"""
    # Classify records with directional info as specific
    blacklist = [
        # Units of distance
        'ft',
        'feet',
        'km',
        'm',
        'meters',
        'mi',
        'miles',
        # Direction info
        r'[ns]\d+[ew]',
        # Relational terms uncommon in place names
        'above',
        'at',
        'below',
        'between',
        'from',
        'in',
        'on',
        'outside',
        'to',
        'top'
    ]
    if isinstance(val, list):
        val = '; '.join(val)
    std = LocStandardizer(remove_chars=[], minlen=1, delim=' ')
    val = std(val, pre=[std.standardize_directions])
    # Check for directional info
    for match in re.findall(r'.?\b[NSEW]{1,2}\b.?', val, flags=re.I):
        if (not match.startswith(('-', "'"))
            and not match.endswith(('-', "'"))
            and not re.search(r'[EW][NS]', match, flags=re.I)):
                return True
    # Check blacklist
    for kw in blacklist:
        pattern = r'.?\b{}\b.?'.format(kw.strip())
        for match in re.findall(pattern, val):
            if (not (match.startswith(('-', "'"))
                and not match.endswith(('-', "'")))):
                    return True
    return False


def parse_directions(val):
    """Parses a simple directional string"""
    return DirectionParser().parse(val)
