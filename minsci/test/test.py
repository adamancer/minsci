from minsci import geotaxa

gt = geotaxa.GeoTaxa()
print gt.item_name('diamond', 'Hope Diamond', 'necklace')
print gt.item_name(['beryl', 'sapphire', 'citrine'], '', 'necklace')
print gt.item_name(['aquamarine', 'sapphire', 'citrine'])
print gt.item_name(['ruby', 'sapphire', 'corundum', 'sapphire'])
print gt.item_name(['basalt, olivine', 'olivine'])
print gt.item_name('h6 chondrite')
print gt.item_name('brachinite')
print gt.item_name('aca-lod')
print gt.item_name('ia')
