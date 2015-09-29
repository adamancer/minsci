from minsci import geotaxa

gt = geotaxa.GeoTaxa()
print ''

# Taxonomic data
species = 'corundum'
data = gt(species)
print 'Data for {}:'.format(species)
for key, value in data.iteritems():
    print key + ':', value
print ''

# Synonyms
print 'Synonyms:'
species = 'idocrase'
preferred = gt.preferred_synonym(species)
print '{} is the current name for {}'.format(preferred, species)
species = 'argentite'
preferred = gt.preferred_synonym(species)
print '{} is the current name for {}'.format(preferred, species)
print ''

# Item names
#gt.item_name(taxa, setting, name)
print 'Names:'
print gt.item_name('diamond', 'necklace', 'Hope Diamond')
print gt.item_name(name='Carmen Lucia Ruby')
print gt.item_name(['beryl', 'sapphire', 'citrine'], 'necklace')
print gt.item_name(['aquamarine', 'sapphire', 'citrine'])
print gt.item_name(['ruby', 'sapphire', 'corundum', 'sapphire'])
print gt.item_name(['basalt, olivine', 'olivine'])
print gt.item_name('h6 chondrite')
print gt.item_name('ia')
