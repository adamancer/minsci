"""Defines methods to recognize and parse directions and bearings"""

import logging
logger = logging.getLogger(__name__)

import re

from titlecase import titlecase
from unidecode import unidecode

from ....helpers import oxford_comma
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
        self.matched = None
        self.unconsumed = None
        self.min_dist = min_dist
        self.max_dist = max_dist
        self.unit = unit
        self.bearing = bearing
        self.feature = feature
        self.kind = 'directions'


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
            'matched': self.matched,
            'unconsumed': self.unconsumed,
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
        dists = [float(d.replace(',', '')) if isinstance(d, str) else d
                 for d in [min_dist, max_dist] if d is not None]
        return sum(dists) / len(dists)


    def avg_distance_km(self):
        """Calculates the average distance in km"""
        unit = self.unit if self.unit else self.defaults['unit']
        return self.avg_distance() * self._to_km[unit]


    def _format_distance(self, dist, dec_places=2):
        """Formats distance to decimal for display"""
        # Format fraction with no coefficient
        if dist and '/' in dist and not ' ' in dist:
            dist = '0 {}'.format(dist)
        try:
            coefficient, fraction = dist.split(' ')
        except (AttributeError, ValueError):
            if dist and '.' not in dist:
                return '{:,}'.format(int(dist))
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
        if re.match(r'^\(.*?\)$', text):
            text = text[1:-1]
        ascii_text = unidecode(text)
        #mod1 = r'(?:about|approx(?:\.|imately)|around|ca\.?|collected|found|just)'
        mod1 = r'(?:(?:\W\.?){0,2})'
        mod2 = r'(?: or so)?'
        mod3 = r'(?: due )?'
        num = r'(\d+/\d+|\d*(?:\.\d+| \d/\d)?)'
        nums = r'{0}(?: ?(?:\-|or|to) ?{0})?'.format(num)
        units = '|'.join(list(self._units.keys()))
        dirs = '|'.join(list(self._bearings.keys()))
        dirs = r'(?:{0}){{1,2}}(?: ?\d* ?(?:{0}))?'.format(dirs)
        mask = r'(?:{mod1} )?(?:{nums}{mod2} ?({units}) )?{mod3}({dirs})'
        bearing = mask.format(mod1=mod1,
                              nums=nums,
                              mod2=mod2,
                              units=units,
                              mod3=mod3,
                              dirs=dirs)
        feature = r'((?:mt\.? )?[a-z \-]+?)'
        mod = r'(?: [a-z]+ (?:of|in))?'
        patterns = [
            r'{0} (?:of|from){2} {1}',
            r'{1} \({0}(?: (?:of|from){2})? *\)',
            r'{1}, {0}(?: (?:of|from){2})?',
        ]
        mask = r'^(?:{})(?=(?:$|\.| \d| (?:N|S|E|W){{1,3}}\b))'
        pattern = mask.format('|'.join(patterns).format(bearing, feature, mod))
        match = re.search(pattern, ascii_text, flags=re.I)
        # Try to extract a complete pattern from a string that contains
        # additional information
        #if match is None:
        #    mask = r'^(?:{})(?=(?:$|\.| \d| (?:N|S|E|W){{1,3}}\b))'
        #    pattern = mask.format('|'.join(patterns).format(bearing, feature))
        #    match = re.search(pattern, text, flags=re.I)
        if match is not None:
            self.matched = match.group(0).strip('. ')
            self.unconsumed = text[len(self.matched):].strip('. ')
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
        logger.debug('Successfully parsed "{}"'.format(self.verbatim))
        return self




class BetweenParser(object):

    def __init__(self, names=None):
        self.verbatim = None
        self.matched = None
        self.unconsumed = None
        self.features = None
        self.kind = 'between'


    def __str__(self):
        if self.features:
            return 'Between {}'.format(oxford_comma(self.features))
        return ''


    def __repr__(self):
        return str({
            'verbatim': self.verbatim,
            'matched': self.matched,
            'unconsumed': self.unconsumed,
            'features': self.features
        })


    def parse(self, text):
        self.verbatim = text
        # Extract between string and test feature names
        between = re.split('between', text, flags=re.I)[-1].rstrip('() ')
        delim = r'(?:\band\b|&|\+|,|;)'
        features = re.split(delim, between, flags=re.I)
        features = [s.strip() for s in features if s.strip()]
        if not features:
            raise ValueError('Could not parse "{}"'.format(text))
        # Test for bad feature names
        for feature in features:
            if any([c.isdigit() for c in feature]):
                raise ValueError('Could not parse "{}"'.format(text))
        # Identify feature
        if ' ' in features[-1] and features[-1].endswith('s'):
            name, feature = features[-1].rsplit(' ', 1)
            features[-1] = name
            endings = ('es', 's')
            for ending in endings:
                if feature.endswith(ending):
                    feature = feature[:-len(ending)]
                    features = ['{} {}'.format(n, feature) for n in features]
                    break
        self.features = features
        return self




def is_directions(val):
    """Tests if a string contains specific locality info"""
    if not val or isinstance(val, (float, int)) or len(val) < 3:
        return False
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
        r'(north|south|east|west) of',
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
    logger.debug('Checking for directions in "{}"'.format(val))
    parsed = []
    while True:
        err = None
        try:
            if 'between' in val.lower():
                parsed.append(BetweenParser().parse(val))
            else:
                parsed.append(DirectionParser().parse(val))
        except ValueError:
            if not parsed:
                raise
            break
        except AttributeError:
            # Handle lists
            parsed = []
            for val in [parse_directions(s) for s in val]:
                parsed.extend(parsed)
            return parsed
        else:
            val = parsed[-1].unconsumed
            if not is_directions(val):
                break
    return parsed
