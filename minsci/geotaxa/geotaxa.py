import json as serialize
import os
import re
from copy import copy

from ..exceptions import TaxonNotFound
from ..helpers import oxford_comma, plural, cprint, rprint
from ..xmu import xmu


class XMu(xmu.XMu):


    def itertax(self, element):
        """Reads taxonomic hierarchy from narratives export

        @param lxml object
        """
        self.record = element
        irn = self.find('irn')
        title = self.find('NarTitle')
        parent = self.find('AssMasterNarrativeRef', 'irn')
        synonyms = self.find('AssAssociatedWithRef_tab', 'irn')
        tags = self.find('DesSubjects_tab', 'DesSubjects')
        taxa = self.find('TaxTaxaRef_tab', 'irn')

        # Read schemes
        names = self.find('NarType_tab', 'NarType')
        ids = self.find('NarExplanation_tab', 'NarExplanation')
        schemes = {}
        for name, _id in zip(names, ids):
            try:
                schemes[name].append(_id)
            except KeyError:
                schemes[name] = [_id]

        self.taxa[irn] = {
            'irn' : irn,
            'name' : title,
            'parent' : parent,
            'synonyms' : synonyms,
            'tags' : tags,
            'schemes' : schemes,
            'taxa_ids' : taxa
        }
        key = self.format_key(title)
        self.map_narratives[key] = irn
        for taxon in taxa:
            self.map_emu_taxa[taxon] = irn
        if not len(self.taxa) % 2500:
            print u'{:,} records read'.format(len(self.taxa))



class GeoTaxa(object):


    def __init__(self, fp=None, force_format=False):
        """Read data from EMu export file"""
        self._fpath = os.path.join(os.path.dirname(__file__), 'files')
        if fp is None:
            fp = os.path.join(self._fpath, 'xmldata.xml')

        # Load captilization exceptions
        try:
            with open(os.path.join(self._fpath, 'exceptions.txt'), 'rb') as f:
                exceptions = [line for line in f.read().splitlines()
                              if bool(line.strip())
                              and not line.startswith('#')]
                self.exceptions = dict([(val.lower(), val)
                                        for val in exceptions
                                        if not val in ('In', 'S')])
        except IOError:
            raise

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
        """Returns taxonomic data when instance is called"""
        return self.find(taxon, classify_unknown)


    def update_taxonomy(self, source_path, json_path):
        """Writes JSON file based on EMu export"""
        print u'Updating taxonomic data...'
        self.taxa = {}
        self.map_narratives = {}  # maps taxon name to narrative irn
        self.map_emu_taxa = {}    # maps taxon irn to narrative irn

        whitelist = [
            'emultimedia',
            'enarratives',
            'etaxonomy'
        ]
        fields = xmu.XMuFields(whitelist=whitelist, source_path=source_path)
        tax = XMu(source_path, fields)
        tax.format_key = self.format_key
        tax.taxa = self.taxa
        tax.map_narratives = self.map_narratives
        tax.map_emu_taxa = self.map_emu_taxa
        tax.fast_iter(tax.itertax)
        print u'{:,} records read'.format(len(self.taxa))

        # Map tree for each taxon
        print 'Mapping trees...'
        n = 0
        for irn in self.taxa:
            tree = self.recurse_tree(self.taxa[irn]['name'], [])
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
        """Standardize formatting of keys in taxa dictionary"""
        return key.lower().replace(' ', '-')


    def find(self, taxon, classify_unknown=True):
        """Returns taxonomic data for a taxon name or narrative irn"""
        taxon = self.clean_taxon(taxon)
        try:
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

        For a more general function, use find()"""
        try:
            return self.taxa[self.map_emu_taxa(irn)]
        except KeyError:
            return self.generate_taxon(taxon)


    def classify_taxon(self, taxon):
        """Classify unknown taxon"""
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


    def recurse_tree(self, taxon, tree):
        try:
            irn = self(taxon)['parent']
            taxon = self(irn)['name']
        except KeyboardInterrupt:
            raise
        except KeyError:
            pass
        except IndexError:
            pass
        else:
            tree.append(taxon)
            self.recurse_tree(taxon, tree)
        return tree[::-1]


    def simple_tree(self, tree):
        """Simplify the full tree for retrieval"""
        return tree


    def format_taxon(self, taxon):
        """Looks for alternative spellings"""
        pass


    def clean_taxon(self, taxon):
        """Reformats taxon of the form 'Gneiss, Garnet' to 'Garnet Gneiss'"""
        if taxon.count(',') == 1:
            taxon = ' '.join([s.strip() for s in taxon.split(',')][::-1])
        return taxon


    def cap_taxa(self, s, ucfirst=True):
        """Returns a properly capitalized taxon name"""
        # Reorder terms and force lower case
        orig = copy(s)
        s = s.lower()
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
        # Clean up string
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
        tdata = self(self.preferred_synonym(taxon))
        if self.is_official(tdata):
            return taxon
        else:
            for t in reversed(self(taxon)['tree']):
                if self.is_official(self(t)):
                    return t
        return taxon


    def is_official(self, tdata):
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
        """Removes duplicate taxa while retaining order"""
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
        name for multiple items, use group_name().

        Args:
            taxa (list)
            setting (str)
            name (str)

        Returns:
            Display name as string
        """
        if bool(name):
            return name
        # Taxa is required if name is not specified
        orig = copy(taxa)
        taxa = [s for s in taxa if bool(s)]
        if not any(taxa):
            return 'Unidentified object'
        if not isinstance(taxa, list):
            taxa = [taxa]
        taxa = self.clean_taxa(taxa, True)
        highest_common_taxon, taxa = self.group_taxa(taxa)
        # Special handling
        if len(taxa) > 1:
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
        # try to remove them here.
        try:
            primary = formatted[0].lower()
        except IndexError:
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
            return primary + ' with ' + oxford_comma(formatted)
        else:
            return ''.join(formatted)


    def group_name(self, *taxas):
        """Format display name for a group of specimens, as in a photo

        @param list (of lists)
        @return string
        """
        highest_common_taxon = self.highest_common_taxon(taxas)
        if highest_common_taxon.endswith((' Group', 'Series')):
            highest_common_taxon = highest_common_taxon.rsplit(' ', 1)[0]
        return highest_common_taxon


    def preferred_synonym(self, taxon):
        """Recursively find the preferred synonym for this taxon

        @param string
        @return string
        """
        taxon = self(taxon)
        while len(taxon['synonyms']):
            taxon = self(copy(taxon['synonyms']).pop())
        return taxon['name']


    def group_taxa(self, taxa):
        """Group synonyms and varieties for a single specimen

        Args:
            taxa (list): list of taxa from one specimen

        Returns:
            List of grouped taxa
        """
        if not isinstance(taxa, list):
            taxa = [taxa]
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
            taxas (list): list of taxa to group

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
