"""Subclass of XMu that converts the geology classification hierarchy to JSON"""

import os

from unidecode import unidecode

from .geotaxa import GeoTaxon, clean_taxon, format_key, PATH
from .containers import MinSciTaxon
from ..xmu import XMu


class GeoTaxaUpdater(XMu):
    """Converts classification info from an EMu XML export into JSON"""

    def __init__(self, *args, **kwargs):
        super(GeoTaxaUpdater, self).__init__(*args, **kwargs)
        self.keep = ['taxa', 'nar_map', 'tax_map']
        self.taxa = {}
        self.nar_map = {}
        self.tax_map = {}


    def iterate(self, element):
        """Adds a taxon to the hierarchy"""
        rec = self.parse(element)
        name = clean_taxon(rec('NarTitle'))
        definition = rec('NarNarrative')
        if 'EMu' in definition or definition.startswith('No additional info'):
            definition = ''
        parent = clean_taxon(rec('AssMasterNarrativeRef', 'NarTitle'))
        alternatives = rec('TaxTaxaRef_tab', 'ClaSpecies')
        key = format_key(name)
        try:
            self.taxa[key]
        except KeyError:
            # Add to taxadict
            taxadict = GeoTaxon({
                'irn': int(rec('irn')),
                'name': name,
                'definition': definition,
                'parent': parent,
                'preferred': rec.get_synonyms(),
                'alternatives': alternatives,
                'tax_irns': rec('TaxTaxaRef_tab', 'irn'),
                'schema': rec.get_schema()
            })
            # Format and test values in taxadict
            taxadict['parent'] = format_key(parent)
            for key in ['preferred', 'alternatives']:
                taxadict[key] = [format_key(t) for t in taxadict[key]]
            if not format_key(name) in taxadict['preferred']:
                self.taxa[key] = taxadict
        else:
            alternatives = [format_key(t) for t in alternatives]
            self.taxa[key]['alternatives'].extend(alternatives)
            warning = u'Warning: {} already exists!'
            try:
                print warning.format(name)
            except UnicodeEncodeError:
                print warning.format(unidecode(name))


    def finish_and_save(self):
        """Adds taxonomic tree and alternative keys, then saves the tree"""
        print 'Deriving taxonomic trees...'
        update = {}
        for taxon in self.taxa:
            self._recurse_synonyms(taxon)
        i = 0
        for taxon, taxadict in self.taxa.iteritems():
            taxadict['tree'] = self._recurse_tree(taxadict['name'])
            taxadict['synonyms'] = sorted(list(set(taxadict.get('synonyms', []))))
            if taxadict['synonyms']:
                try:
                    print taxon, taxadict['synonyms']
                except (KeyError, UnicodeEncodeError):
                    pass
            # Create unaccented keys for accented taxa
            try:
                flattened = unidecode(taxon)
            except AttributeError:
                pass
            else:
                if taxon != flattened and self.taxa.get(flattened) is None:
                    update[flattened] = taxadict
            # Add irns as keys
            if self.taxa.get(taxadict['irn']) is None:
                update[taxadict['irn']] = taxadict
            # Look for unserializable keys
            if taxon != format_key(taxon):
                raise Exception('Bad key: {}'.format(taxon))
            i += 1
            if not i % 25:
                print '{:,} records processed!'.format(i)
        self.taxa.update(update)
        self.save(os.path.join(PATH, 'geotaxa.json'))


    def _recurse_tree(self, taxon, tree=None):
        """Trace classification hierarchy for a given taxon

        Args:
            taxon (str): a type of rock, mineral, or meteorite
            tree (list): the taxonomic hierarchy for the taxon compiled so far.
                This list is modified as the function proceeds.

        Returns:
            A list containing the taxonomic hierarchy for the given taxon
        """
        if tree is None:
            tree = []
        taxon = format_key(taxon)
        try:
            parent = self.taxa[taxon]['parent']
        except KeyboardInterrupt:
            raise
        except KeyError:
            pass
        except IndexError:
            pass
        except RuntimeError:
            raise
        else:
            try:
                taxon = self.taxa[format_key(parent)]['name']
            except KeyError:
                if parent:
                    print 'Missing: {}'.format(parent)
            else:
                tree.append(taxon)
                self._recurse_tree(taxon, tree)
        return tree[::-1]


    def _recurse_synonyms(self, taxon, synonyms=None):
        """Recursively identifies synonyms for the current, preferred taxon"""
        if synonyms is None:
            synonyms = []
        for preferred in self.taxa[taxon]['preferred']:
            try:
                print taxon, '=>', preferred
            except:
                pass
            synonyms.append(taxon)
            taxadict = self.taxa[format_key(preferred)]
            while taxadict['preferred']:
                synonyms.append(taxadict['name'])
                taxadict = self.taxa[format_key(taxadict['preferred'][-1])]
            synonyms = [format_key(t) for t in synonyms]
            taxadict.setdefault('synonyms', []).extend(synonyms)


def update_geotaxa(fp):
    """Convenience function to create geotaxa.json"""
    xmudata = GeoTaxaUpdater(fp, container=MinSciTaxon)
    xmudata.fast_iter(report=5000, callback=xmudata.finish_and_save)
