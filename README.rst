MinSci Tools
============

Everything in this package is in active, albeit sporadic development.
Caveat emptor.

Mosaic
------

This is a simple image-stitching program designed to create mosaics from
tile sets with regular offsets. We use it to stitch images from SEM
and petrographic microscopes and to select subsets of tiles for more
detailed analysis. It is currently being updated to be slightly less
maddening than its earlier incarnation.

To use, first collect the tile sets you'd like to stitch in a single folder.
There are currently three primary tools, each accessible from the command line:

**Mosaic.** Use the mosaic tool to stitch a set of tiles into a mosaic. The
mosaic is saved in the directory you specify. From the command line:

```batchfile
minsci-toolkit mosaic
```

If no path is provided, you will have the option to select the source
directory from within the script. You can also provide the path as part
of the command:

```batchfile
minsci-toolkit mosaic -p C:\path\to\mosaics
```

By default, the script creates a mosaic with the same extension as the
source tiles. You can have the script create a JPEG derivative using the
--create_jpeg flag:

```batchfile
minsci-toolkit mosaic --create_jpeg
```

**Selector.** Use the selector tool to select tiles to exclude from future SEM
element mapping. This tool does the following:

*  *Creates a points file for use with Noran System Seven.* File contains
   the center point of each tile that was kept from the original grid.
*  *Moves excluded tiles to a directory in the source folder.* These tiles
   are automatically reintegrated if the selection script is run again.
*  *Produces a list of tiles to skip.* The mosaic script uses this list to
   fill in gaps in the mosaic where the excluded tiles were removed.
*  *Produces a screenshot showing the final selection grid.*

To use the select script:

```batchfile
minsci-toolkit select
```

Click the tiles you'd like to remove, or click a darkened tile to reinstate it.
As with the mosaic script, the select command accepts an optional path argument
using the -p flag.

**Organizer.** *This command is currently disabled.* This command organizes
element maps produces by Noran System Seven into element-specific folders
suitable for mosaicking. It accepts optional arguments for the source and
destination directories:

```batchfile
minsci-toolkit organize C:\path\to\source C:\path\to\destination
```

GeoTaxa
-------

The GeoTaxa module contains a hierarchical taxonomy for geologic materials,
including rocks, minerals, and meteorites. The hierarchy is based on schemes
and species definitions published by the IUGS, the British Geological Survey,
RRUFF, and Mindat. It is very much a work in progress.

To use, first create an instance of the GeoTaxa class:

```python
from minsci import geotaxa
gt = geotaxa.GeoTaxa()
```

To get info about a rock, mineral, or meteorite, simply call the class itself:

```python
print gt('basalt')
```

If no match for a given taxon is found, the script will try to place the new
taxon in the existing hierarchy.

To find the preferred synonym for a deprecated species, use preferred_synonym:

```python
print gt.preferred_synonym('argentite')
```

To get the name of an object, use item_name. This function accepts as a taxa
list, setting, and/or name as parameters. For example:

```python
print gt.item_name(['corundum, ruby, sapphire'])
print gt.item_name(name='Hope Diamond')
print gt.item_name('diamond', 'ring')
```
