"""Defines methods to match EMu records to GeoNames"""

import logging
logger = logging.getLogger(__name__)

import itertools
import re
from collections import namedtuple

import yaml

from .bot import distance_on_unit_sphere
from .sitelist import SiteList
from ...helpers import oxford_comma




Match = namedtuple('Match', ['record', 'filters', 'radius'])


class Matcher(object):


    def __init__(self, site):
        # Map useful attributes from the site object
        self.site = site
        self.bot = site.bot
        self.config = site.config
        self.codes = site.codes
        self.std = site.std
        #
        self.matches = []
        self.count = 0
        self.latitude = None
        self.longitude = None
        self.radius = None
        self.threshold = -1
        self.most_specific = False
        # Track terms checked and matched
        self.terms = []
        self.matched = []
        self.num_digits = 2


    @staticmethod
    def read_filters(match):
        """Parses the filters from a Match tuple"""
        admin = [
            ('admin_code_2', 'county'),
            ('county', 'county'),
            ('admin_code_1', 'state/province'),
            ('country_code', 'country'),
            ('country', 'country')
        ]
        features = [
            'mine',
            'island',
            'locality',
            'municipality',
            'features',
            'water_body',
            'county',
            'state_provicne',
            'country'
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
        for feature in features:
            if filters.pop(feature, -1) > 0:
                feature = feature.rstrip('s')
                break
        # Get info about matched and missed fields. Raises an error if the
        # filters dict is not consumed.
        matched = []
        blanks = []
        for key, val in admin:
            score = filters.pop(key, None)
            if score is not None:
                if score > 0:
                    matched.append(val)
                elif not score:
                    blanks.append(val)
                else:
                    raise ValueError('Score < 0: {}'.format(key))
        if filters:
            raise ValueError('Unmapped terms: {}'.format(filters))
        return feature, matched, blanks


    def match(self, **kwargs):
        """Matches a collections event record against GeoNames"""
        threshold = -1   # size
        min_size = 0      # lower values = less specific
        max_size = 0      # higher valuers = more specific
        matches = []
        terms = []        # track names checked to compare against matches
        matched = []
        for field in self.config['ordered']:
            # Coerce name to list if needed
            names = getattr(self.site, field)
            if not names:
                logger.info('Rejected {} for match (empty)'.format(field))
                continue
            if not isinstance(names, list):
                names = [s.strip() for s in re.split('[,;]', names)]
            # If this is the first populated value, set the threshold
            # for size. Additional place names must be at least as
            # specific as the largest size in this class.
            fcodes = self.config['codes'][field]
            min_size = self.min_size(fcodes)
            max_size = self.max_size(fcodes)
            if threshold < 0:
                logger.info('Setting threshold to <= {} ({})'.format(max_size, field))
                threshold = max_size
            elif min_size > threshold:
                logger.info('Rejected {} for matching (less specific)'.format(field))
                continue
            # Iterate through all names stored under this attribute
            for name in [n for n in names if n]:
                terms.append(name)
                logger.info('Matching {}={}...'.format(field, name))
                stname = self.std(name).replace('-', ' ')
                stname = self.std.strip_word(name, 'near')
                # Remove field-specific words
                if field == 'island' and stname.endswith('island'):
                    stname = stname.replace('island', '').strip()
                logger.info('Standardized "{}" to "{}"'.format(name, stname))
                # Search GeoNames for matching records
                matches_ = SiteList(self.bot.search(stname, **kwargs))
                # Filter matches based on field-specifc feature codes
                matches_ = SiteList([m for m in matches_ if m.site_kind in fcodes])
                # Get admin codes for all matches
                for match in matches_:
                    match.bot = self.bot
                    match.get_admin_codes()
                # Filter matches on name
                matches_.match(name=name, site=self.site, attr=field)
                fcodes_ = []
                for match in matches_:
                    fcodes_.append(match.site_kind)
                    radius = self.codes[match.site_kind]['SizeIndex']
                    matches.append(Match(match, matches_.filters, radius))
                    matched.append(name)
                # Reset the threshold if a match is found
                if fcodes_:
                    self._check_fcodes(fcodes_)
                    max_size = self.max_size(fcodes_)
                    if max_size < threshold:
                        logger.info('Updating threshold to <= {}'.format(max_size))
                        threshold = max_size
            # This break prevents matching on admin divisions if info in one
            # of the generic feature fields is populated but not matched
            break
        # Save information about the matching process
        self.matches = matches
        self.orig = matches[:]
        self.threshold = threshold
        self.terms = sorted(list(set(terms)))
        self.matched = sorted(list(set(matched)))
        if len(matches) == 1:
            self.latitude = matches[0].record.latitude
            self.longitude = matches[0].record.longitude
            self.radius = self.codes[matches[0].record.site_kind]['SizeIndex']
        elif len(matches) > 1:
            self.encompass()
        else:
            raise ValueError('No match found')
        return self


    def reset(self, reset_all=False):
        """Resets the match object to the most recent result"""
        self.matches = self.orig
        self.group_by_term()
        if reset_all:
            raise ValueError
        return self


    def _check_fcodes(self, fcodes):
        """Verifies that all featureCodes have been mapped to a size"""
        for fcode in fcodes:
            if not self.codes[fcode]['SizeIndex']:
                logger.error('Unmapped featureCode: {}'.format(fcode))



    def min_size(self, fcodes):
        """Returns the smallest radius for a set of feature codes"""
        key ='SizeIndex'
        return min([self.codes[c][key] for c in fcodes if self.codes[c][key]])


    def max_size(self, fcodes):
        """Returns the largest radius for a set of feature codes"""
        key ='SizeIndex'
        return max([self.codes[c][key] for c in fcodes if self.codes[c][key]])


    def encompass(self, max_distance_km=100):
        """Calculates center/radius of a circle encompassing multiple sites"""
        self.high_grade()
        for matches, distance in self.get_distances():
            if distance <= max_distance_km:
                # Calculate central location
                lats = [float(m.record.latitude) for m in matches]
                lngs = [float(m.record.longitude) for m in matches]
                midpoint, self.radius = self.get_midpoint(lngs, lats)
                self.longitude, self.latitude = midpoint
                return matches
        else:
            raise ValueError('Could not encompass all sites'
                             ' ({} km radius)'.format(max_distance_km))


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
            min_sizes.append(self.min_size(fcodes))
            max_sizes.append(self.max_size(fcodes))
        matches = []
        for i, group in enumerate(zip(items, min_sizes, max_sizes)):
            item, min_size, max_size = group
            if min_size <= min(max_sizes):
                matches.extend(item[-1])
            else:
                print('Discarded matches on {}'.format(item[0]))
        if len(matches) != len(self.matches):
            self.matches = matches
            self.group_by_term()
        return self.matches


    def group_by_term(self, matches=None):
        """Groups matches by the term they matched on"""
        if matches is None:
            matches = self.matches
        grouped = {}
        for match in matches:
            for crit in match.filters:
                for key, term in crit.items():
                    if key == '_name':
                        grouped.setdefault(term, []).append(match)
        if matches == self.matches:
            self.count = len(grouped)
        return grouped


    def find_combinations(self):
        """Creates combinations of sites required for distance tests"""
        groups = list(self.group_by_term().values())
        if len(groups) > 1:
            return list(itertools.product(*groups))
        return groups


    def get_distances(self):
        """Calculates the max distance between groups of sites"""
        distances = []
        for sites in self.find_combinations():
            dists = []
            for i, refsite in enumerate(sites):
                s1 = refsite.record
                for site in sites[i + 1:]:
                    s2 = site.record
                    dists.append(distance_on_unit_sphere(s1.latitude,
                                                         s1.longitude,
                                                         s2.latitude,
                                                         s2.longitude))
            if dists:
                distances.append([sites, max(dists)])
        distances.sort(key=lambda d: d[1])
        # Log calculation for comparison to centroid determination later
        simplified = []
        for i, distance in enumerate(distances):
            nums = [m.record.site_num for m in distance[0]]
            simplified.append('{}. {} {} km'.format(i + 1, nums, distance[1]))
        simplified = '\n'.join(simplified)
        logger.info('Calculated distances:\n{}'.format(simplified))
        return distances


    def is_site(self):
        """Tests if a record maps specifically to a site"""
        return self.is_most_specific(is_unique=True)


    def is_most_specific(self, matches=None, is_unique=False):
        """Tests if a record is the most specific possible match"""
        if matches is None:
            matches = self.matches
        max_size = self.max_size([m.record.site_kind for m in matches])
        grouped = self.group_by_term()
        all_terms_matched = len(self.terms) == len(self.matched) == len(grouped)
        most_specific = max_size <= self.threshold
        if is_unique:
            return all_terms_matched and most_specific and len(self.terms) == 1
        return all_terms_matched and most_specific


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
        feature, matched, blanks = self.read_filters(match)
        info = {
            'name': site.summarize(),
            'criteria': oxford_comma([feature + ' name'] + matched),
            'specificity': self._describe_specificity(),
            'geometry': 'Bounding box' if site.bbox else 'Point',
            'digits': self.num_digits,
            'radius': '{} km'.format(self.radius),
            'feature': feature if feature not in ['feature', 'locality']
                               else 'featureCode={}'.format(site.site_kind)
        }
        mask = ('Matched to the GeoNames record for {name} based on {criteria}'
                ' using the situate.py script. {specificity}{geometry}'
                ' coordinates were rounded to {digits} decimal places from'
                ' the values given by GeoNames. An arbitrary error radius of'
                ' {radius} was assigned to all {feature} records matched'
                ' using the script.')
        return mask.format(**info)


    def describe_one_name(self):
        """Describes how match based on repeats of one name was determined"""
        sites = [m.record for m in self.matches]
        combined = self.combine_sites(*self.matches)
        count = len(self.matches)
        info = {
            'name': combined.summarize('{name}{higher_loc}'),
            'urls': oxford_comma(sorted([s.summarize('{url}') for s in sites])),
            'count': 'both' if count == 2 else 'all {}'.format(count)
        }
        mask = ('Multiple records from GeoNames matched the locality {name},'
                ' including {urls}. The situate.py script was unable to'
                ' distinguish between these localities, and the coordinates'
                ' and error radius given here describe a circle encompassing'
                ' {count} localities.')
        return mask.format(**info)


    def describe_multiple_names(self):
        """Describes how match based on multiple sites were determined"""
        # Get names with counts
        names_with_counts = []
        for group in self.group_by_term().values():
            combined = self.combine_sites(*group)
            name = combined.summarize(mask='{name}{higher_loc}')
            names_with_counts.append('{} (n={})'.format(name, len(group)))
        names_with_counts = oxford_comma(names_with_counts, delim='; ')
        subset = self.encompass()
        if len(subset) == 1:
            self.radius = self.codes[subset[0].record.site_kind]['SizeIndex']
            before = self.describe_one(subset[0])
            after = ''
            specificity = self._describe_specificity()
        else:
            before = ('Multiple features of similar apparent specificity'
                      ' were matched to GeoNames records using the situate.py'
                      ' script, including {names_with_counts}.')
            after = ('The coordinates and error radius given here describe a'
                     ' circle encompassing the combination of the'
                     ' instances of {count} names with the smallest maximum'
                     ' distance between them (~{radius} km).')
            specificity = self._describe_specificity()
        info = {
            'names_with_counts': names_with_counts,
            'digits': self.num_digits,
            'radius': int(self.radius * 2),
            'feature': 'featureCode={}'.format(subset[0].record.site_kind),
            'specificity': specificity,
            'count': 'both' if self.count == 2 else 'all {}'.format(self.count)
        }
        info['before'] = before.format(**info)
        info['after'] = after.format(**info)
        mask = ('{before}{after}')
        if not after:
            input(mask.format(**info))
        return mask.format(**info)


    def _describe_specificity(self):
        """Describes how specific the match is"""
        if self.is_site():
            return ('This was the most specific match possible based on'
                    ' information available in this record. ')
        # Check for terms that could not be matched
        names = list(set(self.terms) - set(self.matched))
        if names:
            info = {
                'names': oxford_comma(names),
                'ano': 'Ano' if len(names) == 1 else 'O',
                'sn': '' if len(names) == 1 else 's',
                'was': 'was' if len(names) == 1 else 'were'
            }
            return ('{ano}ther place name{sn} mentioned in the EMu record ({names})'
                    ' could not be matched and {was} ignored when determining'
                    ' the coordinates given here. ').format(**info)
        # Check for terms that were excluded for non-specificity
        grouped = self.group_by_term()
        grouped_orig = self.group_by_term(self.orig)
        names = []
        for name in set(grouped_orig) - set(grouped):
            names.append(' '.join(name.split('-')).title())
        if names:
            info = {
                'names': oxford_comma(names),
                'a': 'a ' if len(names) == 1 else '',
                'ano': 'Ano' if len(names) == 1 else 'O',
                'sn': '' if len(names) == 1 else 's',
                'sv': 's' if len(names) == 1 else '',
                'was': 'was' if len(names) == 1 else 'were'
            }
            return ('{ano}ther place name{sn} mentioned in the EMu record ({names})'
                    ' appear{sv} to describe {a}larger, less specific feature{sn}'
                    ' and {was} ignored when determining coordinates given here. ').format(**info)
        # Check for sites that match multiple localities
        if len(self.terms) == len(self.matched) == len(grouped):
            return ''
        # Failure
        criteria = {
            'is_site': self.is_site(),
            'is_most_specific': self.is_most_specific(),
            'terms': self.terms,
            'matched': self.matched,
            'grouped': grouped.keys()
        }
        raise ValueError('Could not determine specificity: {}'.format(criteria))


    def combine_sites(self, *args):
        """Combines multiple sites into one site with common elements"""
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


    def get_midpoint(self, lngs, lats):
        """Gets the centroid/midpoint and radius from a list of coordiantes"""
        from shapely.geometry import Polygon
        coords = [(lng, lat) for lng, lat in zip(lngs, lats)]
        try:
            poly = Polygon(coords)
        except ValueError:
            x = sum(lngs) / len(lngs)
            y = sum(lats) / len(lats)
            x1, y1 = lngs[1], lats[1]
            x2, y2 = lngs[0], lats[0]
        else:
            centroid = poly.centroid
            bounds = poly.bounds
            x, y = centroid.x, centroid.y
            x1, y1 = x, y
            x2, y2 = bounds[:2]
        radius = distance_on_unit_sphere(y1, x1, y2, x2)
        logger.info('Calcualted circle centered at {} with radius={} km'
                    ' for {}'.format((x, y), radius, coords))
        return (x, y), radius
