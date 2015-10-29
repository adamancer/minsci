MinSci Toolkit
==============

A collection of tools written in Python 2.x for Mineral Sciences at NMNH.
You can install the MinSci Toolkit from the command line using pip:

```
pip install minsci
```

**Note:** The mosaic module has been moved to a separate repository,
[Stitch2D](https://github.com/adamancer/stitch2d).

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
