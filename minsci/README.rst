MinSci Tools
------------

To use, first create an instance of the GeoTaxa class:

   >>> from minsci import geotaxa
   >>> gt = geotaxa.GeoTaxa()

To get info about a rock, mineral, or meteorite, simply call the class itself:

    >>> print gt('basalt')

If no match for a given taxon is found, the script will try to place the new
taxon in the existing hierarchy.

To find the preferred synonym for a deprecated species, use preferred_synonym:

   >>> print gt.preferred_synonym('argentite')

To get the name of an object, use item_name. This function accepts as a taxa
list, setting, and/or name as parameters. For example:

   >>> print gt.item_name(['corundum, ruby, sapphire'])
   >>> print gt.item_name(name='Hope Diamond')
   >>> print gt.item_name('diamond', 'ring')
