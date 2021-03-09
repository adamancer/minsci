"""Defines unit tests for XMuRecord and related classes"""
import os
import unittest

import pytest

from minsci import xmu




class XMu(xmu.XMu):
    """Parsed EMu XML import"""

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.record = None


    def iterate(self, element):
        """Assigns the last record parsed to the record attribute"""
        self.record = self.parse(element)


@pytest.fixture(params=['xmldata.xml', 'xmldata.zip'])
def rec(request):
    xmudata = XMu(
        os.path.join(__file__, '..', '..', 'data', 'tests', request.param)
    )
    xmudata.fast_iter(limit=1)
    return xmudata.record


@pytest.mark.parametrize(
    'test_input, expected',
    [
        ('CatPrefix', 'A'),
        ('CatNumber', '12345'),
        ('CatSuffix', '00'),
        ('CatDivision', 'Petrology & Volcanology'),
        ('CatCatalog', 'Rock & Ore Collections'),
    ]
)
def test_atomic(rec, test_input, expected):
    assert rec(test_input) == expected


def test_atomic_reference(rec):
    assert rec('LocPermanentLocationRef') == {'irn': '1003604'}


def test_grid(rec):
    assert rec('CatCollectionName_tab') == ['Unit Test Collection']


def test_dot_path_to_reference(rec):
    assert rec('LocPermanentLocationRef.irn') == '1003604'


def test_arg_path_to_reference(rec):
    assert rec('LocPermanentLocationRef', 'irn') == '1003604'


def test_grid_iteration(rec):
    cols = ['IdeTaxonRef_tab', 'IdeNamedPart_tab', 'IdeTextureStructure_tab']
    grid = rec.grid(cols)
    expected = [
        {'IdeNamedPart_tab': 'Primary',
         'IdeTaxonRef_tab': {'irn': '1001689'},
         'IdeTextureStructure_tab': ''},
        {'IdeNamedPart_tab': '',
         'IdeTaxonRef_tab': {'irn': '1009644'},
         'IdeTextureStructure_tab': 'Xenocrystic'},
        {'IdeNamedPart_tab': 'Associated',
         'IdeTaxonRef_tab': {'irn': '1004148'},
         'IdeTextureStructure_tab': ''},
    ]
    for i, row in enumerate(grid):
        assert row == expected[i]


def test_grid_by_index(rec):
    cols = ['IdeTaxonRef_tab', 'IdeNamedPart_tab', 'IdeTextureStructure_tab']
    grid = rec.grid(cols)
    expected = [
        {'IdeNamedPart_tab': 'Primary',
         'IdeTaxonRef_tab': {'irn': '1001689'},
         'IdeTextureStructure_tab': ''},
        {'IdeNamedPart_tab': '',
         'IdeTaxonRef_tab': {'irn': '1009644'},
         'IdeTextureStructure_tab': 'Xenocrystic'},
        {'IdeNamedPart_tab': 'Associated',
         'IdeTaxonRef_tab': {'irn': '1004148'},
         'IdeTextureStructure_tab': ''},
    ]
    for i, exp in enumerate(expected):
        assert grid[i] == exp


def test_grid_by_column(rec):
    cols = ['IdeTaxonRef_tab', 'IdeNamedPart_tab', 'IdeTextureStructure_tab']
    grid = rec.grid(cols)
    expected = {
        'IdeTaxonRef_tab': [{'irn': '1001689'},
                            {'irn': '1009644'},
                            {'irn': '1004148'}],
        'IdeNamedPart_tab': ['Primary', '', 'Associated'],
        'IdeTextureStructure_tab': ['', 'Xenocrystic', '']
    }
    for col in cols:
        assert grid[col] == expected[col]
