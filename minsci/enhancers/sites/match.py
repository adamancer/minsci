"""Defines methods to match EMu records to GeoNames"""

import logging
logger = logging.getLogger(__name__)

import hashlib
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


class Hints(dict):

    def __init__(self, *args, **kwargs):
        self._dct = dict(*args, **kwargs)


    def __getitem__(self, key):
        dct = self._dct
        for key in key.split('|'):
            dct = dct[key]
        return dct


    def __setitem__(self, key, val):
        dct = self._dct
        keys = key.split('|')
        last = keys.pop(-1)
        for key in keys:
            dct = dct.setdefault(key, {})
        dct[last] = val
        return dct


    def __iter__(self):
        return iter(self._dct)


    def keyer(self, val, site, codes=None):
        codes = '' if codes is None else '-'.join(codes)
        parts = []
        for part in (val, site.country_code, site.admin_code_1, codes):
            if isinstance(part, list):
                part = '-'.join(part)
            val = site.std(part) if part else 'None'
            parts.append(hashlib.md5(bytes(val, encoding='utf-8')).hexdigest())
        return '|'.join(parts)




class Matcher(object):
    strip_words = ['area', 'near', 'nr', 'off']
    hints = Hints()


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
        self.orig = []
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
        """Splits a name string on common delimiters to get a list of names"""
        if not isinstance(names, list):
            # Remove thousands separators
            names = re.sub(r'(\d),(\d\d\d)\b', r'\1\2', names)
            # Identify distinct clauses strings joined by and
            names = re.sub(r' and (\d)', r'; \1', names)
            try:
                parse_directions(names)
            except ValueError:
                names = [s.strip() for s in re.split('[,;:|]', names)]
            else:
                names = [names]
        names = [n for n in names if n.strip()]
        return names


    def match(self, force_field=None, force_codes=None,
              finalize=True, fallback=True, **kwargs):
        """Wraps _match method to handle errors"""
        msg = 'No match found'
        try:
            self._match(force_field, force_codes, finalize, **kwargs)
        except ValueError as e:
            self.matches = []
            self.matched = []
            msg = str(e)
            logger.debug('Encountered error: {}'.format(msg))
            #raise Exception('Fatal error') from e
        if not self.matches and fallback:
            self.fallback()
        if not self.matches:
            raise ValueError(msg)
        return self


    def match_one(self, name, field, force_codes=None, **kwargs):
        """Wraps _match_one method to allow checking multiple states

        Records that list an archaic state/province may need to check multiple
        ADM1s. This requires some jiggery-pokery with the site attribute.
        """
        # Check for blanks
        if self.std(name) in ['not-stated', 'undetermined']:
            return [], [], 1e8
        # Check the hint dictionary
        try:
            return self._get_hint(name, field, force_codes=force_codes)
        except KeyError:
            pass
        # Search multiple states
        if isinstance(self.site.state_province, list):
            del kwargs['adminCode1']
            state_province = self.site.state_province[:]
            admin_codes = self.site.admin_code_1[:]
            self.site.state_province = ''
            self.site.admin_code_1 = ''
            result = self._match_one(name, field, force_codes, **kwargs)
            matches = result[0]
            # Reset state/province attributes
            self.site.state_province = state_province
            self.site.admin_code_1 = admin_codes
            if matches:
                # Limit matches to those matching one of the states
                filters = matches[0].filters
                filters.append({'admin_code_1': 1})
                matches = [m.record for m in matches
                           if m.record.admin_code_1 in admin_codes]
                # This block of code is adapted from _match_one
                fcodes = []
                matches_ = []
                matched = []
                for match in matches:
                    fcodes.append(match.site_kind)
                    radius = self.get_radius(match)
                    matches_.append(Match(match, filters, radius, name))
                    matched.append(name)
                max_size = 1e8  # arbitrarily large value
                if fcodes:
                    self._check_fcodes(fcodes)
                    max_size = self.max_size(fcodes)
                # Save result to the hints dictionary before returning it
                result = matches_, terms, matched, max_size
                hintcodes = self._get_hintcodes(name, field, force_codes)
                key = self.hints.keyer(name, self.site, hintcodes)
                self.hints[key] = result
                return result
            '''
            # Deprecated--way too many calls to the GeoNames webservice
            master = self.site
            results = []
            for i, val in enumerate(self.site.state_province):
                data = {'state_province': val}
                self.site = master.clone(data, copy_missing_fields=True)
                kwargs['adminCode1'] = self.site.admin_code_1
                result = self._match_one(*args, **kwargs)
                if result[0]:
                    results.append(result)
            self.site = master
            if len(results) == 1:
                return results[0]
            '''
            return [], [], 1e8
        return self._match_one(name, field, force_codes, **kwargs)


    def finalize_match(self, matches, threshold, terms, matched, finalize=True):
        """Determines coordinates and uncertainty by comparing matches"""
        matched = ['"{}"'.format(t) if is_directions(t) else t for t in matched]
        self.matches = self.dedupe_matches(matches)
        self.orig = matches[:]
        self.threshold = threshold
        self.terms = sorted(list(set(terms)))
        self.matched = sorted(list(set(matched)))
        self.missed = sorted(list(set(terms) - set(matched)))
        logger.debug('{:,} matches found'.format(len(self.matches)))
        if self.threshold > 0 and finalize:
            if self.matches:
                self._validate()
            if len(self.matches) == 1:
                self.latitude, self.longitude = self.get_coords(matches[0])
                self.radius = self.get_radius(matches[0])
            elif len(self.matches) > 1:
                self.encompass()
        return self


    def dedupe_matches(self, matches=None):
        """Removes duplicate matches (i.e., same value in multiple fields)"""
        if matches is None:
            matches = self.matches
        sites = [m.record for m in matches]
        return [m for i, m in enumerate(matches) if m.record not in sites[:i]]


    def update_terms(self, matches=None):
        """Updates list of terms found and matched if matches removed"""
        if matches is None:
            matches = self.matches
        matched = set(self.group_by_term(matches).keys())
        for term in self.matched[:]:
            if term not in matched:
                while term in self.terms:
                    self.terms.remove(term)
                while term in self.matched:
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
                #elif site.record.site_kind == '_DIRS':
                elif len(matches) == 2:
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
            if (len(directions) == 1
                and distance < directions[0].radius * 2
                and distance <= max_distance_km / 2):
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
                        ' another locality mentioned in this record ("{}"),'
                        ' which is interpreted as approximate directions'
                        ' to the named feature{}.')
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
                #    logger.debug('Increasing radius from {}'
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


    def fallback(self, max_distance_km=100):
        """Falls back to county or state if more specific matches fail"""
        kwargs = {
            'country': self.site.country_code,
            'adminCode1': self.site.admin_code_1
        }
        # Fall back to county or state (if state is small)
        for field in ['county', 'state_province']:
            name = getattr(self.site, field)
            terms = self.terms
            self.reset(True)
            if name:
                logger.debug('Checking fallback {}={}'.format(field, name))
                self._match(field, **kwargs)
                if len(self.matches) == 1:
                    self.radius = self.get_radius(self.matches[0])
                    if self.radius <= max_distance_km:
                        coords = self.get_coords(self.matches[0])
                        self.latitude, self.longitude = coords
                        self.terms.extend(terms)
                        return self.matches
            self.reset(True)
            self.terms = terms


    def high_grade_syn(self, matches):
        """High-grades a list of matches based on length of synonym list"""
        count = max([len(m.record.synonyms) for m in matches])
        return [m for m in matches if len(m.record.synonyms) == count]


    def high_grade(self):
        """Identifies the most specific matches if multiple names matched"""
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
                logger.debug('Discarded matches on {}'.format(item[0]))
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


    def _match(self, force_field=None, force_codes=None,
               finalize=True, **kwargs):
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
        logger.debug('Checking for PLSS strings')
        plss_strings = []
        if self.site.country_code == 'US' and self.site.admin_code_1:
            for field in fields:
                continue
                field = field.rstrip('0123456789')
                val = getattr(self.site, field)
                states = self.site.admin_code_1
                if not isinstance(states, list):
                    states = [states]
                for state in states:
                    try:
                        plss = SectionTownshipRange(val, state)
                    except (ValueError, TypeError) as e:
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
        logger.debug('Checking directions')
        for field in fields:
            field = field.rstrip('0123456789')
            val = getattr(self.site, field)
            # Remove PLSS strings
            for verbatim in plss_strings:
                try:
                    val = val.replace(verbatim, '').strip()
                except AttributeError:
                    val = [s.replace(verbatim, '').strip() for s in val]
            names = [n for n in self.get_names(val)
                     if self._is_directions(n, field)]
            for name in names:
                logger.debug('Checking for directions in "{}"'.format(name))
                # Update terms regardless of whether the value can be parsed
                # as a direction
                terms.append('"{}"'.format(name.strip('" ')))
                try:
                    parse_directions(name)
                except ValueError:
                    logger.debug('Could not parse directions')
                else:
                    logger.debug('Matching direction in'
                                 ' {}={}...'.format(field, name))
                    match = self.match_one(name, field, **kwargs)
                    matches_, terms_, matched_, max_size = match
                    terms.extend(terms_)
                    matches.extend(matches_)
                    matched.extend(matched_)
                    if max_size < threshold:
                        logger.debug('Updating threshold to'
                                     ' <= {}'.format(max_size))
                        threshold = max_size
        # Create the list of features to test against
        features = []
        for match in matches:
            try:
                for parsed in parse_directions(match.record.locality):
                    try:
                        features.append(parsed.feature)
                    except AttributeError:
                        features.extend(parsed.features)
            except ValueError as e:
                # This error occurs if a direction check has yielded a list
                # of sites instead of a parsed direction (for example, if
                # only site X in "Between X and Y" could be found).
                pass
        features = set(features)
        # Now look for simple (ha) place names
        logger.debug('Checking place names')
        for field in fields:
            field = field.rstrip('0123456789')
            val = getattr(self.site, field)
            # Remove PLSS strings
            for verbatim in plss_strings:
                try:
                    val = val.replace(verbatim, '').strip()
                except AttributeError:
                    val = [s.replace(verbatim, '').strip() for s in val]
            names = [n for n in self.get_names(val)
                     if not self._is_directions(n, field)]
            #names = [n for n in self.get_names(val)
            #         if not '"{}"'.format(n) in terms]
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
            elif terms and field in [#'county',
                                     'state_province',
                                     'country',
                                     'ocean',
                                     'continent']:
                logger.debug('Rejected {} for matching (admin divisions'
                             ' and oceans ignored if terms found'
                             ' elsewhere)'.format(field))
                continue
            # Reset codes to defaults if using field-based featureCodes
            if not force_codes:
                fcodes = None
            # Iterate through all names stored under this attribute
            for name in names:
                # Filter values that match country
                if (field != 'country'
                    and self.std(name) == self.std(self.site.country)):
                        continue
                logger.debug('Matching {}={}...'.format(field, name))
                terms.append(name)
                match = self.match_one(name, field, fcodes,**kwargs)
                matches_, terms_, matched_, max_size = match
                # Discard features mentioned in directions
                modified = matches_[:]
                for feature in features:
                    modified = [m for m in modified if feature not in
                                set(m.record.site_names + m.record.synonyms)]
                if matches_ != modified:
                    terms.remove(name)
                    continue
                terms.extend(terms)
                matches.extend(matches_)
                matched.extend(matched_)
                if max_size < threshold:
                    logger.debug('Updating threshold to <= {}'.format(max_size))
                    threshold = max_size
        self.finalize_match(matches, threshold, terms, matched, finalize)
        return self


    def _match_one(self, name, field, force_codes=None, **kwargs):
        """Matches one name-field pair"""
        try:
            return self._get_hint(name, field, force_codes=force_codes)
        except KeyError:
            pass
        terms = []
        matched = []
        # Is this name actually a direction string?
        if self._is_directions(name, field):
            matches = None
            fcodes = []
            # Parse directions and matched the referenced feature
            for parsed in parse_directions(name):
                if parsed.kind == 'directions':
                    result = self._match_directions(parsed, **kwargs)
                elif parsed.kind == 'between':
                    result = self._match_between(parsed, **kwargs)
                else:
                    raise ValueError('Unknown parser: {}'.format(parsed.kind))
                if result[0] and matches is None:
                    matches = result[0]
                elif result[0]:
                    matches.extend(result[0])
                else:
                    terms.append('"{}"'.format(parsed.matched))
                terms.extend(result[1])
                matched.extend(result[2])
                fcodes.extend(result[3])
        else:
            stname = self.std(name)
            stname = self.std.strip_words(stname, self.strip_words)
            logger.debug('Standardized "{}"'
                         ' to "{}"'.format(name, stname))
            # Search GeoNames for matching records
            logger.debug('Searching GeoNames for {}'.format(stname))
            matches = self.gn_bot.search(stname, **kwargs)
            if not matches:
                # Remove parentheicals
                stname2 = self.std(name).replace('-', ' ')
                stname2 = self.std.strip_words(stname2, self.strip_words)
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
                if stname != stname2 or field == 'water_body':
                    stname2 = stname2.strip('-')
                    logger.debug('Standardized "{}"'
                                 ' to "{}"'.format(name, stname2))
                    logger.debug('Searching GeoNames for {}'.format(stname2))
                    # Oceans and seas do not specify a country
                    if field != 'water_body':
                        matches = self.gn_bot.search(stname2, **kwargs)
                    else:
                        matches = self.gn_bot.search(stname2)
                    stname = stname2
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
            matches = SiteList(matches)
            matches = SiteList([m for m in matches if m.site_kind in fcodes])
            if len(matches) > 1:
                subset = matches[:]
                # HACK: Script is way too aggressive about matching airports
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
                matches.match(name=stname, site=self.site, attr=field)
                #self.note('Found {:,} sites matching.')
            fcodes = [m.site_kind for m in matches]
        # Format matches
        matches_ = []
        for match in matches:
            try:
                fcodes.append(match.site_kind)
            except AttributeError:
                pass
            else:
                radius = self.get_radius(match)
                matches_.append(Match(match, matches.filters(), radius, name))
                if not name.startswith('feature in'):
                    matched.append(name)
        max_size = 1e8  # arbitrarily large value
        if fcodes:
            self._check_fcodes(fcodes)
            max_size = self.max_size(fcodes)
        # Save result to the hints dictionary before returning it
        result = matches_, terms, matched, max_size
        hintcodes = self._get_hintcodes(name, field, force_codes=force_codes)
        self.hints[self.hints.keyer(name, self.site, hintcodes)] = result
        return result


    def _match_directions(self, parsed, **kwargs):
        """Matches a distance along a bearing from a place name"""
        name = str(parsed)
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
            # FIXME: I don't think this works the way it's supposed to--the
            # kwargs are inherited from the outer scope.
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
                    pass
                else:
                    stop = True
                    break
            if stop:
                break
        else:
            return [], [], [], []
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
        return matches, [], [], fcodes


    def _match_between(self, parsed, **kwargs):
        """Matches direction strings like 'Between X and Y'"""
        # Find all features matching the locality string. Only proceed if
        # all features can be matched.
        codes = [
            self.filter_codes(fclass='P'),
            self.filter_codes(max_size=10)
        ]
        # Process features one at a time since all need to match but they
        # don't need to have the same feature code
        matches = []
        terms = []
        matched = []
        found = 0
        for feature in parsed.features:
            terms.append(feature)
            refsite = self.site.clone({
                'country': self.site.country,
                'state_province': self.site.state_province,
                'county': self.site.county,
                'locality': feature
            })
            working = refsite.clone({}, copy_missing_fields=True)
            matcher = Matcher(site=working)
            for force_codes in codes:
                try:
                    logger.debug('Matching feature parsed from directions')
                    matcher.match('locality',
                                  force_codes,
                                  finalize=False,
                                  fallback=False,
                                  **kwargs)
                except ValueError as e:
                    pass
                else:
                    matches.extend(matcher.matches)
                    matched.append(feature)
                    matcher.threshold = 1e8
                    break
        # Check if all features are accounted for
        if not matched:
            msg = ('Could not find any features named in'
                   ' locality string "{}"').format(feature, parsed)
            raise ValueError(msg)
        # Construct a new matcher object from the list of matches
        if terms == matched:
            master = self.site.clone({
                'site_num': 'multiple',
                'site_kind': '_DIRS',
                'locality': str(parsed),
                'country': self.site.country,
                'state_province': self.site.state_province,
                'county': self.site.county,
            })
            master.get_admin_codes()
            matcher = Matcher(site=master)
            matcher.matches = matches
            matcher.terms = matcher.matched = [parsed.verbatim]
            matcher.encompass()
            fcodes = [master.site_kind]
            master.latitude = matcher.latitude
            master.longitude = matcher.longitude
            master.directions_from = matches
            matches = SiteList([master])
            # HACK: Set the radius for the _DIRS fcode to the radius calculated
            # from by encompass(). Adjust the radius based on whether all
            # parsed all features were found.
            radius = matcher.radius
            if len(terms) == len(matched):
                radius /= 2
            self.codes[master.site_kind] = {'SizeIndex': radius}
            # HACK: Set the filter manually since it's needed below but
            # there's currently no easy way to do a dummy match
            filters = [f for f in matcher.matches[0].filters
                       if list(f.keys())[0] != '_name']
            matches._filters = filters + [{'locality': 1, '_name': str(parsed)}]
        else:
            # Set up filters, etc. for partial match
            filters = [f for f in matches[0].filters
                       if list(f.keys())[0] != '_name']
            matches = SiteList([m.record for m in matches])
            name = 'feature in "{}"'.format(str(parsed))
            matches._filters = filters + [{'locality': 1, '_name': name}]
            fcodes = [m.site_kind for m in matches]
        return matches, terms, matched, fcodes





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
            'country_code',
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
                elif feature == 'country_code':
                    feature = 'country'
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


    def get_radius(self, site):
        """Calculates the radius for the given match or site"""
        # Extract the site from the record attribute of a Match object
        if hasattr(site, 'record'):
            site = site.record
        # Certain feature codes should calculate the radius from the bounding
        # box (countries, states, countries, etc.)
        self.radius_from_bbox = False
        codes = []
        keys = [
            'ocean',
            'continent',
            'country',
            'state_province',
            'island_group',
            'county',
            'island'
            ]
        for key in keys:
            codes.extend(self.config['codes'][key])
        codes = [c for c in codes if not re.search(r'ADM[45]', c)]
        # Determine which radius to use
        radius_from_code = self.codes[site.site_kind]['SizeIndex']
        try:
            radius = site.get_radius(from_bounding_box=True)
        except ValueError as e:
            pass
        else:
            if site.site_kind in codes or radius > radius_from_code:
                self.radius_from_bbox = True
                return radius
        return self.codes[site.site_kind]['SizeIndex']


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


    def is_related_to(self, m1, m2=None, swap_order=True):
        related = self.get_related(m1, m2, swap_order=swap_order)
        if len(related) > 1:
            # Check for a parent-child relationship
            parent_child = [rel for rel in related if rel[2]]
            if len(parent_child) == 1:
                return parent_child[0]
            # If all children the same, pick one--the specifics aren't important
            children = [r[0].record.location_id for r in parent_child]
            if len(set(children)) == 1:
                return parent_child[0]
            # If all the same parent, identify largest child
            parents = [r[1].record.location_id for r in parent_child]
            if len(set(parents)) == 1:
                radii = [r[0].radius for r in parent_child]
                largest = [r for r in parent_child if r[0].radius == max(radii)]
                if len(largest) == 1:
                    return largest[0]
            # Identify the smallest parent
            radii = [r[1].radius for r in parent_child]
            smallest = [r for r in parent_child if r[1].radius == min(radii)]
            if len(smallest) == 1:
                return smallest[0]
            # If all the same parent, identify largest child
            parents = [r[1].record.location_id for r in parent_child]
            if len(set(parents)) == 1:
                radii = [r[0].radius for r in parent_child]
                largest = [r for r in parent_child if r[0].radius == max(radii)]
                if len(largest) == 1:
                    return largest[0]
            # Give up
            return None
        return related[0] if len(related) == 1 else None


    def get_related(self, m1, m2=None, swap_order=True):
        """Checks if any match is contained by any other match"""
        related = []
        if m2 is None:
            m2 = m1[1:]
            m1 = m1[:1]
        for site, other in self.find_combinations([m1, m2]):
            # Contains forbidden for admin divs of same level
            if site.record.site_kind != other.record.site_kind:
                # Order sites as larger, smaller
                larger, smaller = self.order_matches(site, other)
                if larger.record.contains(smaller.record):
                    related.append([smaller, larger, True])
                    continue
                # Check if the lat-long of the smaller falls into the
                # radius/box of the larger
                try:
                    lat = float(smaller.record.latitude)
                    lng = float(smaller.record.longitude)
                except ValueError:
                    pass
                else:
                    if larger.record.contains(lat=lat, lng=lng):
                        related.append([smaller, larger, True])
        # If neither site contains the other, check if they are close together
        if not related:
            for site, other in self.find_combinations([m1, m2]):
                larger, smaller = self.order_matches(site, other)
                if larger.record.is_close_to(smaller.record):
                    related.append([smaller, larger, False])
        return related


    @staticmethod
    def order_matches(match, other):
        """Orders sites by as larger, smaller"""
        try:
            site_area = match.record.get_size().area
            other_area = other.record.get_size().area
        except TypeError:
            site_admin = match.record.site_kind.startswith('ADM')
            other_admin = other.record.site_kind.startswith('ADM')
            if site_admin and not other_admin:
                return match, other
            elif not site_admin and other_admin:
                return other, match
            elif site_admin and match.record.site_kind > other.record.site_kind:
                return other, match
            elif site_admin and match.record.site_kind < other.record.site_kind:
                return match, other
            elif match.radius < other.radius:
                return other, match
            elif match.radius > other.radius:
                return match, other
            elif other.record.polygon():
                return other, match
            else:
                return match, other
        else:
            return (match, other) if site_area > other_area else (other, match)



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
            if len(grp) != len(set(grp)) or grp in nums[:i]:
                indexes.append(i)
        for i in sorted(indexes)[::-1]:
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
                if m != self.std.strip_words(m, self.strip_words)]
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
        cmb = {k: list(v) if isinstance(v, tuple) else v
               for k, v in cmb.items()}
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
            site.radius = 0
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
            raise ValueError('No coordinates found')
        if self.threshold < 0:
            description = self.describe_custom()
        elif len(self.matches) == 1:
            description = self.describe_one()
        elif self.count == 1:
            description = self.describe_one_name()
        elif self.count > 1:
            description = self.describe_multiple_names()
        logger.info('Description: {}'.format(description))
        return description


    def describe_custom(self):
        """Describes match to a source other than GeoNames"""
        return self.explanation


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
        #names = ['"{}"'.format(n) if is_directions(n) else n for n in names]
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
        terms = set([self.std.strip_words(self.std(t), self.strip_words)
                     for t in self.terms])
        matched = set([self.std.strip_words(self.std(t), self.strip_words)
                       for t in self.matched])
        grouped = set([self.std.strip_words(self.std(t), self.strip_words)
                       for t in grouped])
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
            'grouped': self.group_by_term().keys(),
            'grouped_set': grouped
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

        Localities determined by parsing a direction string are excluded
        from this check.
        """
        fcodes = [m.record.site_kind for m in self.matches]
        if (len(self.terms) != len(self.matched)
            and self.min_size(fcodes) >= 100):
                missed = list(set(self.terms) - set(self.matched))
                missed = [t for t in missed if not 'ocean' in t.lower()]
                if missed:
                    raise ValueError('Match invalid (matched {},'
                                     ' missed {})'.format(self.matched, missed))
        return True


    def _is_directions(self, name, field):
        if field not in ['country', 'state_province', 'county']:
            return is_directions(name)
        return False


    def _get_hintcodes(self, name, field, force_codes=None):
        """Gets list of feature codes to use with hint check"""
        if self._is_directions(name, field):
            return ['DIR']
        elif force_codes:
            return force_codes
        elif self.site.country:
            return self.config['codes'][field]
        else:
            return self.config['codes']['undersea']


    def _get_hint(self, name, field, force_codes=None):
        hintcodes = self._get_hintcodes(name, field, force_codes)
        return self.hints[self.hints.keyer(name, self.site, hintcodes)]
