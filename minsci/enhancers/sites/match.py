"""Defines methods to match EMu records to GeoNames"""

import logging
logger = logging.getLogger(__name__)

import itertools
import os
import re
from collections import namedtuple

import yaml
from shapely.geometry import Polygon

from .helpers import (
    Kml,
    SectionTownshipRange,
    encircle,
    get_centroid,
    get_circle,
    get_distance,
    get_point,
    is_directions,
    parse_directions
    )
from .sitelist import SiteList
from ...helpers import oxford_comma




Match = namedtuple('Match', ['record', 'filters', 'radius', 'matched'])


class Matcher(object):


    def __init__(self, site):
        # Map useful attributes from the site object
        self.site = site
        self.gl_bot = site.gl_bot
        self.gn_bot = site.gn_bot
        self.config = site.config
        self.codes = site.codes
        self.std = site.std
        # Match metadata
        self.matches = []
        self.count = 0
        self.latitude = None
        self.longitude = None
        self.distance = 0
        self.radius = None
        self.threshold = -1
        self.most_specific = False
        # Track terms checked and matched
        self.terms = []
        self.matched = []
        self.num_digits = 2
        self.explanation = ''
        self._notes = ['Coordinates and uncertainty determined using the'
                       ' situate.py script.']


    def get_names(self, names):
        if not isinstance(names, list):
            try:
                parse_directions(names)
            except ValueError:
                names = [s.strip() for s in re.split('[,;]', names)]
            else:
                names = [names]
        return [n for n in names if n.strip()]


    def match(self, force_field=None, force_codes=None, **kwargs):
        """Matches a site against GeoNames"""
        threshold = -1   # size
        min_size = 0      # lower values = less specific
        max_size = 0      # higher valuers = more specific
        matches = []
        terms = []        # track names checked to compare against matches
        matched = []
        fields = self.config['ordered']
        if force_field is not None:
            fields = [force_field]
        # Check US records for PLSS coordinates
        plss_strings = []
        if self.site.country_code == 'US' and self.site.admin_code_1:
            for field in fields:
                val = getattr(self.site, field)
                states = self.site.admin_code_1
                if not isinstance(states, list):
                    states = [states]
                for state in states:
                    try:
                        plss = SectionTownshipRange(val, state)
                    except (ValueError, TypeError):
                        pass
                    else:
                        # PLSS coordinates are highly specifc, so stop here
                        sites = plss.sites(self.site)
                        if sites:
                            match = Match(sites[-1], {},
                                          plss.get_radius(),
                                          None)
                            self.finalize_match([match], -1, [], [])
                            polygon = plss.get_coords(dec_places=None)
                            self.latitude = [c[0] for c in polygon]
                            self.longitude = [c[1] for c in polygon]
                            self.radius = match.radius
                            self.explanation = plss.describe()
                            sites[-1].directions_from = sites[:-1]
                            return self
                        else:
                            term = '"{}"'.format(plss.verbatim.strip('" '))
                            terms.append(term)
                            plss_strings.append(plss.verbatim)
        # Check for directions (10 km W of Washington)
        for field in fields:
            val = getattr(self.site, field)
            # Remove PLSS strings
            for verbatim in plss_strings:
                try:
                    val = val.replace(verbatim, '').strip()
                except AttributeError:
                    val = [s.replace(verbatim, '').strip() for s in val]
            names = [n for n in self.get_names(val) if is_directions(n)]
            for name in names:
                logger.debug('Checking for directions in "{}"'.format(name))
                try:
                    parse_directions(name)
                except ValueError:
                    pass
                else:
                    logger.debug('Matching {}={}...'.format(field, name))
                    terms.append('"{}"'.format(name.strip('" ')))
                    match = self.match_one(name, field, **kwargs)
                    matches_, matched_, max_size = match
                    matches.extend(matches_)
                    matched.extend(matched_)
                    if max_size < threshold:
                        logger.debug('Updating threshold to'
                                     ' <= {}'.format(max_size))
                        threshold = max_size
        # Create the list of features to test against
        features = set([parse_directions(m.record.locality).feature
                        for m in matches])
        # Now look for simple (ha) place names
        for field in fields:
            val = getattr(self.site, field)
            # Remove PLSS strings
            for verbatim in plss_strings:
                try:
                    val = val.replace(verbatim, '').strip()
                except AttributeError:
                    val = [s.replace(verbatim, '').strip() for s in val]
            names = [n for n in self.get_names(val) if not is_directions(n)]
            # If this is the first populated value, set the threshold
            # for size. Additional place names must be at least as
            # specific as the largest size in this class.
            fcodes = force_codes if force_codes else self.config['codes'][field]
            min_size = self.min_size(fcodes)
            max_size = self.max_size(fcodes)
            if threshold < 0:
                logger.debug('Setting threshold to <='
                             '{} ({})'.format(max_size, field))
                threshold = max_size
            elif min_size > threshold:
                logger.debug('Rejected {} for matching'
                             ' (less specific)'.format(field))
                continue
            elif terms and field in ['county',
                                     'state_province',
                                     'country',
                                     'ocean',
                                     'continent']:
                logger.debug('Rejected {} for matching (county and'
                             ' larger ignored if terms found'
                             ' elsewhere)'.format(field))
                continue
            # Reset codes to defaults if using field-based featureCodes
            if not force_codes:
                fcodes = None
            # Iterate through all names stored under this attribute
            for name in names:
                logger.debug('Matching {}={}...'.format(field, name))
                terms.append(name)
                match = self.match_one(name, field, fcodes,**kwargs)
                matches_, matched_, max_size = match
                # Discard features mentioned in directions
                modified = matches_[:]
                for feature in features:
                    modified = [m for m in modified if feature not in
                                set(m.record.site_names + m.record.synonyms)]
                if matches_ != modified:
                    terms.remove(name)
                    continue
                matches.extend(matches_)
                matched.extend(matched_)
                if max_size < threshold:
                    logger.debug('Updating threshold to <= {}'.format(max_size))
                    threshold = max_size
        self.finalize_match(matches, threshold, terms, matched)
        return self


    def assign(self, geonames_id):
        match = self.site.get_by_id(geonames_id)
        description = ('Manually matched this record to the GeoNames record'
                       ' for...')


    def match_one(self, name, field, force_codes = None, **kwargs):
        # Is this name actually directions?
        if is_directions(name):
            # Parse directions and matched the referenced feature
            parsed = parse_directions(name)
            # Set defaults for distance calculations
            parsed.defaults['min_dist_km'] = 0
            parsed.defaults['max_dist_km'] = 100
            refsite = self.site.clone({
                'country': self.site.country,
                'state_province': self.site.state_province,
                'county': self.site.county,
                'locality': parsed.feature
            })
            # Find all features matching the feature in the locality string,
            # then make the distance calculation for each. The final
            # coordinates and uncertainty will be a circle encompassing the
            # distance calculated from each site.
            codes = [
                self.filter_codes(fclass='P'),
                self.filter_codes(max_size=10)
            ]
            working = refsite.clone({}, copy_missing_fields=True)
            for attr in [None, 'county', 'state_province']:
                # Directions may indicate a point outside the political
                # geography of the reference site. If a match fails, try
                # again without county and again without state if needed.
                if attr is not None:
                    setattr(working, attr, '')
                    working.get_admin_codes()
                matcher = Matcher(site=working)
                stop = False
                for force_codes in codes:
                    try:
                        logger.debug('Matching feature parsed from directions')
                        matcher.match('locality', force_codes, **kwargs)
                    except ValueError:
                        raise
                    else:
                        stop = True
                        break
                if stop:
                    break
            else:
                msg = ('Could not find feature named in'
                       ' locality string "{}"').format(parsed)
                logger.warning(msg)
                raise ValueError(msg)
            sites = matcher.matches
            master = self.site.clone({
                'site_num': 'd{}'.format(sites[0].record.site_num),
                'site_kind': '_DIRS',
                'locality': str(parsed),
                'country': self.site.country,
                'state_province': self.site.state_province,
                'county': self.site.county,
            })
            master.get_admin_codes()
            fcodes = [master.site_kind]
            matches = []
            for match in matcher.matches:
                # Summarize site info, pulling political geopgraphy from the
                # site record being georeferenced
                try:
                    distance_km = parsed.avg_distance_km()
                except ZeroDivisionError:
                    raise ValueError('Directions do not specify a distance')
                bearing = parsed.bearing
                point = match.record.get_point(distance_km, bearing)
                fakesite = master.clone({'latitude': point.latitude,
                                         'longitude': point.longitude},
                                         copy_missing_fields=True)
                matches.append(Match(fakesite, None, point.radius, name))
            encircled = self.encircle(matches)
            master.latitude = encircled.latitude
            master.longitude = encircled.longitude
            master.directions_from = sites
            matches = SiteList([master])
            # HACK: Set the radius for the _DIRS fcode to the radius
            # calculated from by encircle()
            self.codes[master.site_kind] = {'SizeIndex': encircled.radius}
            # HACK: Set the filter manually since it's needed below but
            # there's currently no easy way to do a dummy match
            filters = [f for f in matcher.matches[0].filters
                       if list(f.keys())[0] != '_name']
            matches._filters = filters + [{'locality': 1, '_name': name}]
            msg = ('Parsed direction string "{}" as "{}" and calculated'
                   ' coordinates and uncertainty for the point at that'
                   ' distance and bearing from the GeoNames records'
                   ' matching {} (n={}).')
        else:
            stname = self.std(name).replace('-', ' ')
            stname = self.std.strip_words(name, ['area', 'near', 'nr'])
            logger.debug('Standardized "{}"'
                         ' to "{}"'.format(name, stname))
            # Search GeoNames for matching records
            matches = SiteList(self.gn_bot.search(stname, **kwargs))
            if not matches:
                stname2 = stname
                # Custom mountain search
                if stname2.startswith('mt-'):
                    stname2 = re.sub(r'\bmt\b', '', stname2)
                    stname2 = re.sub(r'\bmont\b', '', stname2)
                    stname2 = re.sub(r'\bmonte\b', '', stname2)
                    force_codes = ['HLL', 'MT', 'MTS', 'PK', 'VLC']
                # Custom island search
                if stname2.endswith('island'):
                    stname2 = stname2.replace('island', '').strip()
                    force_codes = self.config['codes']['island']
                if stname != stname2:
                    stname2 = stname2.strip('-')
                    logger.debug('Standardized "{}"'
                                 ' to "{}"'.format(name, stname2))
                    matches = SiteList(self.gn_bot.search(stname2, **kwargs))
            # Filter matches based on field-specifc feature codes
            if force_codes:
                logger.debug('Using a custom set of featureCodes'
                             ' (field={}): {}'.format(field, force_codes))
                fcodes = force_codes
            elif self.site.country:
                fcodes = self.config['codes'][field]
            else:
                fcodes = self.config['codes']['undersea']
                field = 'undersea feature'
            # Get rid of less likely codes
            matches = SiteList([m for m in matches if m.site_kind in fcodes])
            if len(matches) > 1:
                subset = matches[:]
                subset = [m for m in matches if m.site_kind !=' AIRP']
                if subset:
                    matches = SiteList(subset)
            logger.debug('{} records remain after filtering'
                         ' by featureCode'.format(len(matches)))
            if matches:
                # Get admin codes for all matches
                for match in matches:
                    match.bot = self.gn_bot
                    match.get_admin_codes()
                # Filter matches on name
                matches.match(name=name, site=self.site, attr=field)
                #self.note('Found {:,} sites matching.')
            fcodes = [m.site_kind for m in matches]
        # Format matches
        matches_ = []
        matched = []
        for match in matches:
            fcodes.append(match.site_kind)
            radius = self.codes[match.site_kind]['SizeIndex']
            matches_.append(Match(match, matches.filters(), radius, name))
            matched.append(name)
        max_size = 1e8  # arbitrarilty large value
        if fcodes:
            self._check_fcodes(fcodes)
            max_size = self.max_size(fcodes)
        return matches_, matched, max_size


    def finalize_match(self, matches, threshold, terms, matched):
        """Determines coordinates and uncertainty by comparing matches"""
        self.matches = matches
        self.orig = matches[:]
        self.threshold = threshold
        self.terms = sorted(list(set(terms)))
        self.matched = sorted(list(set(matched)))
        self.missed = sorted(list(set(terms) - set(matched)))
        if self.matches:
            self._validate()
        if len(self.matches) == 1:
            self.latitude, self.longitude = self.get_coords(matches[0])
            self.radius = self.get_radius(matches[0])
        elif len(self.matches) > 1:
            self.encompass()
        else:
            raise ValueError('No match found')
        return self


    def update_terms(self, matches=None):
        """Updates list of terms found and matched if matches removed"""
        if matches is None:
            matches = self.matches
        matched = set(self.group_by_term(matches).keys())
        for term in self.matched:
            if term not in matched:
                self.terms.remove(term)
                self.matched.remove(term)


    def encompass(self, max_distance_km=100, high_grade=True):
        """Calculates center/radius of a circle encompassing multiple sites"""
        # Checks if only one match found
        if len(self.matches) == 1:
            self.latitude, self.longitude = self.get_coords(self.matches[0])
            self.radius = self.get_radius(self.matches[0])
            return self.matches
        # That failed, so now try to encompass the matching sites
        grouped = self.group_by_term()
        logger.debug('Attempting to encompass {} names'.format(len(grouped)))
        # Find admin districts that contain the other sites
        matches = list(grouped.values())
        if len(matches) == 2 or (len(matches) == 1 and len(matches[0]) == 2):
            result = self.is_related_to(*matches)
            if result is not None:
                site, admin, contained = result
                site_name = site.record.summarize('{name}')
                admin_name = admin.record.summarize('{name}')
                related_to = 'located within' if contained else 'related to'
                if len(matches) == 1:
                    logger.debug('Sites are related')
                    mask = ('determined that the two sites that best match'
                            ' the information in this record are related'
                            ' and kept the less specific one'
                            ' (featureCode={4})')
                    matches = [admin]
                elif site.record.site_kind == '_DIRS':
                    logger.debug('Sites are parent-child')
                    mask = ('determined that this locality is {2}'
                            ' {3} (featureCode={4}), another feature mentioned'
                            ' in this record')
                    matches = [site]
                    # Update match bookkeepers since all terms accounted for
                    self.update_terms(matches)
                else:
                    logger.debug('Sites are close by')
                    mask = ('determined that {} (featureCode={}) is {}'
                            ' {} (featureCode={}), another feature mentioned'
                            ' in this record')
                    matches = [site]
                    # Update match bookkeepers since all terms accounted for
                    self.update_terms(matches)
                self.explanation = mask.format(site_name,
                                               site.record.site_kind,
                                               related_to,
                                               admin_name,
                                               admin.record.site_kind)
                self.latitude, self.longitude = self.get_coords(matches[0])
                self.radius = self.get_radius(matches[0])
                if len(matches) != len(self.matches):
                    self.matches = matches
                    self.group_by_term()
                return matches
        # Discard directions if named site is in similar location
        count = 0
        for matches, distance in self.get_distances():
            # Test if one of the matches is a direction string
            directions = [m for m in matches if m.record.site_kind == '_DIRS']
            if len(directions) == 1 and distance <= max_distance_km / 2:
                count += 1
            else:
                break
        else:
            if count:
                loc = directions[0].record.locality
                feature = 'this feature is'
                s = ''
                if count > 1:
                    feature = 'these features are'
                    s = 's'
                distance = round(distance) if distance > 1 else 1
                mask = (' determined that {} located within {} km of'
                        ' another locality mentioned in this record ({}),'
                        ' which is interpreted as approximate directions'
                        ' to the named feature{}')
                self.explanation = mask.format(feature, distance, loc, s)
                self.matches = [m for m in self.matches
                                if m not in directions]
                self.group_by_term()
        # High-grade the results. This is less specific than the contains
        # check above.If only one feature remains after high-grading, skip
        # the distance check.
        matches = self.high_grade()
        if len(matches) == 1:
            logger.debug('One site is more specific than the others')
            self.latitude, self.longitude = self.get_coords(matches[0])
            self.radius = self.get_radius(matches[0])
            return matches
        # Find sites separated by a reasonable distance
        for matches, distance in self.get_distances():
            if distance <= max_distance_km:
                self.distance = distance
                # Calculate central location
                #lats = [float(m.record.latitude) for m in matches]
                #lngs = [float(m.record.longitude) for m in matches]
                #midpoint, self.radius = self.get_midpoint(lats, lngs)
                # Check if radius is smaller than the radius for the most
                # specific feature
                #sizes = self.sizes([m.record.site_kind for m in matches])
                #try:
                #    min_size = min([s for s in sizes if s > 1])
                #except ValueError:
                #    min_size = 1
                #if self.radius <= min_size:
                #    size = min_size * 2
                #    logging.debug('Increasing radius from {}'
                #                  ' to {} km'.format(self.radius, size))
                #    self.radius = size
                #self.note('Encompassed results')
                #self.longitude, self.latitude = midpoint
                encircled = self.encircle(matches)
                self.latitude = encircled.latitude
                self.longitude = encircled.longitude
                self.radius = encircled.radius
                return matches
        # If all else fails, repeat with matches high-graded based on synonyms
        # NOTE: This block results in a significant increase in bad matches
        #if high_grade:
        #    matches = []
        #    for key, group in grouped.items():
        #        matches.extend(self.high_grade_syn(group))
        #    if len(matches) != len(self.matches):
        #        self.update_terms(matches)
        #        self.matches = matches
        #        self.count = len(self.group_by_term())
        #        return self.encompass(max_distance_km, high_grade=False)
        raise ValueError('Could not encompass all sites'
                         ' ({} km radius)'.format(max_distance_km))


    def high_grade_syn(self, matches):
        """High-grades a list of matches based on length of synonym list"""
        count = max([len(m.record.synonyms) for m in matches])
        return [m for m in matches if len(m.record.synonyms) == count]


    def high_grade(self):
        """Identifies the most specific matches if multiple names matched"""
        # Directions supersede otherwise more precise localities

        # Identify sites that matched uniquely
        grouped = self.group_by_term()
        matches = []
        min_sizes = []
        max_sizes = []
        items = list(grouped.items())
        for name, matches in items:
            fcodes = [m.record.site_kind for m in matches]
            # Do not remove directions when high grading
            #if '_DIRS' in fcodes:
            #    return self.matches
            min_sizes.append(self.min_size(fcodes))
            max_sizes.append(self.max_size(fcodes))
        matches = []
        for i, group in enumerate(zip(items, min_sizes, max_sizes)):
            item, min_size, max_size = group
            if min_size <= min(max_sizes):
                matches.extend(item[-1])
            else:
                logging.debug('Discarded matches on {}'.format(item[0]))
        if len(matches) != len(self.matches):
            self.matches = matches
            self.count = len(self.group_by_term())
        return self.matches


    def reset(self, reset_all=False):
        """Resets the match object to the most recent result"""
        self.matches = self.orig
        self.group_by_term()
        if reset_all:
            self.matches = []
            self.orig = []
            self.group_by_term()
            self.terms = []
            self.matched = []
        return self


    @staticmethod
    def read_filters(match):
        """Parses the filters from a Match tuple"""
        admin = [
            ('admin_code_2', 'district/county'),
            ('county', 'district/county'),
            ('admin_code_1', 'state/province'),
            ('country_code', 'country'),
            ('country', 'country')
        ]
        features = [
            'mine',
            'island',
            'locality',
            'municipality',
            'volcano',
            'features',
            'water_body',
            'county',
            'state_province',
            'country',
            'undersea feature'
        ]
        # Exlcude all keys starting with _
        filters = {}
        for fltr in match.filters:
            for key, val in fltr.items():
                if not key.startswith('_'):
                    filters.setdefault(key, []).append(val)
        for key, val in filters.items():
            filters[key] = val[0]
        # Find the feature name used to make the match
        for candidate in features:
            if filters.pop(candidate, -1) > 0:
                feature = candidate.rstrip('s').replace('_', '/')
                # Make county a little more descriptive
                if feature == 'county':
                    feature = 'district/county'
                break
        else:
            raise ValueError('No feature detected: {}'.format(filters))
        # Get info about matched and missed fields. Raises an error if the
        # filters dict is not consumed.
        matched = []
        blanks = []
        for key, val in admin:
            score = filters.pop(key, None)
            # Skip keys that duplicate the feature (mostly this happens with
            # county or state/province)
            if val == feature:
                continue
            if score is not None:
                if score > 0:
                    matched.append(val)
                elif not score:
                    blanks.append(val)
                else:
                    raise ValueError('Score < 0: {}'.format(key))
        if filters and not feature:
            raise ValueError('Unmapped terms: {}'.format(filters))
        return feature, matched, blanks


    def get_coords(self, match, use_point=False):
        """Gets the coordinates for the bounding box or point"""
        if not use_point and match.record.bbox:
            polygon = match.record.polygon()
            lats = [c[0] for c in polygon]
            lngs = [c[1] for c in polygon]
            return lats, lngs
        return match.record.latitude, match.record.longitude


    def get_radius(self, match):
        # Certain feature codes should calculate the radius from the bounding
        # box (countries, states, countries, etc.)
        self.radius_from_bbox = False
        codes = []
        keys = [
            'ocean',
            'continent',
            'country',
            'state_province',
            'county',
            'island'
            ]
        for key in keys:
            codes.extend(self.config['codes'][key])
        codes = [c for c in codes if not re.search(r'ADM[45]', c)]
        # Determine which radius to use
        radius_from_code = self.codes[match.record.site_kind]['SizeIndex']
        try:
            radius = match.record.get_radius(from_bounding_box=True)
        except ValueError:
            pass
        else:
            if match.record.site_kind in codes or radius > radius_from_code:
                self.radius_from_bbox = True
                return radius
        return self.codes[match.record.site_kind]['SizeIndex']


    def encircle(self, matches):
        """Calculates the centroid and encompassing radius from list of sites"""
        coords = []
        for match in matches:
            lat = match.record.latitude
            lng = match.record.longitude
            coords.extend(get_circle(lat, lng, match.radius))
        return encircle([c[0] for c in coords], [c[1] for c in coords])


    def get_midpoint(self, lats, lngs):
        """Gets the centroid/midpoint and radius from a list of coordinates"""
        coords = [(lng, lat) for lng, lat in zip(lngs, lats)]
        try:
            poly = Polygon(coords)
        except ValueError:
            # Two points
            x = sum(lngs) / len(lngs)
            y = sum(lats) / len(lats)
            x1, y1 = x, y
            x2, y2 = lngs[0], lats[0]
        else:
            centroid = poly.centroid
            bounds = poly.bounds
            x, y = centroid.x, centroid.y
            x1, y1 = x, y
            x2, y2 = bounds[:2]
        # Radius calculated between center and corner of bounding box
        radius = get_distance(y1, x1, y2, x2)
        coords = [(lat, lng) for lat, lng in zip(lats, lngs)]
        logger.debug('Calculated circle centered at {} with radius={} km'
                     ' for {}'.format((y, x), radius, coords))
        return (x, y), radius


    def get_distances(self):
        """Calculates the max distance between groups of sites"""
        distances = []
        for group in self.find_combinations():
            dists = []
            for i, refsite in enumerate(group):
                s1 = refsite.record
                for site in group[i + 1:]:
                    s2 = site.record
                    args = [float(s1.latitude), float(s1.longitude),
                            float(s2.latitude), float(s2.longitude)]
                    try:
                        dist = get_distance(*args)
                    except ValueError:
                        logger.error('Failed to calulate distance between'
                                     ' ({}, {}) and ({}, {})'.format(*args))
                        return []
                    else:
                        dists.append(dist)
            if dists:
                distances.append([group, max(dists)])
        distances.sort(key=lambda d: d[1])
        # Log calculation for comparison to centroid determination later
        if distances:
            simplified = []
            for i, distance in enumerate(distances):
                nums = [m.record.site_num for m in distance[0]]
                simplified.append('{}. {} {} km'.format(i + 1, nums, distance[1]))
            simplified = '\n'.join(simplified)
            logger.debug('Calculated distances:\n{}'.format(simplified))
        return distances


    def min_size(self, fcodes):
        """Returns the smallest radius for a set of feature codes"""
        key ='SizeIndex'
        return min([self.codes[c][key] for c in fcodes if self.codes[c][key]])


    def max_size(self, fcodes):
        """Returns the largest radius for a set of feature codes"""
        key ='SizeIndex'
        return max([self.codes[c][key] for c in fcodes if self.codes[c][key]])


    def sizes(self, fcodes):
        """Returns radii for a set of feature codes"""
        key ='SizeIndex'
        return[self.codes[c][key] for c in fcodes if self.codes[c][key]]


    def filter_codes(self, fclass=None, min_size=0, max_size=10000):
        codes = []
        for key, vals in self.codes.items():
            if (vals['SizeIndex']
                and vals.get('FeatureClass')
                and min_size <= vals['SizeIndex'] <= max_size
                and (fclass is None or vals['FeatureClass'] == fclass)):
                    codes.append(key)
        return codes



    def is_related_to(self, m1, m2=None, swap_on_failure=True):
        """Checks if any match is contained by any other match"""
        if m2 is None:
            m2 = m1[1:]
            m1 = m1[:1]
        admins = [m for m in m2
                  if m.record.site_kind.startswith('ADM') or m.record.polygon()]
        if admins:
            for site, admin in self.find_combinations([m1, admins]):
                if admin.record.contains(site.record):
                    return site, admin, True
                try:
                    lat = float(site.record.latitude)
                    lng = float(site.record.longitude)
                except ValueError:
                    pass
                else:
                    if admin.record.contains(lat=lat, lng=lng):
                        return site, admin, True
        if swap_on_failure:
            return self.is_related_to(m2, m1, False)
        # If neither site contains the other, check if they are close together
        for site, admin in self.find_combinations([m1, admins]):
            if admin.record.is_close_to(site.record):
                # Check that the sites are ordered correctly. The
                # comparison here relies on the ordering of the ADM
                # fields in GeoNames.
                if (not admin.record.site_kind.startswith('ADM')
                    or (admin.record.site_kind < site.record.site_kind)):
                        site, admin = admin, site
                return site, admin, False
        return None


    def group_by_term(self, matches=None):
        """Groups matches by the term they matched on"""
        if matches is None:
            matches = self.matches
        grouped = {}
        for match in matches:
            found = False
            for crit in match.filters:
                for key, term in crit.items():
                    if key == '_name' and not found:
                        grouped.setdefault(term, []).append(match)
                        found = True
        if matches == self.matches:
            self.count = len(grouped)
        return grouped


    def find_combinations(self, groups=None):
        """Creates combinations of sites required for distance tests"""
        if groups is None:
            groups = list(self.group_by_term().values())
        if len(groups) > 1:
            groups = list(itertools.product(*groups))
        # Remove combinations that include duplicates
        nums = [[m.record.site_num for m in g] for g in groups]
        indexes = []
        for i, grp in enumerate(nums):
            if len(grp) != len(set(grp)):
                indexes.append(i)
        for i in indexes[::-1]:
            del groups[i]
        # Log combinations
        if groups:
            simplified = []
            for i, group in enumerate(groups):
                nums = [m.record.site_num for m in group]
                simplified.append('{}. {}'.format(i + 1, nums))
            simplified = '\n'.join(simplified)
            logger.debug('Combinations of sites:\n{}'.format(simplified))
        return groups


    def is_site(self):
        """Tests if a record maps specifically to a site"""
        return self.is_most_specific(is_unique=True)


    def is_most_specific(self, matches=None, is_unique=False):
        """Tests if a record is the most specific possible match"""
        if matches is None:
            matches = self.matches
        # Check if any of the matched terms include "near"
        matched = [self.std(m) for m in self.matched]
        near = [m for m in matched
                if m != self.std.strip_words(m, ['near', 'nr'])]
        if near:
            return False
        max_size = self.max_size([m.record.site_kind for m in matches])
        grouped = self.group_by_term()
        all_terms_matched = len(self.terms) == len(self.matched) == len(grouped)
        most_specific = max_size <= self.threshold
        one_match = len(matches) == 1
        if is_unique:
            return all_terms_matched and most_specific and one_match
        return all_terms_matched and most_specific


    def combine_sites(self, *args):
        """Combines multiple sites into one site with the common elements"""
        cmb = {}
        for match in args:
            site = match.record
            for attr in site._attributes:
                val = getattr(site, attr)
                if isinstance(val, list):
                    val = tuple(val)
                cmb.setdefault(attr, []).append(val)
        # The combined dict MUST have a site name, so force the issue here
        # by assigning a common name from the three sites
        cmb = {k: v[0] if len(set(v)) == 1 else '' for k, v in cmb.items()}
        if not cmb['site_names']:
            names = []
            for match in args:
                names.extend(match.record.site_names)
            name = '/'.join(sorted(list(set(names))))
            cmb['site_names'] = [name]
        return self.site.__class__(cmb)


    def names_with_counts(self):
        """Writes a string with the count for each name matched by the script"""
        names_with_counts = []
        for key, grp in self.group_by_term().items():
            try:
                parse_directions(key)
            except ValueError:
                mask = '{name}{higher_loc}'
                mod1 = ''
                mod2 = ''
            else:
                mask = '"{name}"{higher_loc}'
                mod1 = 'the locality string '
                mod2 = ', mapped from coordinates derived from GeoNames'
            combined = self.combine_sites(*grp)
            name = combined.summarize(mask=mask)
            mask = '{}{} (n={}{})'
            names_with_counts.append(mask.format(mod1, name, len(grp), mod2))
        return oxford_comma(names_with_counts, delim='; ')


    def kml(self, measured=None):
        kml = Kml()
        # Get exact center for bounding box
        lat, lng = self.latitude, self.longitude
        if isinstance(lat + lng, list):
            lat = self.matches[0].record.latitude
            lng = self.matches[0].record.longitude
        site = self.orig[0].record.__class__({
            'latitude': lat,
            'longitude': lng
        })
        site.radius = self.radius
        # Describe how georeference was determined
        html = []
        for attr in ['latitude', 'longitude', 'radius']:
            mask = '{:.2f}' if attr != 'radius' else '{:.0f}'
            try:
                val = mask.format(getattr(site, attr))
            except ValueError:
                val = mask.format(float(getattr(site, attr)))
            if attr == 'radius':
                val += ' km'
            html.append('<strong>{}:</strong> {}'.format(attr.title(), val))
        html = '<br />'.join(html) + '<br /><br />' + self.site.html()
        kml.add_site(site,
                     style='#final',
                     name=self.site.location_id,
                     desc=self.describe() + '<br /><br />' + html)
        # Add measured coordinates if provided
        if measured is not None:
            lat, lng = measured
            site = self.orig[0].record.__class__({
                'latitude': lat,
                'longitude': lng
            })
            kml.add_site(site,
                         style='#measured',
                         name='{}, {}'.format(lat, lng),
                         desc='Measured by collector')
        # Add sites used to make the match
        for match in self.orig:
            kml.add_site(match.record, style='#candidate')
        try:
            os.mkdir('kml')
        except OSError:
            pass
        fp = os.path.join('kml', '{}.kml'.format(self.site.location_id))
        kml.save(fp)


    def describe(self):
        """Describes how the coordinates and error radius were determined"""
        if not (self.latitude and self.longitude):
            raise ValueError('No match found')
        if len(self.matches) == 1:
            description = self.describe_one()
        elif self.count == 1:
            description = self.describe_one_name()
        elif self.count > 1:
            description = self.describe_multiple_names()
        logger.info('Description: {}'.format(description))
        return description


    def describe_one(self, match=None):
        """Describes how exact match was determined"""
        if match is None:
            match = self.matches[0]
        site = match.record
        # Route directions to a different method
        if site.site_kind == '_DIRS':
            return self.describe_direction()
        feature, matched, blanks = self.read_filters(match)
        sm_feature = feature
        fm_feature = feature
        if feature in ['feature', 'locality']:
            sm_feature = site.site_kind
            fm_feature = 'featureCode={}'.format(site.site_kind)
        explanation = ''
        if self.explanation.strip():
            explanation = 'The script {}. '.format(self.explanation.strip())
        info = {
            'name': site.summarize(feature=sm_feature),
            'criteria': oxford_comma([feature + ' name'] + matched),
            'specificity': self._describe_specificity(),
            'geometry': 'Bounding box' if site.bbox else 'Point',
            'digits': self.num_digits,
            'radius': self._describe_radius(feature=fm_feature),
            'explanation': explanation,
            'synonyms': self._describe_synonyms([match])
        }
        mask = ('Matched to the GeoNames record for {name} based on {criteria}'
                ' using the situate.py script. {explanation}{specificity}'
                ' {geometry} coordinates were rounded to {digits}'
                ' decimal places from the values given by GeoNames.'
                ' {radius}{synonyms}')
        return mask.format(**info).strip().replace('  ', ' ')


    def describe_direction(self, match=None):
        """Describes how exact match was determined"""
        if match is None:
            match = self.matches[0]
        site = match.record
        feature, matched, blanks = self.read_filters(match)
        sm_feature = feature
        fm_feature = feature
        if feature in ['feature', 'locality']:
            sm_feature = site.site_kind
            fm_feature = 'featureCode={}'.format(site.site_kind)
        explanation = ''
        if self.explanation.strip():
            explanation = 'The script {}. '.format(self.explanation.strip())
        # Note if directions calculated from multiple features
        if len(site.directions_from) > 1:
            combined = self.combine_sites(*site.directions_from)
            name = combined.summarize('{name}{higher_loc}')
            mask = ('The given point was calculated based'
                    ' on {} GeoNames records matching {}. ')
            explanation += mask.format(len(site.directions_from), name)
        info = {
            'name': site.summarize('"{name}"{higher_loc}', feature=sm_feature),
            'criteria': oxford_comma([feature + ' name'] + matched),
            'specificity': self._describe_specificity(),
            'geometry': 'Bounding box' if site.bbox else 'Point',
            'digits': self.num_digits,
            #'radius': self._describe_radius(feature=fm_feature),
            'explanation': explanation,
            'synonyms': self._describe_synonyms(site.directions_from)
        }
        mask = ('Mapped coordinates and uncertainty for the locality string'
                ' {name} using the situate.py script based on coordinates'
                ' given by GeoNames. {explanation}{specificity}Point'
                ' coordinates were rounded to {digits} decimal places from'
                ' the calculated values. {synonyms}')
        return mask.format(**info).strip().replace('  ', ' ')


    def describe_one_name(self):
        """Describes how match based on repeats of one name was determined"""
        sites = [m.record for m in self.matches]
        # Split matches into sites and specific localities
        directions = [s for s in sites if s.site_kind == '_DIRS']
        if directions:
            raise ValueError('describe_one_name() includes direction')
        sites = [s for s in sites if s.site_kind != '_DIRS']
        combined = self.combine_sites(*self.matches)
        name = combined.summarize('{name}{higher_loc}')
        count = len(self.matches)
        specificity = self._describe_specificity()
        # Create the explanation of the match
        explanation = ('was unable to distinguish between these localities,'
                       ' and the coordinates and error radius given here'
                       ' describe a circle encompassing {count} localities')
        if self.explanation.strip():
            explanation += '. ' + self.explanation.strip()
            subset = self.encompass()
            name = combined.summarize('{name}{higher_loc}',
                                      feature=subset[0].record.site_kind)
        if explanation:
            explanation = 'The situate.py script {}. '.format(explanation)
        info = {
            'name': name,
            'urls': oxford_comma(sorted([s.summarize('{url}') for s in sites])),
            'count': 'both' if count == 2 else 'all {}'.format(count),
            'specificity': specificity,
            'explanation': explanation,
            'synonyms': self._describe_synonyms()
        }
        info['explanation'] = explanation.format(**info)
        mask = ('Multiple records from GeoNames matched the locality {name},'
                ' including {urls}. {explanation}{specificity}{synonyms}')
        return mask.format(**info).strip().replace('  ', ' ')


    def describe_multiple_names(self):
        """Describes how match based on multiple sites were determined"""
        # Get names with counts
        names_with_counts = self.names_with_counts()
        subset = self.encompass()
        if len(subset) == 1:
            self.radius = self.get_radius(subset[0])
            before = self.describe_one(subset[0])
            after = ''
            specificity = self._describe_specificity()
        else:
            before = ('Multiple features of similar apparent specificity'
                      ' were matched to GeoNames records using the situate.py'
                      ' script, including {names_with_counts}.'
                      ' {explanation}')
            after = ('The coordinates and uncertainty given here describe a'
                     ' circle encompassing the combination of localities'
                     ' matching {count} localities with the smallest maximum'
                     ' distance between them (~{distance} km).'
                     ' {specificity}{synonyms}')
            specificity = self._describe_specificity()
        # Round radius
        distance = '{:.1f}'.format(self.distance)
        if self.distance > 5 or self.distance == int(self.distance):
            distance = int(self.distance)
        info = {
            'names_with_counts': names_with_counts,
            'digits': self.num_digits,
            'distance': distance,
            'feature': 'featureCode={}'.format(subset[0].record.site_kind),
            'specificity': specificity,
            'count': 'both' if self.count == 2 else 'all {}'.format(self.count),
            'explanation': self.explanation.strip(),
            'synonyms': self._describe_synonyms()
        }
        info['before'] = before.format(**info)
        info['after'] = after.format(**info)
        mask = ('{before}{after}')
        return mask.format(**info).strip().replace('  ', ' ')


    def _describe_radius(self, feature=None):
        if self.radius > 5 or self.radius == int(self.radius):
            radius = '{} km'.format(int(self.radius))
        else:
            radius = '{:.1f} km'.format(self.radius)
        if self.radius_from_bbox:
            return ('The uncertainty radius represents the center-to-corner'
                    ' distance of the bounding box ({}). '.format(radius))
        return ('An arbitrary uncertainty of {} was assigned to all {}'
                ' records matched using the script. '.format(radius, feature))


    def _describe_specificity(self):
        """Describes how specific the match is"""
        if self.is_site():
            return ('This was the most specific match possible based on'
                    ' information available in this record. ')
        # Check for terms that could not be matched
        names = list(set(self.terms) - set(self.matched))
        names = ['"{}"'.format(n) if is_directions(n) else n for n in names]
        if names:
            info = {
                'names': oxford_comma([n.strip('. ') for n in names]),
                'ano': 'Ano' if len(names) == 1 else 'O',
                'sn': '' if len(names) == 1 else 's',
                'was': 'was' if len(names) == 1 else 'were'
            }
            return ('{ano}ther place name{sn} mentioned in the EMu record'
                    ' ({names}) could not be matched and {was} ignored when'
                    ' determining the coordinates given here. ').format(**info)
        # Check for terms that were excluded for non-specificity
        grouped = self.group_by_term()
        grouped_orig = self.group_by_term(self.orig)
        names = []
        for name in set(grouped_orig) - set(grouped):
            names.append(' '.join(name.split('-')).title())
        if names and not self.explanation:
            info = {
                'names': oxford_comma(names),
                'a': 'a ' if len(names) == 1 else '',
                'ano': 'Ano' if len(names) == 1 else 'O',
                'sn': '' if len(names) == 1 else 's',
                'sv': 's' if len(names) == 1 else '',
                'was': 'was' if len(names) == 1 else 'were'
            }
            return ('{ano}ther place name{sn} mentioned in the EMu record'
                    ' ({names}) appear{sv} to describe {a}larger, less specific'
                    ' feature{sn} and {was} ignored when determining'
                    ' coordinates given here. ').format(**info)
        # Check for sites that match multiple localities
        terms = set([self.std.strip_words(self.std(t), ['near', 'nr'])
                     for t in self.terms])
        matched = set([self.std.strip_words(self.std(t), ['near', 'nr'])
                       for t in self.matched])
        one_name = len(terms) == len(matched) == len(grouped) == 1
        if one_name and len(self.matches) > 1:
            return ('This was the most specific place name found'
                    ' in this record. ')
        elif one_name:
            return ('This was the most specific match possible based on'
                    ' information available in this record. ')
        elif self.explanation:
            logger.debug('No explanation of specificty made'
                         ' (matched={}, terms={})'.format(matched, terms))
            return ''
        elif len(terms) == len(matched) == len(grouped):
            logger.debug('No explanation of specificty made'
                         ' (matched={}, terms={})'.format(matched, terms))
            # The code below seems to be redundant, but keeping it just in case
            return ''
            all_both = 'Both' if len(terms) == 2 else 'All'
            return ('{} place names in the EMu record of similar apparent'
                    ' specificity were included when calculating these'
                    ' coordinates. '.format(all_both))
        # Failure
        criteria = {
            'is_site': self.is_site(),
            'is_most_specific': self.is_most_specific(),
            'terms': self.terms,
            'terms_set': terms,
            'matched': self.matched,
            'matched_set': matched,
            'grouped': grouped.keys()
        }
        raise ValueError('Could not determine specificity: {}'.format(criteria))


    def _describe_synonyms(self, matches=None):
        """Notes any synonyms used when matching feature names"""
        synonyms = []
        for match in matches if matches is not None else self.matches:
            if match.record.is_synonym_for(match.matched):
                name = match.record.summarize('{name}')
                syn = match.matched
                # Filter out instances where the name appears in the synonym
                # or vice versa
                if (self.std(name) not in self.std(syn)
                    and self.std(syn) not in self.std(name)):
                        mask = '{} is a synonym for {}'
                        synonyms.append(mask.format(syn, name))
                        logger.debug(synonyms[-1])
        if synonyms:
            return 'According to GeoNames, {}. '.format(oxford_comma(synonyms))
        return ''


    def _check_fcodes(self, fcodes):
        """Verifies that all featureCodes have been mapped to a size"""
        for fcode in fcodes:
            if not self.codes[fcode]['SizeIndex']:
                logger.error('Unmapped featureCode: {}'.format(fcode))


    def _validate(self):
        """Confirms that match is specific enough to be reasonable

        Primarily this mean not matching to very large features if other names
        mentioned in the record are outstanding. This is distinct from the
        sequencing in the match method because it can catch admin info/large
        areas that are contained in general fields like Precise Locality.
        """
        fcodes = [m.record.site_kind for m in self.matches]
        if (len(self.terms) != len(self.matched)
            and self.min_size(fcodes) >= 100):
                missed = list(set(self.terms) - set(self.matched))
                logger.warning('Match invalid (matched {},'
                               ' missed {})'.format(self.matched, missed))
                self.reset(reset_all=True)
                return False
        return True
