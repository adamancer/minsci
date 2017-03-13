"""Tools to match EMu records for making attachments"""

import copy
import json
import os

from unidecode import unidecode

from ...xmu import XMu, MinSciRecord, is_reference


def standardize_taxon(species):
    """Standardize formatting of classification to improve matching"""
    species = unidecode(species).replace('-', ' ')
    if species.count(',') == 1:
        species = ' '.join([s.strip() for s in species.split(',')[::-1]])
    return species


# List of fields to include for the attachment search. All other fields will
# be excluded.
INCLUDE = {
    'ebibliography': ['ArtTitle', 'ArtParentRef', 'ArtVolume', 'ArtIssue'],
    'ecatalogue': ['CatPrefix', 'CatNumber', 'CatSuffix', 'CatDivision'],
    'elocations': ['LocLevel{}'.format(x) for x in xrange(1, 9)],
    'eparties': ['NamFirst', 'NamMiddle', 'NamLast', 'NamOrganisation'],
    'etaxonomy': ['ClaSpecies']
}

# List of fields to exclude from the attachment search. All other fields will
# be included.
EXCLUDE = {
    'ecollectionevents': ['ColParticipantStringAuto',
                          'ColParticipantString',
                          'LatCentroidLatitude0',
                          'LatCentroidLatitudeDec_tab',
                          'LatCentroidLongitude0',
                          'LatCentroidLongitudeDec_tab',
                          'LatPreferred_tab',
                          'LocRecordClassification'
                          'LocSiteStationNumber',
                          'LocSiteStationSource',
                          'LocSiteName_tab',
                          'MulMultiMediaRef_tab',
                          'LocContinent',
                          'VolRegionName',
                          'VolSubRegionName']
}

# Contains lists of fields that contain the same data converted to different
# units. This causes matching problems, and only one of these should be
# included in the data passed back to EMu if no match can be made offline.
DERIVED = {
    'ecollectionevents': [
        ['AquBottomDepthFromFath', 'AquBottomDepthFromFt', 'AquBottomDepthFromMet'],
        ['AquBottomDepthToFath', 'AquBottomDepthToFt', 'AquBottomDepthToMet'],
        ['LatLatitude_nesttab', 'LatLatitudeDecimal_nesttab', 'LatLatitudeVerbatim_nesttab'],
        ['LatLongitude_nesttab', 'LatLongitudeDecimal_nesttab', 'LatLongitudeVerbatim_nesttab'],
        ['TerElevationFromFt', 'TerElevationFromMet'],
        ['TerElevationToFt', 'TerElevationToMet'],
    ]
}

# Transform data in certain fields to handle different formats, etc.
TRANSFORMATIONS = {
    'etaxonomy': {'ClaSpecies': standardize_taxon}
}


class Matcher(XMu):
    """Match data from a given record to existing EMu records

    Attributes:
        fields (list): the subset of EMu fields used to perform the match.
            If fields is None, all fields in the source will be considered.
        from_json (bool): specifies whether fields lookup was read from a
            pre-existing JSON file
        module (str): the name of the module
        new (list): records that do not exist in EMu
    """

    def __init__(self, module, include=None, exclude=None):
        print 'Creating attachment search for {}...'.format(module)
        fp = os.path.join('matcher', '{}'.format(module))
        super(Matcher, self).__init__(fp, module=module, container=MinSciRecord)
        self.keep = ['_records', '_fields']
        self.include = INCLUDE.get(module, []) if include is None else include
        self.exclude = EXCLUDE.get(module, []) if exclude is None else exclude
        self.transformations = TRANSFORMATIONS.get(module, {})
        self.derived = DERIVED.get(module, {})
        self.new = []
        self.write = False
        json_path = os.path.join('matcher', '{}.json'.format(module))
        #os.remove(json_path)
        try:
            self.load(json_path)
        except IOError:
            self._records = {}
            self._fields = []
            fp = os.path.join('matcher', module)
            self.fast_iter(report=10000)
            self._fields = list(set(self._fields))
            print self._fields
            self.save(json_path)
        self._fields.sort()


    def iterate(self, element):
        """Populate dict used for matching"""
        rec = self.parse(element)
        # HACK: Skip sites if given by collector
        if (self.module == 'ecollectionevents'
                and rec('LocSiteNumberSource') == 'Collector'):
            return True
        irn = rec.pop('irn')  # IRN will never be included in the match set
        key = self.keyer(rec)
        self._fields.extend(rec.keys())
        if key:
            data = self.container({'irn': irn})
            self._records.setdefault(key, []).append(data)
        else:
            raise ValueError(rec)


    def keyer(self, rec):
        """Format a value as a standard key to use for matching

        Args:
            rec (XMuRecord): the record to match or match against

        Returns:
            A JSON-encoded string representing the desired fields from
            the source record
        """
        # Prune a copy of the source record, then remove any key that does
        # not appear in the fields attribute.
        rec.prune()
        for key in rec.keys():
            if ((self.include and not key in self.include)
                    or key in self.exclude):
                del rec[key]
            elif self.transformations:
                try:
                    rec[key] = self.transformations[key](rec[key])
                except KeyError:
                    pass
        return json.dumps(rec, sort_keys=True).lower()


    def match(self, match_data, match_once=False):
        """Match record against the existing record set

        Args:
            match_data (dict): object data
            match_once (bool): if true, the record in the match dictionary
                will be deleted once it is matched

        Returns:
            Record modified to to include irn if match can be made
        """
        # No need to match if any IRN is provided or if there are no records
        # to match against, so check those parameters first.
        irn = match_data.get('irn')
        if irn is not None:
            return self.container({'irn': irn})
        elif not self._records:
            return self._prepare(match_data)
        else:
            # Check for a match
            key = self.keyer(self.container(match_data).expand())
            if key:
                try:
                    irn = self._records[key][0]
                except (IndexError, KeyError):
                    rec = self._prepare(match_data)
                    try:
                        del rec['irn']
                    except KeyError:
                        pass
                    if not rec in self.new:
                        self.new.append(rec)
                    return rec
                else:
                    if match_once:
                        del self._records[key][0]
                    return irn
            return None


    def attach(self, rec, fields, mapper):
        """Attach a record from another module to the provided record

        Args:
            rec (XMuRecord): an expanded XMu record
            mapper (Mapper): a Mapper object for the current record
        """
        # Note: bad matches can be made if the record being matched includes
        # fields that are not accounted for in the Matcher object.
        root = True
        if is_reference(mapper(fields[0])[0]):
            root = False
        match_data = {}
        for field in fields:
            try:
                match_data[field] = copy.deepcopy(rec[field])
                if not root:
                    del rec[field]
            except KeyError:
                pass
        if match_data:
            mapper.expand(match_data)
            if not root:
                attach_field = match_data.keys()[0]
                match_data = match_data[attach_field]
            else:
                attach_field = 'irn'
            if isinstance(match_data, list):
                attachment = [self.match(row, root)
                              for row in match_data if row]
            else:
                attachment = self.match(match_data, root)
            if any(attachment) and not all(attachment):
                raise Exception('Row {}: Bad attachment on'
                                ' {}'.format(rec['_RowNumber'], attach_field))
            return attachment


    def _prepare(self, rec):
        """Fill out an EMu record to include all fields used to match

        Args:
            rec (xmu.DeepDict): object data
        """
        if self.module == 'etaxonomy':
            rec.setdefault('ClaCurrentlyAccepted', 'Unknown')
        # Explicitly include the fields that should be empty. Fields that
        # we don't want to use as part of the match (as defined by the include
        # and exclude attributes) are also removed here.
        for key in self._fields:
            try:
                rec[key]
            except KeyError:
                pass #rec_key = [] if is_table(key) else u''
            if ((self.include and not key in self.include)
                    or key in self.exclude):
                del rec[key]
        # Expand into a full EMu record
        rec = self.container(rec).expand()
        # EMu does not automatically exclude inactive records, so we need to
        # specify that we only want active records in both the base record
        # and any references therein. Only goes one deep right now.
        rec['SecRecordStatus'] = 'Active'
        for field in [field for field in rec if is_reference(field)]:
            if rec[field]:
                try:
                    if not 'irn' in rec[field]:
                        rec[field]['SecRecordStatus'] = 'Active'
                except TypeError:
                    for i in xrange(len(rec[field])):
                        if not 'irn' in rec[field][i]:
                            rec[field][i]['SecRecordStatus'] = 'Active'
        # Look for derivative fields. EMu includes a handful of groups of
        # related fields that are derived from each other (coordiantes,
        # elevation, and depth). Matching against these fields is a problems
        # because it's unlikely that the import will include more than one,
        # so we check for those here.
        for sources in self.derived:
            keep = u''
            for src in sources:
                if rec.get(src) is not None:
                    keep = src
                    for derived in [fld for fld in sources if not fld == keep]:
                        try:
                            del rec[derived]
                        except KeyError:
                            pass
                    break
        return rec


def rower(rec, cols):
    """Group data from different fields into rows"""
    rows = []
    for col in cols:
        for i, val in enumerate(rec.get(col, [])):
            try:
                rows[i][col] = val
            except IndexError:
                rows.append({col: val})
    return rows
