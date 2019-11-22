"""Defines unit tests for XMuRecord and related classes"""
import os
import unittest

from minsci import xmu




class XMu(xmu.XMu):
    """Parsed EMu XML import"""

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.record = None


    def iterate(self, element):
        """Assigns the last record parsed to the record attribute"""
        self.record = self.parse(element)




class TestXMu(unittest.TestCase):
    """Base testing class with method to read data from file"""
    _record = None

    def __init__(self, *args, **kwargs):
        self.grid = None
        super(TestXMu, self).__init__(*args, **kwargs)


    @property
    def record(self):
        """Reads record from file if class attribute not already populated"""
        if self._record is None:
            fp = os.path.join(os.path.dirname(__file__), 'files', 'xmldata.xml')
            xmudata = XMu(fp)
            xmudata.fast_iter()
            self.__class__._record = xmudata.record
        return self._record




class TestAtomic(TestXMu):
    """Tests parsing of atomic fields"""

    def test_atomic(self):
        """Tests parsing atomic fields, including entity parsing"""
        rec = self.record
        self.assertEqual(rec('CatPrefix'), 'A')
        self.assertEqual(rec('CatNumber'), '12345')
        self.assertEqual(rec('CatSuffix'), '00')
        self.assertEqual(rec('CatDivision'), 'Petrology & Volcanology')
        self.assertEqual(rec('CatCatalog'), 'Rock & Ore Collections')




class TestGrids(TestXMu):
    """Tests parsing of grids"""

    def test_simple_grids(self):
        """Tests one-column grids"""
        rec = self.record
        self.assertEqual(rec('CatCollectionName_tab'), ['Unit Test Collection'])


    def test_identification_grid(self):
        """Tests grid with empty cell in middle row"""
        cols = [
            'IdeTaxonRef_tab',
            'IdeNamedPart_tab',
            'IdeTextureStructure_tab'
        ]
        # Set up test rows
        tests = [
            ({'irn': '1001689'}, 'Primary', ''),
            ({'irn': '1009644'}, '', 'Xenocrystic'),
            ({'irn': '1004148'}, 'Associated', '')
        ]
        test_rows, test_cols = set_tests(cols, tests)
        # Run tests on record before the grid is configured
        test_call(self, test_cols)
        # Run tests on grid
        self.grid = self.record.grid(cols)
        self.grid.label = 'IdeNamedPart_tab'
        test_iter(self, test_rows)
        test_by_index(self, test_rows)
        test_by_column(self, test_cols)
        test_by_label(self, 'Primary', test_rows)


    def test_other_numbers_grid(self):
        """Tests grid with empty middle row"""
        cols = [
            'CatOtherNumbersType_tab',
            'CatOtherNumbersValue_tab'
        ]
        # Set up test rows
        tests = [
            ("Collector's field number", 'ABC-1'),
            ('', ''),
            ('IGSN', 'NHB000ABC')
        ]
        test_rows, test_cols = set_tests(cols, tests)
        # Run tests on record before the grid is configured
        test_call(self, test_cols)
        # Run tests on grid
        self.grid = self.record.grid(cols)
        test_iter(self, test_rows)
        test_by_index(self, test_rows)
        test_by_column(self, test_cols)
        test_by_label(self, 'IGSN', test_rows)


    def test_preparation_grid(self):
        """Tests grid with top row"""
        cols = [
            'ZooPreparation_tab',
            'ZooPreparationCount_tab'
        ]
        # Set up test rows
        tests = [
            ('', ''),
            ('Thin Section', '2'),
            ('Probe Mount', '')
        ]
        test_rows, test_cols = set_tests(cols, tests)
        # Run tests on record before the grid is configured
        test_call(self, test_cols)
        # Run tests on grid
        self.grid = self.record.grid(cols)
        test_iter(self, test_rows)
        test_by_index(self, test_rows)
        test_by_column(self, test_cols)
        test_by_label(self, 'Thin Section', test_rows)


    def test_notes_grid(self):
        """Tests grid with empty top row in contained nested table"""
        cols = [
            'NotNmnhText0',
            'NotNmnhDate0',
            'NotNmnhType_tab',
            'NotNmnhAttributedToRef_nesttab'
        ]
        # Set up test rows
        tests = [(
            ('Record with data entry irregularities to use for unit'
             ' tests of the xmu package'),
            '2019-11-21',
            'Comments',
            [{'irn': ''}, {'irn': '1006206'}]
        )]
        test_rows, test_cols = set_tests(cols, tests)
        # Run tests on record before the grid is configured
        test_call(self, test_cols)
        # Run tests on grid
        self.grid = self.record.grid(cols)
        self.grid.label = 'NotNmnhType_tab'
        test_iter(self, test_rows)
        test_by_index(self, test_rows)
        test_by_column(self, test_cols)
        test_by_label(self, 'Comments', test_rows)




class TestRefs(TestXMu):
    """Tests parsing of references to other modules"""

    def test_permanent_location_ref(self):
        """Tests different paths for retireving a reference"""
        tests = {
            'LocPermanentLocationRef.irn': '1003604',
            'LocPermanentLocationRef': {'irn': '1003604'}
        }
        for key, expected in tests.items():
            self.assertEqual(self.record(key), expected)




class TestHelpers(TestXMu):
    """Tests helper functions"""

    def test_get_catalog_number(self):
        """Tests get_catalog_number method"""
        rec = xmu.MinSciRecord(self.record)
        catnum = rec.get_catalog_number()
        self.assertEqual(catnum, 'NMNH A12345-00')


    def test_get_guid(self):
        """Tests get_guid method"""
        igsn = self.record.get_guid('IGSN')
        self.assertEqual(igsn, 'NHB000ABC')


    def test_has_collection(self):
        """Tests has_collection method"""
        self.assertTrue(self.record.has_collection('Unit Test Collection'))




def set_tests(keys, vals):
    """Converts values to lists of rows and columns"""
    rows = [{k: v for k, v in zip(keys, vals)} for vals in vals]
    cols = {}
    for row in rows:
        for key, val in row.items():
            cols.setdefault(key, []).append(val)
    return rows, cols


def test_call(inst, cols):
    """Tests calling the XMuRecord object, which invokes smart_pull"""
    for col, vals in cols.items():
        vals = vals[:]
        while not vals[-1]:
            vals.pop()
        inst.assertEqual(inst.record(col), vals)


def test_iter(inst, rows):
    """Tests grid iteration"""
    for i, row in enumerate(inst.grid):
        inst.assertEqual(row, rows[i])


def test_by_index(inst, rows):
    """Tests retrieving rows from the grid by index"""
    for i, row in enumerate(rows):
        inst.assertEqual(row, inst.grid[i])


def test_by_column(inst, cols):
    """Tests columns from the grid by column name"""
    for col, vals in cols.items():
        inst.assertEqual(inst.grid[col], vals)


def test_by_label(inst, label, rows):
    """Tests retrieving row from the grid by label"""
    col = inst.grid.label
    inst.assertEqual(inst.grid[label], [r for r in rows if r[col] == label][0])




if __name__ == '__main__':
    unittest.main()
