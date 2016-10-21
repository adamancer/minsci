"""Analyzes and formats classifications for rocks, minerals, and meteorites.
Identifies deprecated terms, official terms, preferred synonyms,
and varieities."""

import json as serialize
import os
import re
from copy import copy

from ..exceptions import TaxonNotFound
from ..helpers import oxford_comma, plural, cprint, rprint


# TODO: Integrate general migratax functions
# TODO: Integrate schema from Taxonomy module
# TODO: Add function to test/assign parent. Parent is/parent should be.


class GeoTaxa(object):

    def __init__(self, fp=None, force_format=False):
        # TODO: Fix so that the EMu function is called manually
        """Read data from EMu export file"""
        self.hints = {}
        self._fpath = os.path.join(os.path.dirname(__file__), 'files')
        if fp is None:
            fp = os.path.join(self._fpath, 'xmldata.xml')
        # Load captilization exceptions
        with open(os.path.join(self._fpath, 'exceptions.txt'), 'rb') as f:
            exceptions = [line for line in f.read().splitlines()
                          if bool(line.strip())
                          and not line.startswith('#')]
            self.exceptions = dict([(val.lower(), val)
                                    for val in exceptions
                                    if not val in ('In', 'S')])
        # Check for serialized data
        serialized = os.path.join(self._fpath, 'geotaxa.json')
        if force_format:
            try:
                os.remove(serialized)
            except OSError:
                pass
        try:
            tds = serialize.load(open(serialized, 'rb'))
        except IOError:
            self.update_taxonomy(fp, serialized)
        else:
            # Use serialized data. This is much faster.
            print u'Reading saved taxonomic data...'
            self.taxa = tds['taxa']
            self.map_narratives = tds['map_narratives']
            self.map_emu_taxa = tds['map_emu_taxa']


    def __call__(self, taxon, classify_unknown=True):
        """Shorthand for GeoTaxa.find()"""
        return self.find(taxon, classify_unknown)


    def update_taxonomy(self, source_path, json_path):
        """Writes JSON file summarizing the data in the EMu export

        Args:
            source_path (str): path to EMu export containing taxonomic data
            json_path (str): path to JSON file to which to write
        """
        print u'Updating taxonomic data...'
        self.taxa = {}
        self.map_narratives = {}  # maps taxon to narrative irn
        self.map_emu_taxa = {}    # maps taxon irn to narrative irn

        whitelist = [
            'emultimedia',
            'enarratives',
            'etaxonomy'
        ]
        fields = xmu.XMuFields(whitelist=whitelist, source_path=source_path)
        tax = XMu(source_path, fields)
        tax.geotaxa = self
        tax.fast_iter(tax.itertax)
        print u'{:,} records read'.format(len(self.taxa))

        # Map tree for each taxon
        print 'Mapping trees...'
        n = 0
        for irn in self.taxa:
            tree = self._recurse_tree(self.taxa[irn]['name'], [])
            self.taxa[irn]['tree'] = tree
            n += 1
            if not n % 1000:
                print '{:,} tress mapped!'.format(n)
        print '{:,} tress mapped!'.format(n)

        # Serialize the taxanomic dictionaries for later use
        taxadicts = {
            'taxa' : self.taxa,
            'map_narratives' : self.map_narratives,
            'map_emu_taxa' : self.map_emu_taxa,
             }
        with open(json_path, 'wb') as f:
            serialize.dump(taxadicts, f)


    def format_key(self, key):
        """Standardize formatting of keys in taxa dictionary

        Args:
            key (str): a taxon or irn

        Returns:
            Properly formatted key as string
        """
        return key.lower().replace(' ', '-')


    def find(self, taxon, classify_unknown=True):
        """Returns taxonomic data for a taxon or narrative irn

        Args:
            taxon (str): a type of rock, mineral, or meteorite
            classify_unknown (bool): if True, will attempt to place
                an unrecognized taxon in the existing hierarchy

        Returns:
            Dict containing taxonomic data for the given taxon
        """
        taxon = self.clean_taxon(taxon)
        try:
            # Taxon is given as an irn
            int(taxon)
        except ValueError:
            # Taxon is given as name
            try:
                return self.taxa[self.map_narratives[self.format_key(taxon)]]
            except KeyError:
                if classify_unknown:
                    return self.classify_taxon(taxon)
                else:
                    raise TaxonNotFound
        else:
            # Taxon given as irn
            try:
                return self.taxa[taxon]
            except KeyError:
                if classify_unknown:
                    return self.classify_taxon(taxon)
                else:
                    raise TaxonNotFound


    def find_emu_taxon(self, irn):
        """Returns taxonomic data for an EMu Taxonomy irn

        For a more general function, use GeoTaxa.find().

        Args:
            irn (str): the identification number for a given taxon

        Returns:
            Dict containing taxonomic data for the taxon at the given irn
        """
        return self.taxa[self.map_emu_taxa(irn)]


    def classify_taxon(self, taxon):
        """Classify unknown taxon

        Args:
            taxon (str): an unrecognized type of rock, mineral, or meteorite

        Returns:
            Taxonomic data for where the unknown taxon was placed into the
            existing hierarchy
        """
        taxon = self.clean_taxon(taxon)
        # Confirm tha taxon does not exist
        try:
            return self(taxon)
        except:
            pass
        key = self.format_key(taxon).split('-')
        keys = []
        if len(key) > 2:
            keys.append('-'.join([key[0], key[len(key)-1]]))
        keys.append(key[len(key)-1])
        for key in keys:
            try:
                parent = self(key, False)
            except TaxonNotFound:
                pass
            else:
                break
        else:
            parent = self('uncertain')
        key = self.format_key(taxon)
        return {
            'irn' : None,
            'name' : self.cap_taxa(taxon),
            'parent' : parent['name'],
            'synonyms' : [],
            'tags' : parent['tags'],
            'schemes' : {},
            'taxa_ids' : [],
            'tree' : parent['tree'] + [parent['name']],
            'synonyms' : []
        }


    def _recurse_tree(self, taxon, tree):
        """Trace classification hierarchy for a given taxon

        Args:
            taxon (str): a type of rock, mineral, or meteorite
            tree (list): the taxonomic hierarchy for the taxon compiled so far.
                This list is modified as the function proceeds.

        Returns:
            A list containing the taxonomic hierarchy for the given taxon
        """
        try:
            parent = self(taxon)['parent']
        except KeyboardInterrupt:
            raise
        except KeyError:
            pass
        except IndexError:
            pass
        except RuntimeError:
            raise
        else:
            if parent is not None:
                taxon = self(parent)['name']
                tree.append(taxon)
                self._recurse_tree(taxon, tree)
        return tree[::-1]


    def clean_taxon(self, taxon):
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


    def cap_taxa(self, taxon, ucfirst=True):
        """Capitalizes taxon while maintaining proper case for elements, etc.

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Return:
            Capitalized taxon as a string
        """
        # Reorder terms and force lower case
        orig = copy(taxon)
        s = taxon.lower()
        # Split into words
        p = re.compile('(\W)', re.U)
        try:
            words = re.split('(\W)', s)
        except:
            raise
        else:
            temp = []
            for word in words:
                for w in re.split('([A-z]+)', word):
                    try:
                        temp.append(self.exceptions[w])
                    except KeyError:
                        temp.append(w)
        s = ''.join(temp)
        # Clean up formatting text found in some strings
        replacements = {
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
        for key in replacements:
            while key in s:
                s = s.replace(key, replacements[key])
        while s.count('(') > s.count(')'):
            s += ')'
        if ucfirst:
            try:
                s = s[0].upper() + s[1:]
            except IndexError:
                s = s.upper()
        return s


    def get_official_taxon(self, taxon):
        """Find the most specific officially recognized taxon for a given tree

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Returns:
            The name of the closest official taxon, if found, as a string.
            If no official taxon can be found, returns the original taxon.
        """
        tdata = self(self.preferred_synonym(taxon))
        if self.is_official(tdata):
            return taxon
        else:
            for t in reversed(self(taxon)['tree']):
                if self.is_official(self(t)):
                    return t
        return taxon


    def is_official(self, tdata):
        """Check a taxon is recognized by an authority

        Args:
            tdata (dict): data about a type of rock, mineral, or meteorite

        Returns:
            Boolean. True if the given taxon is official, False if not.
        """
        authorities = {
            'BGS-MAIN': None,
            'BGS-TAS': None,
            'IMA Status': ['Approved', 'Grandfathered'],
            'IUGS': None
        }
        for key in authorities:
            try:
                status = tdata['schemes'][key]
            except KeyError:
                pass
            else:
                if (authorities[key] is None or status[0] in authorities[key]):
                    return True
        else:
            return False


    def clean_taxa(self, taxa, dedupe=False):
        """Removes repeated or child taxa while retaining order

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite
            dedupe (bool): if True, remove exact duplicates from the list

        Returns:
            List of the preferred synonyms for each taxon in the original
            list, standardized for word order and, if stipulated, deduped
        """
        taxa = [self.preferred_synonym(self.clean_taxon(taxon))
                for taxon in taxa if bool(taxon)]
        if dedupe:
            temp = []
            while len(taxa):
                taxon = taxa.pop()
                if not taxon in taxa:
                    temp.insert(0, taxon)
            taxa = temp
        return taxa


    def item_name(self, taxa=[], setting=None, name=None):
        """Format display name for a specimen based on taxa and other info

        This function is intended for single specimens. To format a
        name for multiple items, use :py:func:`~GeoTaxa.group_name()`.

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite
            setting (str): kind of object. Necklace, bowl, etc.
            name (str): proper name of object, if exists

        Returns:
            Display name as string
        """
        if bool(name):
            return name
        # Check hints
        key = '|'.join([s.lower().strip() for s
                        in taxa + [setting] if s is not None])
        try:
            return self.hints[key]
        except KeyError:
            pass
        # Taxa is required if name is not specified
        orig = copy(taxa)
        taxa = [s for s in taxa if bool(s)]
        if not any(taxa):
            name = 'Unidentified object'
            self.hints[key] = name
            return name
        if not isinstance(taxa, list):
            taxa = [taxa]
        taxa = self.clean_taxa(taxa, True)
        taxa = self.group_taxa(taxa)
        highest_common_taxon = self.highest_common_taxon(taxa)
        # Special handling
        if len(taxa) > 1:
            # FIXME: Change to module constant
            prepend = ['Catseye', 'Star']
            append = ['Jade', 'Moonstone', 'Sunstone']
            for i in xrange(len(taxa)):
                try:
                    taxon = taxa[i]
                except IndexError:
                    continue
                if taxon in prepend:
                    try:
                        taxa[i-1] = u'{} {}'.format(
                            taxon, taxa[i-1][0].lower() + taxa[i-1][1:])
                    except IndexError:
                        pass
                    else:
                        del taxa[i]
                if taxon in append:
                    try:
                        taxa[i-1] = u'{} {}'.format(taxa[i-1], taxon.lower())
                    except IndexError:
                        pass
                    else:
                        del taxa[i]
        if 'Elbaite' in taxa and 'Schorl' in taxa:
            taxa.remove('Schorl')
        # Remove parents
        taxa = [self.preferred_synonym(taxon) for taxon in taxa]
        for i in xrange(len(taxa)):
            try:
                taxon = self(taxa[i])
            except IndexError:
                continue
            for parent in taxon['tree']:
                try:
                    j = taxa.index(parent)
                except ValueError:
                    pass
                else:
                    taxa[j] = taxa[i]
        # Dedupe while maintaining list order
        taxa = [taxa[i] for i in xrange(len(taxa)) if not taxa[i] in taxa[:i]]
        # Special handling for jewelry
        if bool(setting) and any(taxa):
            taxa = [taxon.replace(' Group', '') for taxon in taxa]
            setting = setting.lower()
            taxa = oxford_comma(taxa)
            if setting == 'carved':
                formatted = 'Carved {}'.format(taxa[0].lower() + taxa[1:])
            else:
                formatted = taxa + ' ' + setting.lower()
            name = self.cap_taxa(formatted)
            self.hints[key] = name
            return self.cap_taxa(formatted)
        formatted = []
        for i in xrange(len(taxa)):
            try:
                taxon = self(taxa[i])
            except IndexError:
                continue
            name = taxon['name']
            # Handle minerals and varieties. Valid mineral species will
            # have an IMA status populated; a variety is anything defined
            # below an approved mineral in the taxonomic hierarchy. We
            # only keep the lowest, most specific variety for display.
            try:
                taxon['schemes']['IMA Status']
            except KeyError:
                for parent in taxon['tree']:
                    parent = self(parent)
                    try:
                        parent['schemes']['IMA Status']
                    except KeyError:
                        pass
                    else:
                        variety = taxon['name'][0].lower() + taxon['name'][1:]
                        name = (u'{} (var. {})'.format(parent['name'], variety))
                        break
            # Handle unnamed meteorites. Meteorites use a short,
            # not especially descriptive nomenclature, so we'll
            # add a bit of context to supplement.
            if 'Iron achondrite' in taxon['tree']:
                name = u'{} (Iron achondrite)'.format(name)
            elif 'Meteorites' in taxon['tree']:
                try:
                    name = u'{} ({})'.format(name, taxon['tree'][2].lower())
                except IndexError:
                    pass
            formatted.append(name)
        # Some commonly used named for minerals are actually groups
        # (e.g., pyroxene). The hierarchy stores them as such, but
        # that looks a little odd, so we strip them for display.
        formatted = [name.rsplit(' ', 1)[0] if name.lower().endswith('group')
                     else name for name in formatted]
        # Some rock names include the primary mineral. Sometimes
        # that mineral will be listed separately as well. We typically
        # don't want to include that information twice, so we'll
        # try to remove those here.
        try:
            primary = formatted[0].lower()
        except IndexError:
            # FIXME: Create custom exception
            print 'FATAL ERROR'
            print 'ORIGINAL:', orig
            print 'MODIFIED:', taxa
            raw_input()
            raise
        for taxon in copy(formatted[1:]):
            if taxon.lower() in primary:
                formatted.remove(taxon)
        # Long lists of associated taxa look terrible, so we'll
        # ditch everything after the third taxon.
        if len(formatted) > 4:
            formatted = formatted[:3]
            formatted.append('others')
        # Group varieties if everything is the same mineral
        siblings = [taxon for taxon in formatted
                    if 'var.' in taxon and taxon.startswith(highest_common_taxon)]
        if len(siblings) == len(taxa) and len(taxa) > 1:
            varieties = [taxon.split('var.', 1).pop().strip(' )')
                         for taxon in formatted]
            formatted = [(highest_common_taxon +
                          u' (vars. {})').format(oxford_comma(varieties))]
        # We're done! Format the list as a string.
        if len(formatted) > 1:
            primary = formatted.pop(0)
            name = primary + ' with ' + oxford_comma(formatted)
        else:
            name = ''.join(formatted)
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


    def preferred_synonym(self, taxon):
        """Recursively search for the preferred synonym for this taxon

        Args:
            taxon (str): a type of rock, mineral, or meteorite

        Returns:
            Preferred synonym as a string, if found. If not, returns the
            original taxon string.
        """
        taxon = self(taxon)
        while len(taxon['synonyms']):
            taxon = self(copy(taxon['synonyms']).pop())
        return taxon['name']


    def group_taxa(self, taxa):
        """Group synonyms and varieties for a single specimen

        Args:
            taxa (list): one or more types of rock, mineral, or meteorite

        Returns:
            List of grouped taxa
        """
        if not isinstance(taxa, list):
            taxa = [taxa]
        if not len(taxa):
            return []
        taxa = [self.clean_taxon(taxon) for taxon in taxa]
        if len(taxa) == 1:
            return [self(self.preferred_synonym(taxa[0]))['name']]
        else:
            taxa = [self.preferred_synonym(taxon) for taxon in taxa]
            trees = [self(taxon)['tree'] + [self(taxon)['name']]
                     for taxon in taxa]
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
        grouped = []
        for taxa in taxas:
            # Check for rocks
            if 'Rocks and Sediments' in self(taxa[0])['tree']:
                taxa = [taxa[0]]
            grouped.extend(self.group_taxa(taxa))
        # Because this function uses self.group_taxa, we already have the
        # preferred synonym.
        trees = [self(taxon)['tree'] + [self(taxon)['name']]
                 for taxon in grouped]
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
