MinSci Tools
============

Everything in this package is in active, albeit sporadic development.
Caveat emptor.

GeoTaxa
-------

The GeoTaxa module contains a hierarchical taxonomy for geologic materials,
including rocks, minerals, and meteorites. The hierarchy is based on schemes
and species definitions published by the IUGS, the British Geological Survey,
RRUFF, and Mindat. It is very much a work in progress.

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

Mosaic
------

This is a simple image-stitching program designed to create mosaics from
tile sets with regular offsets. We use it to stitch images from the SEM
and petrographic microscopes and to select subsets of tiles for more
detailed analysis. It is currently being updated to be slightly less
maddening than its earlier incarnation.

To use, collect the tile sets you'd like to stitch in a single folder. Then
run the following:

   >>> from minsci.mosaic import mosey
   >>> mosey(r'C:\path\to\my\tiles')  # you can provide the path
   >>> mosey()                        # or use a dialog in the script instead

Select the folder where you've stored your tile sets. The script will then
direct you through the process of determining the offsets and stitching a
mosaic together.
