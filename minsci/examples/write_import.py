"""Script to write an EMu update file"""
from minsci import xmu


# Updates are the same as imports except they specify an irn and support
# appending data to grids
rec = xmu.XMuRecord({
    'irn': 1001299,
    'CatPrefix': 'G',
    'CatNumber': '3551',
    'CatSuffix': '00',
})

# Use (+) after the field name to append to a grid. If the fields are part of
# a grid, the fields will be automatically grouped so they all end up in the
# same row. Note that the grouping functionality requires tables to be defined
# in minsci/xmu/files/tables; the files in the default installation of this
# package are specific to NMNH.
rec['MeaType_tab(+)'] = ['Weight']
rec['MeaVerbatimValue_tab(+)'] = ['45.52']    # specify numbers as strings
rec['MeaVerbatimUnit_tab(+)'] = ['ct']

rec.module = 'ecatalogue'                     # specify the module
rec.expand()                                  # fill out grids and references
xmu.write('update.xml', [rec], 'ecatalogue')  # create the import
