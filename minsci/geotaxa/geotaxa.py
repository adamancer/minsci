import cPickle as pickle
import os
import re
from copy import copy

from minsci import XMu


class XMu(XMu):


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
            except:
                schemes[name] = [_id]

        self.taxa[irn] = {
            'irn' : irn,
            'name' : title,
            'parent' : parent,
            'synonyms' : synonyms,
            'tags' : tags,
            'schemes' : schemes,
            'taxa' : taxa
        }
        key = self.format_key(title)
        self.map_narratives[key] = irn
        for taxon in taxa:
            self.map_emu_taxa[taxon] = irn
        if not len(self.taxa) % 2500:
            print '{:,} records read'.format(len(self.taxa))




class GeoTaxa(object):


    def __init__(self, fi=None, force_format=False):
        """Read data from EMu export file

        Will check for pickled data if exists"""
        self.dir = os.path.join(os.path.dirname(__file__), 'files')
        if fi is None:
            fi = os.path.join(self.dir, 'xmldata.xml')
        self.elements = open(os.path.join(self.dir,
                                          'elements.txt')).read().splitlines()

        # Check for pickled data
        pickled = os.path.splitext(fi)[0] + '.p'
        if force_format:
            try:
                os.remove(pickled)
            except:
                pass
        try:
            f = open(pickled, 'rb')
        except:
            print 'Reading taxonomic data from {}...'.format(fi)
            self.taxa = {}
            self.map_narratives = {}  # maps taxon name to narrative irn
            self.map_emu_taxa = {}    # maps taxon irn to narrative irn

            xmu = XMu(fi=fi, fo='geotaxa.xml', force_format=True)
            xmu.format_key = self.format_key
            xmu.taxa = self.taxa
            xmu.map_narratives = self.map_narratives
            xmu.map_emu_taxa = self.map_emu_taxa
            xmu.fast_iter(xmu.itertax)
            print '{:,} records read'.format(len(self.taxa))

            # Map tree for each taxon
            for irn in self.taxa:
                tree = self.recurse_tree(self.taxa[irn]['name'], [])
                self.taxa[irn]['tree'] = tree

            # Pickle the taxanomic dictionaries for later use
            tds = {
                'taxa' : self.taxa,
                'map_narratives' : self.map_narratives,
                'map_emu_taxa' : self.map_emu_taxa,
                 }
            with open(pickled, 'wb') as f:
                pickle.dump(tds, f)
            os.remove('geotaxa.xml')
        else:
            # Use pickled data. This is much faster.
            print 'Reading taxonomic data from {}...'.format(pickled)
            with open(pickled, 'rb') as f:
                tds = pickle.load(f)
            self.taxa = tds['taxa']
            self.map_narratives = tds['map_narratives']
            self.map_emu_taxa = tds['map_emu_taxa']




    def __call__(self, taxon):
        """Returns taxonomic data when instance is called"""
        return self.find(taxon)




    def find(self, taxon):
        """Returns taxonomic data for a taxon name or narrative irn"""
        try:
            int(taxon)
        except:
            # Taxon is given as name
            try:
                return self.taxa[self.map_narratives[self.format_key(taxon)]]
            except:
                return self.generate_taxon(taxon)
        else:
            # Taxon given as irn
            try:
                return self.taxa[taxon]
            except:
                return self.generate_taxon(taxon)




    def find_emu_taxon(self, irn):
        """Returns taxonomic data for an EMu Taxonomy irn

        For a more general function, use find()"""
        try:
            return self.taxa[self.map_emu_taxa(irn)]
        except:
            return self.generate_taxon(taxon)




    def generate_taxon(self, taxon):
        """Creates minimal taxon record if could not match taxon"""
        if bool(taxon):
            print u'Warning! Could not match {}'.format(taxon)
            key = self.format_key(taxon)
            self.taxa[key] = {
                'irn' : None,
                'name' : self.cap_taxa(taxon),
                'parent' : '',
                'synonyms' : [],
                'tags' : [],
                'schemes' : {},
                'taxa' : [],
                'tree' : [],
                'synonyms' : []
            }
            print key
            return self.taxa[key]
        else:
            return {}




    def recurse_tree(self, taxon, tree):
        try:
            irn = self(taxon)['parent']
            taxon = self(irn)['name']
        except:
            pass
        else:
            tree.append(taxon)
            self.recurse_tree(taxon, tree)
        return tree[::-1]




    def format_taxon(self, taxon):
        """Looks for alternative spellings"""
        pass




    def format_key(self, key):
        return key.lower().replace(' ', '-')




    def _cap_taxa(self, s, ucfirst=True):
        """Returns a properly capitalized taxon name"""

        # Exceptions to capitlization rules, mostly meteorite classes.
        # These should always be capitalized.
        exceptions = [
            'CB', 'CH', 'CK', 'CM', 'CR', 'CV', 'CO', 'CI',
            'EH', 'EL',
            'H', 'HED',
            'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
            'IAB', 'IA', 'IB', 'IC', 'ID', 'IE',
            'IIAB', 'IICD', 'IIA', 'IIB', 'IIC', 'IID', 'IIE', 'IIF', 'IIG',
            'IIIAB', 'IIICD', 'IIIA', 'IIIB', 'IIIC', 'IIID', 'IIIE', 'IIIF',
            'IVAB', 'IVA', 'IVB',
            'L', 'LL',
            'TAS',
            'Cerny', 'Chen', 'Hauser', 'Hogarth',
            'Leake', 'Nicol', 'Shephard', 'Voloshin'
            ]
        # Reorder terms and force lower case
        s = s.lower()
        orig = copy(s)
        # Elements and exceptions
        self.elements = []
        exclude = ('in', 's')
        elements = [e.lower() for e in self.elements if not e in exclude]
        lc_exceptions = [e.lower() for e in exceptions]
        # Handle suffixes of, e.g Mineral-(La) or Mineral-(CaMnMg)
        p = re.compile('(\W)', re.U)
        try:
            arr = p.split(s)
        except:
            pass
        else:
            capped = []
            for s in arr:
                # Stripped s
                s_stripped = s.rstrip('1234567890.')
                # Capitalize elements
                if s in elements:
                    try:
                        s = s[0].upper() + s[1].lower()
                    except:
                        s = s.upper()
                elif s_stripped in lc_exceptions:
                    s = exceptions[lc_exceptions.index(s_stripped)] +\
                        s[len(s_stripped):]
                # Capitalize element groups (e.g., CaFeMg)
                elif not self.taxon_exists(s):
                    temp = ''
                    i = 0
                    while i < len(s):
                        try:
                            sub = s[i:i+2]
                        except:
                            sub = s[i]
                            if sub.lower() in elements:
                                #print sub + ' is an element'
                                temp += sub.upper()
                                i += 1
                            else:
                                #print 'Not elemental: ' + suffix
                                temp = ''
                                i = len(s)
                        else:
                            # Case 1: One-two letter element
                            if sub.lower() in elements:
                                #print 'Case 1: ' + sub + ' is an element'
                                try:
                                    temp += sub[0].upper() + sub[1].lower()
                                except:
                                    temp += sub.upper()
                                i += 2
                            # Case 2: Two one-letter elements
                            elif sub[0] in elements:
                                #print 'Case 2: ' + sub[0] + ' is an element'
                                temp += sub[0].upper()
                                i += 1
                            else:
                                #print 'Not elemental: ' + suffix
                                temp = ''
                                i = len(s)
                # Special handling
                if s == 'S':
                    s = s.lower()
                capped.append(s)
            s = ''.join(capped)
        # Capitalize first letter if ucfirst
        if ucfirst:
            try:
                s = s[0].upper() + s[1:]
            except:
                s = s.upper()
        else:
            try:
                s = s[0].lower() + s[1:]
            except:
                s = s.lower()
        # Special handling
        if s.lower().startswith('bgs-'):
            s = s.upper()
        s = s.replace(' et al.', 'et al.')
        # Return capitalized string
        if self.debug and orig.lower() != s.lower():
            print 'Capitalization error: ' + orig, s
        return s




    def cap_taxa(self, taxon, ucfirst=True):
        """Capitalize string

        @param string
        @param boolean
        @return string
        """
        if ucfirst:
            return taxon[0].upper() + taxon[1:]
        else:
            return taxon[0].lower() + taxon[1:]




    def clean_taxon(self, taxon):
        """Reformats taxon of the form 'Gneiss, Garnet' to 'Garnet gneiss'"""
        if taxon.count(',') == 1:
            taxon = ' '.join([s.strip() for s in taxon.split(',')][::-1])
        return taxon




    def dedupe_taxa(self, taxa):
        """Removes duplicate taxa while retaining order"""
        taxa = [geotaxa.preferred_synonym(taxon) for taxon in taxa]
        temp = []
        while len(taxa):
            taxon = taxa.pop()
            if not taxon in taxa:
                temp.insert(0, taxon)
        taxa = temp




    def oxford_comma(self, lst, lowercase=True):
        """Formats string as comma-delimited string

        @param list
        @param boolean
        @return string
        """
        if lowercase:
            lst = [s[0].lower() + s[1:] for s in lst]
        if len(lst) <= 1:
            return ''.join(lst)
        elif len(lst) == 2:
            return ' and '.join(lst)
        else:
            last = lst.pop()
            return ', '.join(lst) + ', and ' + last





    def item_name(self, taxa, name=None, setting=None):
        """Format display name for a specimen based on taxa and other info

        @param list
        @param string
        @param string
        @return string

        This function is intended for single specimens. To format a
        name for multiple items, use _____.
        """
        if bool(name):
            return name
        if not isinstance(taxa, list):
            taxa = [taxa]
        highest_common_taxon, taxa = self.group_taxa(taxa)
        if bool(setting):
            formatted = self.oxford_comma(taxa) + ' ' + setting
            return formatted[0].upper() + formatted[1:]
        formatted = []
        for taxon in taxa:
            preferred = self.preferred_synonym(taxon)
            taxon = self(preferred)
            # Handle minerals and varieties. Approved mineral species will
            # have an IMA status populated; a variety is anything defined
            # below an approved mineral in the taxonomic hierarchy.
            try:
                taxon['schemes']['IMA Status']
            except:
                for parent in taxon['tree']:
                    parent = self(parent)
                    try:
                        parent['schemes']['IMA Status']
                    except:
                        pass
                    else:
                        variety = taxon['name'][0].lower() + taxon['name'][1:]
                        formatted.append(u'{} (var. {})'.format(parent['name'],
                                                                variety))
                        break
                else:
                    #name = taxon['name']
                    #if name.lower().endswith(' group'):
                    #    name = name.rsplit(' ', 1)[0]
                    formatted.append(taxon['name'])
            else:
                formatted.append(taxon['name'])
        # Some rock names include the primary mineral. Sometimes
        # that mineral will be listed separately as well. We typically
        # don't want to include that information twice, so we'll
        # try to remove them here.
        primary = formatted[0].lower()
        for taxon in copy(formatted[1:]):
            if taxon.lower() in primary:
                formatted.remove(taxon)
        # Long lists of associated taxa look terrible, so we'll
        # ditch everything after the third taxon.
        if len(formatted) > 4:
            formatted = formatted[:3]
            formatted.append('others')
        # Group varieties if everyone is the same mineral
        siblings = [taxon for taxon in formatted
                    if taxon.startswith(highest_common_taxon)]
        if len(siblings) == len(taxa) and len(taxa) > 1:
            varieties = [taxon.split('var.')[1].strip(' )')
                         for taxon in formatted]
            formatted = [(highest_common_taxon +
                          ' (vars. {})').format(self.oxford_comma(varieties))]
        # Finally format the list as a string
        if len(formatted) > 1:
            primary = formatted.pop(0)
            return primary + ' with ' + self.oxford_comma(formatted)
        else:
            return ''.join(formatted)




    def group_name(self, *taxas):
        """Format display name for a group of specimens, as in a photo

        @param list (of lists)
        @return string
        """
        highest_common_taxa = []
        all_taxa =[]
        for taxa in taxas:
            highest_common_taxon, taxa = self.group_taxa(taxa)
            highest_common_taxa.append(highest_common_taxon)
            all_taxa.extend(taxa)
        highest_common_taxa = set(highest_common_taxa)
        if len(highest_common_taxa) == 1 and len(all_taxa) > 1:
            highest_common_taxon = highest_common_taxa.pop()
            return 'Muliple ' + self.cap_taxa(highest_common_taxon, False)
        else:
            return self.cap_taxa(self.oxford_comma([self.item_name(taxa)
                                                    for taxa in all_taxa]))




    def preferred_synonym(self, taxon):
        """Recursively find the preferred synonym for this taxon

        @param string
        @return string
        """
        taxon = self(taxon)
        while len(taxon['synonyms']):
            taxon = self(taxon['synonyms'].pop())
        return taxon['name']




    def group_taxa(self, taxa):
        """Group synonyms and varieties while maintaining order

        @param list
        @return list of the form [string, list]
        """
        if len(taxa) == 1:
            taxon = self(self.preferred_synonym(taxa[0]))
            return [taxon['name'], [taxon['name']]]
        else:
            taxa = [self.preferred_synonym(taxon) for taxon in taxa]
            trees = [self(taxon)['tree'] + [self(taxon)['name']]
                     for taxon in taxa]
            sets = [set(tree) for tree in trees]
            _sets = copy(sets)
            _set = sets.pop(0)
            common = _set.intersection(*_sets)
            highest_common_taxon = trees[0][len(common)-1]
            # Some taxa aren't great for display, so we filter them out
            # using exclude.
            exclude = ['Informal group', 'Structural group', 'Ungrouped']
            while highest_common_taxon in exclude:
                highest_common_taxon = trees[0][len(common)-2]
            grouped = [tree[len(common):].pop() for tree in trees
                       if len(tree[len(common):])]
            unique = list(set(grouped))
            taxa = []
            for taxon in grouped:
                if taxon in unique:
                    taxa.append(taxon)
                    unique.remove(taxon)
            return [highest_common_taxon, taxa]
