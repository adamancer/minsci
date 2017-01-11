"""Analyzes and formats classifications for rocks, minerals, and meteorites"""


import json
import logging
import os
import re
import pprint as pp
from copy import copy

from unidecode import unidecode

from ..exceptions import TaxonNotFound
from ..helpers import oxford_comma, dedupe, ucfirst, lcfirst


# TODO: Integrate general migratax functions
# TODO: Integrate schema from Taxonomy module
# TODO: Add function to test/assign parent. Parent is/parent should be.

logging.basicConfig(filename='example.log', level=None)

PATH = os.path.join(os.path.dirname(__file__), 'files')
REPLACEMENTS = {
    '  ': ' ',
    ' /': '/',
    ' ?': '?',
    ' )': ')',
    '( ': '(',
    '<sup>': '',
    '</sup>': '',
    '<sub>': '',
    '</sub>': '',
    'et Al': 'et al'
}


class GeoTaxon(dict):
    """Customized container for geological taxa"""

    def __init__(self, *args, **kwargs):
        super(GeoTaxon, self).__init__(*args, **kwargs)


    def is_official(self):
        """Assesses whether a taxon is officially recognized"""
        return is_official(self)


    def pprint(self):
        """Pretty prints the taxon data"""
        pp.pprint(self)


class GeoTaxa(object):
    """Contains methods to organize and analyze geological taxa"""

    def __init__(self):
        """Read taxonomic information from JSON file"""
        self.taxa = {}
        self.tax_map = {}
        self.nar_map = {}
        self.hints = {}
        # Load exceptions to general capitalization rules
        with open(os.path.join(PATH, 'exceptions.txt'), 'rb') as f:
            exceptions = []
            for line in f.read().splitlines():
                exception = line.strip()
                if exception and not exception.startswith('#'):
                    exceptions.append(exception)
            self.exceptions = {s.lower(): s for s in exceptions
                               if not s in ('In', 'S')}
        # Read data from JSON file created from an EMu export
        fp = os.path.join(PATH, 'geotaxa.json')
        try:
            data = json.load(open(fp, 'rb'))
        except IOError:
            raise Exception('GeoTaxa source file not found. Run'
                            ' update_geotaxa to fix.')
        else:
            for key in data:
                setattr(self, key, data[key])
            # JSON strips the GeoTaxon subclass, so add it back
            for taxon, taxadict in self.taxa.iteritems():
                self.taxa[taxon] = GeoTaxon(taxadict)


    def __call__(self, taxon, classify_unknown=True):
        """Alias for self.find()"""
        return self.find(taxon, classify_unknown)


    def find(self, taxon, classify_unknown=True):
        """Returns taxonomic data for a taxon or narrative irn

        Args:
            taxon (str): a type of rock, mineral, or meteorite
            classify_unknown (bool): if True, will attempt to place
                an unrecognized taxon in the existing hierarchy

        Returns:
            Dict containing taxonomic data for the given taxon
        """
        taxadict = self.taxa.get(format_key(taxon))
        if (taxadict is None
                and classify_unknown
                and isinstance(taxon, basestring)):
            logging.info(u'Classifying unknown taxa %s', taxon)
            return self.classify_unknown_taxon(taxon)
        elif taxadict is None:
            raise TaxonNotFound
        return taxadict


    def faceted_find(self, taxon, include_synonyms=True):
        """Return preferred taxon using a faceted search

        Args:
            taxon (str): a type of rock, mineral, or meteorite
        """
        faceted = self.facet(taxon, include_synonyms)
        for term in dedupe([format_key(s) for s in faceted]):
            try:
                return self.taxa[term]
            except KeyError:
                pass
        return self.classify_unknown_taxon(taxon)


    def find_emu_taxon(self, irn):
        """Returns taxonomic data for an EMu Taxonomy irn

        For a more general function, use GeoTaxa.find().

        Args:
            irn (str): the identification number for a given taxon

        Returns:
            Dict containing taxonomic data for the taxon at the given irn
        """
        return self.tax_map.get(format_key(irn))


    def facet(self, taxon, include_synonyms=True):
        """Facet a taxon for matching"""
        endings = (u' series', u' group', u' (general term)')
        # Get different variants to consider
        preferred = self.get_preferred_name(taxon)
        official = self.get_official(taxon)
        variants = [taxon, preferred, official]
        if include_synonyms:
            synonyms = self.find(preferred)['synonyms']
            variants.extend(synonyms)
        # Add common endings for groups, series, etc.
        faceted = []
        for term in dedupe([s.lower() for s in variants]):
            term = term.lower()
            if term.endswith(endings):
                term = term.rsplit(' ', 1)[0]
            for val in (term, unidecode(term)):
                faceted.append(val)
                faceted.extend([val + ending for ending in endings])
        return dedupe(faceted)


    def get_official(self, taxon):
        """Find the most specific officially recognized taxon for a given tree

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Returns:
            The name of the closest official taxon, if found, as a string.
            If no official taxon can be found, returns the original taxon.
        """
        taxadict = self.get_preferred(taxon)
        if taxadict.is_official():
            return taxon
        else:
            for taxon in reversed(taxadict['tree']):
                if self.find(taxon).is_official():
                    return taxon
        return taxon


    def get_preferred(self, taxon):
        """Recursively searches for the preferred synonym for this taxon

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Returns:
            Dict of taxon data for preferred taxon
        """
        taxadict = self.find(taxon)
        while taxadict['preferred']:
            taxadict = self.find(taxadict['preferred'][-1])
        preferred = taxadict['name']
        if preferred.lower() == taxon.lower():
            logging.info(u'%s is the preferred term', taxon)
        else:
            logging.info(u'%s is preferred to %s', preferred, taxon)
        return taxadict


    def get_preferred_name(self, taxon):
        """Recursively searches for the preferred name for this taxon

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Returns:
            Name of preferred taxon as string
        """
        return self.get_preferred(taxon)['name']


    def cap_taxa(self, taxon, capitalize_first=True):
        """Capitalizes taxon while maintaining proper case for elements, etc.

        Args:
            taxon (str): a type of rock, mineral, or meteorite
            capitalize_first (str): if True, capitalize the first letter

        Return:
            Capitalized taxon as a string
        """
        # Reorder terms and force lower case
        taxon = taxon.lower()
        # Split into words
        temp = []
        for word in re.split(r'(\W)', taxon):
            for part in re.split('([A-z]+)', word):
                temp.append(self.exceptions.get(part, part))
        taxon = u''.join(temp)
        # Clean up formatting text found in some strings
        for key, val in REPLACEMENTS.iteritems():
            taxon = taxon.replace(key, val)
        # Clean up parentheses
        taxon += ')' * (taxon.count('(') - taxon.count(')'))
        if capitalize_first:
            taxon = ucfirst(taxon)
        if taxon == 'Xenolithic':
            taxon = 'Xenolith'
        return taxon


    def classify_unknown_taxon(self, taxon):
        """Classify unknown taxon

        Args:
            taxon (str): an unrecognized type of rock, mineral, or meteorite

        Returns:
            Taxonomic data for where the unknown taxon was placed into the
            existing hierarchy
        """
        taxon = clean_taxon(taxon)
        # Confirm the taxon does not exist
        try:
            return self.find(taxon, classify_unknown=False)
        except TaxonNotFound:
            pass
        key = format_key(taxon).split('-')
        keys = []
        if len(key) > 2:
            keys.append('-'.join([key[0], key[len(key)-1]]))
        keys.append(key[len(key)-1])
        for key in keys:
            try:
                parent = self.find(key, False)
            except TaxonNotFound:
                pass
            else:
                break
        else:
            parent = self.find('uncertain')
        key = format_key(taxon)
        return GeoTaxon({
            'irn' : None,
            'name' : self.cap_taxa(taxon),
            'parent' : parent['name'],
            'preferred': [],
            'synonyms' : [],
            'schema' : {},
            'taxa_ids' : [],
            'tree' : parent['tree'] + [parent['name']],
        })


    def clean_taxa(self, taxa, remove_dupes=False):
        """Removes repeated or child taxa while retaining order

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite
            dedupe (bool): if True, remove exact duplicates from the list

        Returns:
            List of the preferred synonyms for each taxon in the original
            list, standardized for word order and, if stipulated, deduped
        """
        cleaned = [self.get_preferred_name(clean_taxon(t)) for t in taxa if t]
        if remove_dupes:
            return dedupe(cleaned)
        return cleaned


    def item_name(self, taxa=None, setting=None, keep_group=False):
        """Format display name for a specimen based on taxa and other info

        This function is intended for single specimens. To format a
        name for multiple items, use :py:func:`~GeoTaxa.group_name()`.

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite
            setting (str): kind of object. Necklace, bowl, etc.

        Returns:
            Display name as string
        """
        if taxa is None:
            taxa = []
        # Check hints
        key = format_hint(taxa, setting)
        name = self.hints.get(key)
        if name is not None:
            return name
        # Taxa is required if name is not specified
        if not isinstance(taxa, list):
            taxa = [taxa]
        taxa = self.clean_taxa(taxa, True)
        if not any(taxa):
            name = 'Unidentified object'
            self.hints[key] = name
            return name
        taxa = self.group_related_taxa(taxa)
        highest_common = self.highest_common_taxon([taxa])
        # Special handling
        taxa = _prepend_taxon(taxa)
        taxa = _append_taxon(taxa)
        taxa = _remove_exclusive(taxa)
        # Remove parents accounted for elsewhere in the taxa list (e.g.,
        # remove corundum if sapphire also exists)
        taxadicts = [self.get_preferred(taxon) for taxon in taxa]
        taxa = _remove_parents(taxadicts)
        taxa = dedupe(taxa)
        # Special handling for jewelry
        if setting and any(taxa):
            name = self._name_jewelry(taxa, setting)
            self.hints[key] = name
            return name
        # Format each taxon in the taxa list using the taxa dict
        formatted = []
        for taxon in taxa:
            try:
                taxadict = self.find(taxon)
            except IndexError:
                continue
            if 'Minerals' in taxadict['tree']:
                name = self._name_mineral(taxadict)
            elif 'Meteorites' in taxadict['tree']:
                name = self._name_meteorite(taxadict)
            else:
                name = self._name_rock(taxadict)
            formatted.append(name)
        # Some commonly used named for minerals are actually groups
        # (e.g., pyroxene). The hierarchy stores them as such, but
        # that looks a little odd, so we strip them for display.
        if not keep_group:
            formatted = [name.rsplit(' ', 1)[0]
                         if name.lower().endswith(' group')
                         else name for name in formatted]
        # Some rock names include the primary mineral. Sometimes
        # that mineral will be listed separately as well. We typically
        # don't want to include that information twice, so we'll
        # try to remove the duplicate info here.
        primary = formatted[0].lower()
        for taxon in formatted[1:]:
            if taxon.lower() in primary:
                formatted.remove(taxon)
        # Long lists of associated taxa look terrible, so ditch everything
        # after the third taxon
        if len(formatted) > 4:
            formatted = formatted[:3]
            formatted.append('others')
        # Group varieties if everything is the same mineral
        formatted = _group_varieties(formatted, highest_common)
        # We're done! Format the list as a string.
        if len(formatted) > 1:
            name = formatted.pop(0) + ' with ' + oxford_comma(formatted, True)
        else:
            name = u''.join(formatted)
        self.hints[key] = name
        return name


    def group_name(self, *taxas):
        """Format display name for a group of specimens, as in a photo

        Essentially a wrapper for :py:func:`~GeoTaxa.highest_common_taxon()`
        at present.

        Args:
            *taxas: lists of taxa for each object in the group

        Returns:
            The name of taxon common to the group
        """
        highest_common_taxon = self.highest_common_taxon(taxas)
        if highest_common_taxon.endswith((' Group', 'Series')):
            highest_common_taxon = highest_common_taxon.rsplit(' ', 1)[0]
        return highest_common_taxon


    def group_related_taxa(self, taxa):
        """Group synonyms and varieties for a single specimen

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite

        Returns:
            List of grouped taxa
        """
        if not taxa:
            return []
        if not isinstance(taxa, list):
            taxa = [taxa]
        taxa = [clean_taxon(taxon) for taxon in taxa]
        if len(set(taxa)) == 1:
            return [self.get_preferred_name(taxa[0])]
        else:
            taxa = [self.get_preferred(taxon) for taxon in taxa]
            #names = [td['name'] for td in taxa]
            trees = [td['tree'] + [td['name']] for td in taxa]

            sets = [set(tree) for tree in trees]
            _sets = copy(sets)
            _set = sets.pop(0)
            common = _set.intersection(*_sets)
            # Group taxa
            grouped = [tree[len(common):].pop() for tree in trees
                       if len(tree[len(common):])]
            unique = list(set(grouped))
            taxa = []
            for taxon in grouped:
                if taxon in unique:
                    taxa.append(taxon)
                    unique.remove(taxon)
            return grouped


    def highest_common_taxon(self, taxas):
        """Identify the most specific common taxonomic element

        Args:
            taxas (list): lists of taxa for each object being compared

        Returns:
            Highest common taxon as string
        """
        logging.info('SEEKING HIGHEST COMMON TAXON')
        grouped = []
        for taxa in taxas:
            # Check for rocks
            if 'Rocks and Sediments' in self.find(taxa[0])['tree']:
                taxa = [taxa[0]]
            grouped.extend(self.group_related_taxa(taxa))
        # Because this function uses self.group_related_taxa, we already have the
        # preferred synonym.
        grouped = [self.find(taxon) for taxon in grouped]
        trees = [td['tree'] + [td['name']] for td in grouped]
        sets = [set(tree) for tree in trees]
        _sets = copy(sets)
        _set = sets.pop(0)
        common = _set.intersection(*_sets)
        highest_common_taxon = trees[0][len(common)-1]
        # Some taxa aren't intended for display, so we filter them out
        # using exclude.
        exclude = ['Informal group', 'Structural group', 'Ungrouped']
        while highest_common_taxon in exclude:
            highest_common_taxon = trees[0][len(common)-2]
        return highest_common_taxon


    def _name_jewelry(self, taxa, setting):
        """Formats the name of a piece of jewelry"""
        taxa = [taxon.replace(' Group', '') for taxon in taxa]
        setting = setting.lower()
        taxa_string = oxford_comma(taxa, True)
        if setting == 'carved':
            name = u'Carved {}'.format(lcfirst(taxa_string))
        else:
            name = taxa_string + ' ' + setting
        return self.cap_taxa(name)


    @staticmethod
    def _name_meteorite(taxadict):
        """Format the name of a Meteorites

        Handle unnamed meteorites. Meteorites use a short, not especially
        descriptive nomenclature, so this adds a bit of context to supplement.
        """
        name = taxadict['name']
        if 'Iron achondrite' in taxadict['tree']:
            name = u'{} (iron achondrite)'.format(name)
        elif 'Meteorites' in taxadict['tree']:
            try:
                name = u'{} ({})'.format(name, taxadict['tree'][2].lower())
            except IndexError:
                pass
        return name


    def _name_mineral(self, taxadict):
        """Format the name of a mineral

        Handle minerals and varieties. Valid mineral species will have an IMA
        status populated; a variety is anything defined below an approved mineral
        in the taxonomic hierarchy. We only keep the lowest, most specific variety
        for display.
        """
        name = taxadict['name']
        if 'Minerals' in taxadict['tree'] and not taxadict.is_official():
            for parent in taxadict['tree'][::-1]:
                parent = self.find(parent)
                if (parent.is_official()
                        and not parent['name'].endswith(' Group')):
                    variety = taxadict['name'].lower()
                    name = u'{} (var. {})'.format(parent['name'], variety)
                    break
        return name


    @staticmethod
    def _name_rock(taxadict):
        """Format the name of a rock"""
        return taxadict['name']


    def pprint(self, taxon):
        """Print basic and derived data for a taxon"""
        print 'TAXADICT:'
        self(taxon).pprint()
        print 'PREFERRED:', self.get_preferred_name(taxon)
        print 'OFFICIAL: ', self.get_official(taxon)
        print 'ITEM NAME:', self.item_name([taxon])


def format_hint(taxa, setting=None):
    """Serializes taxa and setting information as a hint"""
    keywords = taxa + [setting]
    return '|'.join([s.lower().strip() for s in keywords if s is not None])


def format_key(key):
    """Standardize formatting of keys in taxa dictionary

    Args:
        key (str): a taxon or irn

    Returns:
        Properly formatted key as string
    """
    try:
        return int(key)
    except ValueError:
        return clean_taxon(key).lower().replace(' ', '-')


def clean_taxon(taxon):
    """Reformat NMNH index taxa

    Changes taxa of the form "Gneiss, Garnet" to "Garnet Gneiss."

    Args:
        taxon (str): a type of rock, mineral, or meteorite

    Returns:
        Reformatted taxon as a string
    """
    if taxon.count(',') == 1:
        taxon = ' '.join([s.strip() for s in taxon.split(',')][::-1])
    return taxon


def is_official(taxadict):
    """Assesses whether a taxon is reconigzed by an authority

    Args:
        taxadict (GeoTaxon): taxonomic information

    Returns:
        Boolean
    """
    if 'Minerals' in taxadict['tree']:
        names = ['IMA Status', 'RRuff']
        values = ['Approved', 'Grandfathered', 'Structural Group']
    else:
        names = ['BGS-MAIN', 'BGS-TAS', 'IUGS']
        values = None
    for scheme in taxadict['schema']:
        if (scheme['scheme'] in names
                and (values is None or scheme['value'] in values)):
            return True
    return False


def _prepend_taxon(taxa):
    """Find varieties that should be prepended to previous taxon"""
    if len(taxa) > 1:
        prepend_these = ['Catseye', 'Star']
        for i, taxon in enumerate(taxa):
            if i and taxon in prepend_these:
                taxa[i-1] = u'{} {}'.format(taxon, lcfirst(taxa[i-1]))
                taxa[i] = None
    return [taxon for taxon in taxa if taxon is not None]


def _append_taxon(taxa):
    """Find varieties that should be appended to previous taxon"""
    if len(taxa) > 1:
        append_these = ['Jade', 'Moonstone', 'Sunstone']
        for i, taxon in enumerate(taxa):
            if i and taxon in append_these:
                taxa[i-1] = u'{} {}'.format(taxa[i-1], taxon.lower())
                taxa[i] = None
    return [taxon for taxon in taxa if taxon is not None]


def _remove_exclusive(taxa):
    """Removes non-preferred term of mutally exclusive pairs if both occur"""
    exclusives = [('Elbaite', 'Schorl')]
    for keep, ditch in exclusives:
        if keep in taxa and ditch in taxa:
            taxa.remove(ditch)
    return taxa


def _remove_parents(taxadicts):
    """Replace parents with most specific child"""
    taxa = [taxon['name'] for taxon in taxadicts]
    for taxadict in taxadicts:
        for parent in taxadict['tree']:
            try:
                i = taxa.index(parent)
            except ValueError:
                pass
            else:
                taxa[i] = taxadict['name']
    return taxa


def _group_varieties(taxa, highest_common):
    """Group varieties if everything is a variety of the same mineral"""
    siblings = [taxon for taxon in taxa
                if 'var.' in taxon and taxon.startswith(highest_common)]
    if len(siblings) == len(taxa) and len(taxa) > 1:
        varieties = oxford_comma([taxon.split('var.', 1).pop().strip(' )')
                                  for taxon in taxa], True)
        taxa = [highest_common + u' (vars. {})'.format(varieties)]
    return taxa
