"""Script to write an EMu import file"""
from minsci import xmu


# XMuRecord is the generic subclass for writing EMu-friendly XML
rec = xmu.XMuRecord({
    'CatPrefix': 'G',
    'CatNumber': '3551',
    'CatSuffix': '00',
})

# Add a classification term from etaxonomy by irn or name. Note that because
# IdeTaxonRef_tab is a grid, we provide the values as a list.
rec['IdeTaxonRef_tab'] = [{'irn': 1004090}]
rec['IdeTaxonRef_tab'] = [{'ClaScientificName': 'Diamond'}]

# Linking by irn is a common operation and consistent across all modules, so
# XMuRecord assumes that a list of integers assigned to a reference are irns.
rec['IdeTaxonRef_tab'] = [1004090]

rec.module = 'ecatalogue'                     # specify the module
rec.expand()                                  # fill out grids and references
xmu.write('import.xml', [rec], 'ecatalogue')  # create the import