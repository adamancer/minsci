"""Script for classifying geologic specimens using the geotaxa submodule

The geotaxa submodule is used to contextualize rock, mineral, and meteorite
names in terms of a deep taxonomic hierarchy. The hierarchy is maintained in
the Mineral Sciences taxonomy module and has been cobbled together from a
variety of sources including but not limited to the following:

+ BGS Rock Classification Scheme
+ Dana mineral classification
+ Nickel-Stunz mineral classificaiton
+ Mindat
+ Le Maitre et al., 2002. *IGNEOUS ROCKS. A Classification and Glossary of
  Terms*

A searchable and browsable version of the hierarchy is available at
http://adamancer.pythonanywhere.com/.

"""

from minsci.geotaxa import get_tree, Taxon, TaxaParser


# Construct a TaxaNamer tree containing the full taxonomic hierarchy. Slow to
# load the first time but faster thereafter.
tree = get_tree()

# Add the tree to the Taxon class so it only has to be loaded once. Indexes
# used to find and place taxa are generated as needed, so keeping the tree in
# one place means that those also only need to be set up once as well.
Taxon.tree = tree

# Run through some examples illustrating the basic functionality of the tree
print '\n\nBASIC USE\n---------'
names = [
    'corundum',                       # a valid mineral species
    'aquamarine',                     # a gem variety
    'idocrase',                       # a deprecated mineral species
    'fractured biotite-quartz gneiss'  # a rock name with modifiers
]
for name in names:
    taxon = Taxon(name)  # a taxon can also be built from XMuRecord objects
    print '\n{}\n{}'.format(name, '-' * len(name))
    print 'Name:     ', taxon              # the verbatim name
    print 'Preferred:', taxon.preferred()  # the preferred name
    print 'Official: ', taxon.official()   # the closest official name
    print 'Full name:', taxon.autoname()
    print 'Parent:   ', taxon.parent       # the direct parent in the hierarchy


# You can also automatically format the name of an object
print '\n\nOBJECT NAMES\n------------'
print tree.name_item(['emerald', 'diamond'], 'necklace')
print tree.name_item(['beryl (var. aquamarine)'], 'ring')


# The TaxaParser class is used to parse complex rock names. Valid rock names
# can contain textural and compositional modifiers, including mineral names,
# which can make them difficult to wrangle into a manageable hierarchy. The
# TaxaParser class tries to parse out the modifiers to leave a simple rock
# name that can then be placed in the broader hierarchy.
print '\n\nPARSING ROCK NAMES\n------------------'
name = 'foliated muscovite glimmerite'
print '{}\n{}'.format(name, '-' * len(name))
print TaxaParser(name)
