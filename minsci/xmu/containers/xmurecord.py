"""Subclass of DeepDict with methods specific to XMu"""
from __future__ import print_function
from __future__ import unicode_literals
from builtins import str
from builtins import range
from past.builtins import basestring

import json
import pprint as pp
import re
from collections import namedtuple
from datetime import datetime
from pytz import timezone
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

from dateparser import parse

from ..constants import FIELDS
from ...dicts import DeepDict


Row = namedtuple('Row', ['irn', 'field', 'row', 'val'])
GridInfo = namedtuple('GridInfo', ['rows', 'cols'])


class XMuRecord(DeepDict):
    """Contains methods for reading data from EMu XML exports"""
    delim = '|'

    def __init__(self, *args):
        super(XMuRecord, self).__init__(*args)
        self._attributes = ['fields', 'module']
        # Set defaults for carryover attributes
        for attr in self._attributes:
            setattr(self, attr, None)
        self.tabends = ('0', '_nesttab', '_nesttab_inner', '_tab')
        self.refends = ('Ref', 'Ref_tab')
        self.fields = FIELDS


    def __call__(self, *args, **kwargs):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        return self.smart_pull(*args)


    def __setitem__(self, key, val):
        """Tests if val contains classwide delimiter before adding to self"""
        if self.delim:
            try:
                delimited = self.delim in json.dumps(val)
            except TypeError:
                pass
            else:
                pass
                #if delimited:
                #    raise ValueError('{} contains {}: {}'.format(key,
                #                                                 self.delim,
                #                                                 val))
        super(XMuRecord, self).__setitem__(key, val)



    '''
    def __getattribute__(self, attr):
        try:
            val = super(XMuRecord, self).__getattribute__(attr)
        except AttributeError:
            if attr == 'fields':
                self.fields = FIELDS
                return FIELDS
            raise
        else:
            if attr == 'fields' and val is None:
                self.fields = FIELDS
                return FIELDS
            return val
    '''


    def finalize(self, *args, **kwargs):
        pass


    def add(self, path, val, delim='|'):
        if isinstance(path, basestring):
            path = path.split('/')
        rec = self
        for i, seg in enumerate(path):
            is_tab = seg.endswith(self.tabends)
            is_ref = seg.endswith(self.refends)
            if is_tab and is_ref:
                # This catches lists of irns
                if isinstance(val, list) and all([v.isnumeric() for v in val]):
                    rec.setdefault(seg, []).extend(val)
                # This catches tables with values that don't work with this func
                elif val and i == len(path) - 1:
                    raise ValueError('{}: {}'.format(path, val))
                else:
                    rec.setdefault(seg, []).append(self.clone())
                    rec = rec[seg]
            elif is_ref:
                rec = rec.setdefault(seg, self.clone())
            elif path[-1] == seg:
                vals = []
                if val is not None:
                    vals = [s.strip() for s in val.split(delim)]
                else:
                    val = u''
                rec[seg] = vals if seg.endswith(self.tabends) else val
            else:
                raise ValueError('{}: {}'.format(path, val))


    def setdefault(self, key, val, delim='|'):
        if '/' in key:
            raise KeyError('Illegal key: {}'.format(key))
        if key.endswith(self.tabends) and not isinstance(val, list):
            val = [s.strip() for s in val.split(delim)]
        return super(XMuRecord, self).setdefault(key, val)


    def simple_pull(self, path):
        """Returns data from path in DeepDict

        Args:
            path (mixed): the path to an EMu field as a string or list

        Returns:
            Value for the given path
        """
        if isinstance(path, basestring):
            return self(path)
        else:
            return self(*path)


    def _guess_module(self):
        """Attempts to guess the module if no module attribute set"""
        # FIXME: Fill out and move to a config file
        keys = {
            'ArtTitle': 'ebibliography',
            'CatPrefix': 'ecatalogue',
            'CatNumber': 'ecatalogue',
            'CatSuffix': 'ecatalogue',
            'LocCountry': 'ecollectionevents',
            'LocStateProvinceTerritory': 'ecollectionevents',
            'LocDistrictCountyShire': 'ecollectionevents',
            'LocTownship': 'ecollectionevents',
            'MulTitle': 'emultimedia',
            'NamLast': 'eparties',
            'NamOrganisation': 'eparties',
            'NamRoles_tab': 'eparties',
            'ShpContactRef': 'eshipments',
            'TraNumber': 'enmnhtransactions'
        }
        try:
            assert self.module
        except AssertionError:
            modules = []
            for key, module in keys.items():
                if self.get(key) is not None:
                    modules.append(module)
            if len(set(modules)) == 1:
                self.module = modules[0]
            else:
                raise


    def smart_pull(self, *args, **kwargs):
        """Pull data from the record, formatting the result based on the path

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg. If args[0] contains one or more dots,
                the path will be expanded from that and ignore subsequent args.

        Returns:
            Value for the given path, formatted as follows:
                An atomic field returns a string
                A reference pointing to a single field returns a string
                A simple table returns a list of values
                A reference table that specifies a field returns a list
                A reference table returns a list of XMuRecord objects
                A nested table returns a list of lists
        """
        self._guess_module()
        if '.' in args[0]:
            args = args[0].split('.')
        # Nested tables need to be handled very carefully
        nested = [arg for arg in args if arg.endswith('_nesttab')]
        if nested:
            args = list(args)
            nesttab = nested[0]
            nesttab_inner = nesttab + '_inner'
            if not nesttab_inner in args:
                args.insert(args.index(nesttab) + 1, nesttab_inner)
            # Split into inner and outer tables
            outer_table = args[:args.index(nesttab_inner)]
            inner_table = args[args.index(nesttab_inner):]
            if not inner_table:
                inner_table = [nesttab.split('_')[0]]
            try:
                retval = [row.get_rows(*inner_table, **kwargs)
                          for row in self.pull(*outer_table)]
            except AttributeError:
                retval = [[]]
            except KeyError:
                retval = [[]]
        # Reference tables return a list of dictionaries, unless a field
        # is specified, in which case they return a list of values
        elif [arg for arg in args if arg.endswith('Ref_tab')]:
            retval = self.get_reference(*args, **kwargs)
            if retval is None:
                retval = []
        # One-dimensional tables return a list of values
        elif [arg for arg in args if arg.endswith(self.tabends)]:
            retval = self.get_rows(*args, **kwargs)
        # Atomic references return a single dictionary, whereas atomic
        # fields return a value
        else:
            default = self.clone() if args[-1].endswith(self.refends) else u''
            try:
                val = self.pull(*args, **kwargs)
            except KeyError:
                retval = default
            else:
                retval = val if val is not None else default
        # Update module attribute for references/attachments
        if args[-1].endswith(self.refends):
            path = [self.module] + list(args)
            field_data = self.fields.get(*path)
            if isinstance(retval, list):
                for val in retval:
                    try:
                        val.module
                    except AttributeError:
                        val = self.clone(val)
                    val.module = field_data['schema'].get('RefTable')
            else:
                retval.module = field_data['schema']['RefTable']
        # Verify path against the schema if no value is returned. A failed
        # call does not itself return an error because not all fields will
        # be present in all records.
        if not retval:
            path = [self.module] + list(args)
            try:
                self.fields.get(*path)
            except KeyError:
                raise KeyError('/'.join(args))
        # Last check
        if retval is None:
            raise TypeError
        return retval


    def is_new(self, found):
        """Checks if current module:irn exists in found

        Args:
            found (dict): marks irns already found as True

        Returns:
            Boolean expressing if the current record has already been seen

        This method can be invoked manually inside the XMu subclass when
        reading XML exports from a directory containing multiple, potentially
        overlapping record sets to prevent (a) the same record from being read
        twice or (b) an older version of a record from overwriting a more
        recent one.
        """
        key = ':'.join([self.module, self('irn')])
        try:
            return not found[key]
        except KeyError:
            found[key] = True
            return True


    def verify(self):
        for path in self.get_paths():
            path.insert(0, self.module)
            path = [seg.rsplit('(', 1)[0].rstrip('_') for seg in path]
            try:
                self.fields.get(*path)
            except KeyError:
                if not [seg for seg in path if seg.startswith('_')]:
                    raise KeyError('/'.join(path))


    def get_paths(self, rec=None, path=None, paths=None):
        if rec is None:
            rec = self
        if path is None:
            path = []
        if paths is None:
            paths = []
        for key in rec:
            path.append(key)
            try:
                child = rec(key)
            except IOError:
                for child in rec:
                    paths = self.get_paths(rec=child, path=path, paths=paths)
            else:
                if isinstance(child, dict):
                    paths = self.get_paths(rec=child, path=path, paths=paths)
                else:
                    paths.append(path[:])
            path.pop()
        return paths



    '''
    def smart_push(self, val, *args):
        """Add value to paths stipulated by args

        Not recommended, needs testing.
        """
        # Confim that paths to tables are valid
        temp = []
        for i in xrange(len(args)):
            temp.append(args[i])
            stripped = args[i].rstrip('+')
            stem = stripped.rsplit('_', 1)[0]
            if (stripped.endswith(self.tabends)
                and not stripped.endswith('Ref_tab')
                and (i == (len(args) - 1) or args[i+1] != stem)):
                temp.append(stem)
        args = temp
        # Process args using a modification of the base pull function
        d = self
        for i in xrange(len(args) - 1):
            arg = args[i]
            append = False
            table = False
            if arg.rstrip('+').endswith(self.tabends):
                table = True
            if arg.endswith('+'):
                append = True
                arg = arg.rstrip('+')
            try:
                d = d[arg]
            except KeyError:
                if table:
                    d[arg] = [self.__class__()]
                    d = d[arg][0]
                else:
                    d[arg] = self.__class__()
                    d = d[arg]
            else:
                # Append to an existing table
                if table and append:
                    d.append(self.__class__())
                # Replace an existing table
                elif table and not append:
                    d = [self.__class__()]
                d = d[-1]
        d[args[-1].rstrip('+')] = val
    '''


    def get_rows(self, *args):
        """Returns a list of values corresponding to the table rows

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg

        Returns:
            List of values, one per row
        """
        # Clean up tables
        for i in range(len(args)):
            if args[-(i+1)].endswith(self.tabends):
                if i:
                    args = args[:-i]
                break
        try:
            table = self.pull(*args)
        except (KeyError, KeyError):
            return []
        else:
            rows = []
            for row in table:
                try:
                    rows.extend(list(row.values()))
                except AttributeError:
                    raise AttributeError('No values attribute found for {}. Try'
                                         ' expanding the record.'.format(args))
            return rows


    def get_reference(self, *args):
        """Returns a list of values corresponding to the table rows

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg.

        Returns:
            If the last arg is a field (as opposed to a reference table),
            this function will return a list of values, one per row. If the
            last arg is a reference table, it will return a list of XMuRecords.
        """
        # Check for key within reference
        key = None
        while not args[-1].endswith(('Ref_tab')):
            key = args[-1]
            args = args[:-1]
        try:
            ref = self.pull(*args)
        except KeyError:
            return []
        else:
            if ref and key is None:
                return ref
            elif ref:
                rows = []
                for row in ref:
                    rows.append(row.get(key, []))
                return rows


    def get_matching_rows(self, match, label_field, value_field):
        """Helper function to find rows in any table matching a kind/label

        Args:
            match (str): the name of the label to match
            label_field (str): field in a table containing the label
            value_field (str): field in a table containing the value

        Returns:
            List of values matching the match string
        """
        labels = self.simple_pull(label_field)
        values = self.simple_pull(value_field)
        rows = zip_longest(labels, values)
        match = standardize(match)
        return [val for label, val in rows if standardize(label) == match]


    def get_accession_number(self, legacy=False):
        """Returns the accession number for a specimen"""
        tranum = self('AcqTransactionRef', 'TraNumber')
        legnum = self('AcqTransactionRef', 'TraLegacyNumber')
        Accession = namedtuple('Accession', ['number', 'legacy_number'])
        return Accession(tranum if tranum else None, legnum if legnum else None)



    def get_location(self, current=False, keyword=None):
        """Returns the current or permanent location of a specimen"""
        locs = self('LocLocationRef_tab' if current else 'LocPermanentLocationRef')
        if not current:
            locs = [locs]
        for i, loc in enumerate(locs):
            try:
                locs[i] = loc['SummaryData']
            except KeyError:
                val = [loc('LocLevel{}'.format(x)) for x in range(1,9)]
                locs[i] = ' - '.join([s for s in val if s]).upper()
        # Filter multiple locations on keyword
        if keyword:
            try:
                return [s for s in locs if keyword.lower() in s.lower()][0]
            except IndexError:
                pass
        return locs[-1]


    def get_date(self, date_from, date_to=None, date_format='%Y-%m-%d'):
        """Returns dates and date ranges

        Args:
            date_from (mixed): path to date from field
            date_to (mixed): path to date to field
            date_format (str): formatting mask for date

        Returns:
            Date or date range as a string
        """
        dates = [self.simple_pull(date_from)]
        if date_to is not None:
            dates.append(self.simple_pull(date_to))
        date_range = []
        for date in [dt for dt in dates if dt]:
            parsed = parse(date).strftime(date_format)
            if not parsed in date_range:
                date_range.append(parsed)
        return ' to '.join(date_range)


    def get_datetime(self, date_from, date_to=None, date_modifier=None,
                     time_from=None, time_to=None, time_modifier=None,
                     conjunction=' to ', format='%Y%m%dT%H%M%S'):
            pass


    def get_notes(self, kind):
        """Return the note matching the given kind"""
        fields = [
            ('NotNmnhType_tab', 'NotNmnhText0'),
            ('NteType_tab', 'NteText0')
        ]
        for note_kind, note_content in fields:
            if note_kind in self and note_content in self:
                return self.get_matching_rows(kind, note_kind, note_content)
        return []


    def get_created_time(self, timezone_id='US/Eastern', mask=None):
        """Gets datetime of record creation"""
        return self._localize_datetime(self('AdmDateInserted'),
                                       self('AdmTimeInserted'),
                                       timezone_id,
                                       mask)


    def get_modified_time(self, timezone_id='US/Eastern', mask=None):
        """Gets datetime of last modification"""
        return self._localize_datetime(self('AdmDateModified'),
                                       self('AdmTimeModified'),
                                       timezone_id,
                                       mask)


    def get_current_weight(self, decimal_places=2):
        """Gets the current weight of the object

        Args:
            decimal_places (int): the number of decimal places to which to
                round the weight

        Returns:
            Unicode-encoded string with the weight and unit, if any
        """
        assert isinstance(decimal_places, int)
        weight = self('MeaCurrentWeight').rstrip('0.')
        unit = self('MeaCurrentUnit')
        if weight and unit:
            if '.' in weight:
                weight = float(weight)
                mask = u'{weight:.' + str(decimal_places) + 'f} {unit}'
                return mask.format(weight=weight, unit=unit)
            else:
                weight = int(weight)
                return u'{weight:,} {unit}'.format(weight=weight, unit=unit)
        return u''


    @staticmethod
    def _localize_datetime(date, time, timezone_id, mask):
        if not (date and time):
            raise ValueError('Both date and time are required')
        iso_datetime = '{}T{}'.format(date, time)
        timestamp = datetime.strptime(iso_datetime, '%Y-%m-%dT%H:%M:%S')
        localized = timezone(timezone_id).localize(timestamp)
        if mask is not None:
            return localized.strftime(mask)
        return localized


    def get_guid(self, kind='EZID', allow_multiple=False):
        """Gets value from the GUID table for a given key

        Args:
            kind (str): name of GUID
            allow_multiple (bool): if False, raises error if multiple
                values with same type are found

        Returns:
            First match from the GUID table for the key (if allow_multiple
            is False) or the full set of matches (if allow_multiple is True)
        """
        args = (kind, 'AdmGUIDType_tab', 'AdmGUIDValue_tab')
        matches = self.get_matching_rows(*args)
        if len(set(matches)) and not allow_multiple:
            raise Exception('Multiple values found for {}'.format(kind))
        if allow_multiple:
            return matches
        else:
            try:
                return matches[0]
            except IndexError:
                return None


    def get_url(self):
        """Gets the ark link to this record"""
        ezid = self.get_guid('EZID')
        if ezid:
            return 'http://n2t.net/{}'.format(ezid)


    def wrap(self, module):
        """Wraps the XMuRecord with name of module

        Args:
            module (str): name of module to use as key

        Returns:
            Wrapped XMuRecord. In a typical use case, this means the paths
            used to retrieve data need to include the module name.
        """
        return self.clone({module: self})


    def unwrap(self):
        """Removes outermost level of XMuRecord

        This simplifies the paths needed to pull data from the record. The
        record will need to be wrapped again before writing to XML.

        Returns:
            Unwrapped XMuRecord. In a typical use case, this means the paths
            used to retrieve data do not need to include the module name.
        """
        return self[list(self.keys())[0]]


    def expand(self, keep_empty=False):
        """Expands and verifies a flattened record"""
        self._expand(keep_empty=keep_empty)
        self.verify()
        return self


    def _expand(self, keep_empty=False):
        """Expands a flattened record"""
        # Clear pre/append logic if record is not an update
        try:
            self['irn']
        except KeyError:
            pass
        else:
            keep_empty = True
        # Empty atoms should be excluded from appends; they show up as empty
        # tags and will therefore erase any value currently in the table.
        # Also strips append markers from records that do not include an irn.
        for key in list(self.keys()):
            if key.endswith(')') and not self[key]:
                del self[key]
            elif not keep_empty:
                k = key.rsplit('(', 1)[0]
                if k != key:
                    if self[key]:
                        self[k] = self[key]
                    del self[key]
            elif key.startswith('_'):
                del self[key]
        # Expand shorthand keys, including tables and simple references.
        # Keys pointing to other XMuRecord objects are left alone.
        for key in list(self.keys()):
            val = self[key]
            k = key.rsplit('(', 1)[0]               # key stripped of row logic
            base = key.rstrip('_').split('_', 1)[0].rsplit('(')[0]
            # Confirm that data type appears to be correct
            if (key.rstrip('_').endswith(('0', 'tab', ')'))
                and not isinstance(val, list)):
                raise ValueError('{} must be a list (={})'.format(key, val))
            elif (val
                  and not key.startswith('_')
                  and not key.rstrip('_').endswith(('0', 'tab', ')', 'Ref'))
                  and not isinstance(val, (basestring, int, float))):
                raise ValueError('{} must be atomic (={})'.format(key, val))
            # Handle nested tables
            if k.endswith('_nesttab'):
                #print('{}={} parsed as nested table'.format(key, val))
                # Nested references are irn only
                if 'Ref_' in k:
                    base = 'irn'
                # Process nested tables as if mixed
                vals = []
                for val in val:
                    # Each val is either a list or a dict
                    if isinstance(val, dict):
                        vals.append(val)
                    else:
                        vals.append(self.clone({k + '_inner': [self.clone({base: s}) for s in val]}))
                self[key] = vals
            elif (k.endswith('Ref')
                  and isinstance(val, (int, str))
                  and val):
                #print('{}={} parsed as atomic reference'.format(key, val))
                self[key] = self.clone({'irn': val})
            elif k.endswith('Ref'):
                #print('{}={} parsed as atomic reference'.format(key, val))
                try:
                    self[key]._expand(keep_empty=True)
                except AttributeError:
                    self[key] = self.clone(self[key])._expand(keep_empty=True)
            elif (k.endswith('Ref_tab')
                  and isinstance(val, list)
                  and any(val)):
                #print('{}={} parsed as reference grid'.format(key, val))
                vals = []
                for val in val:
                    if isinstance(val, dict) or base in val:
                        vals.append(self.clone(val)._expand(keep_empty=True))
                    else:
                        vals.append(self.clone({'irn': val}))
                self[key] = vals
            elif (k.rstrip('_').endswith(self.tabends)
                  and isinstance(val, list)
                  and any(val)
                  and any([isinstance(s, (int, str)) for s in val])):
                #print('{}={} parsed as mixed grid'.format(key, val))
                # Local table (all unexpanded or a mix)
                vals = []
                for val in val:
                    if isinstance(val, dict) or base in val:
                        vals.append(val)
                    else:
                        vals.append(self.clone({base: val}))
                self[key] = vals
            elif (k.rstrip('_').endswith(self.tabends)
                  and isinstance(val, list)
                  and not any(val)):
                #print('{}={} parsed as empty table'.format(key, val))
                # Local table without anything in it
                self[key] = [] if not keep_empty else [{base: s} for s in val]
            elif (isinstance(val, list)
                  and any([v for v in val if isinstance(v, dict)])
                  and any([v for v in val if not isinstance(v, dict)])):
                # Catches mixtures of expanded and unexpanded keys
                self[key] = [val if isinstance(val, dict) else {base: val}
                             for val in self[key]]
            else:
                pass#print('{}={} either atomic or previously parsed'.format(key, val))
        return self


    def to_refine(self):
        """Maps EMu data to Google Refine

        FIXME: Needs to be cleaned up and tested
        """
        irn = self('irn')
        rows = []
        for field in self:
            vals = self(field)
            if isinstance(vals, basestring):
                rows.append(Row(irn, field, None, vals))
            elif isinstance(vals, list):
                for i, val in enumerate(vals):
                    rows.append(Row(irn, field, i + 1, val))
            elif isinstance(vals, XMuRecord):
                # Excludes attachments
                pass
            else:
                print(field, vals, type(val))
        return rows


    def delete_rows(self, key, indexes=None, conditions=None):
        """Deletes any rows matching the given conditions from a table"""
        assert key.endswith(self.tabends)
        assert indexes is not None or conditions is not None
        if indexes is not None:
            if not isinstance(indexes, list):
                indexes = [indexes]
            indexes.sort(reverse=True)
            for i in indexes:
                self.delete_row(key, i)
        else:
            matches = {}
            for field, condition in conditions.items():
                for i, val in enumerate(self(field)):
                    if val == condition:
                        matches.setdefault(field, []).append(i)
            if list(matches.values()):
                values = [set(val) for val in list(matches.values())]
                indexes = list(values[0].intersection(*values))
                indexes.sort(reverse=True)
                for i in indexes:
                    self.delete_row(key, i)
        # Add blank rows for any fields not represented
        for key in self.get_table(key):
            if not self(key):
                self[key] = []


    def delete_row(self, key, i):
        """Deletes the row matching the given index"""
        for field in self.get_table(key):
            try:
                del self[field][i]
            except (IndexError, KeyError):
                pass


    def get_table(self, *path):
        """Returns the table to which the field specified in path belongs"""
        fields = self.fields.get(self.module, *path).get('columns', [])
        return ['/'.join(field[1:]) for field in fields]


    def zip(self, *args):
        """Zips the set of lists, padding each list to the max length"""
        return zip_longest(*[self(arg) for arg in args])


    def grid(self, cols, **kwargs):
        """Creates an XMuGrid object based on this record"""
        return XMuGrid(rec=self, cols=cols, **kwargs)


    def trim(self):
        for key in self:
            val = self(key)
            print(key, val)




class XMuGrid(object):

    def __init__(self, rec, cols, default=''):
        self.record = rec
        self.cols = sorted(list(set(cols)))
        self.default = default
        self.pad_grid()


    def __str__(self):
        return pp.pformat(self.rows())


    def __repr__(self):
        return pp.pformat({col: self.record.get(col, []) for col in self.cols})


    def __iter__(self):
        return iter(self.rows())


    def __len__(self):
        return max([len(self.record.get(col, [])) for col in self.cols])


    def __getitem__(self, key):
        if isinstance(key, int):
            return self.rows()[key]
        elif key in self.cols:
            return self.record[key]
        raise KeyError('{} not in grid'.format(key))


    def __delitem__(self, i):
        self.delete(i)


    @staticmethod
    def _check_type(col, val):
        """Checks type for append"""
        if col.endswith('_nesttab'):
            if not isinstance(val, list):
                raise KeyError('{} must be a list (={})'.format(col, val))
        elif col.endswith('Ref_tab'):
            if not isinstance(val, (int, float, str, dict)):
                raise KeyError('{} must be atomic (={})'.format(col, val))
        elif col.endswith(('0', '_tab')):
            if not isinstance(val, (int, float, str)):
                raise KeyError('{} must be atomic (={})'.format(col, val))
        else:
            raise KeyError('No type check defined for {}'.format(col))


    @staticmethod
    def coerce(col, val=None):
        if col.endswith('_nesttab') and not isinstance(val, list):
            return [val]
        return val


    def expand(self):
        self.record.expand(keep_empty=True)
        missing = set(self.cols) - set(self.record)
        if missing:
            raise ValueError('Missing columns from grid: {}'.format(list(missing)))


    def info(self):
        return GridInfo(len(self), self.cols)


    def rows(self):
        """Converts the grid to a list of dictionaries"""
        self.expand()
        rows = []
        for col in self.cols:
            for i, val in enumerate(self.record(col)):
                try:
                    rows[i][col] = val
                except IndexError:
                    rows.append({col: val})
        return rows


    def grid(self):
        """Returns the grid"""
        grid = self.record.clone({c: self.record(c) for c in self.cols})
        grid['irn'] = '00000000'
        grid.expand()
        del grid['irn']
        return grid


    def pad_grid(self):
        """Pads the grid to the length of the column with the most rows"""
        if self.default is not None:
            num_rows = len(self)
            for col in self.cols:
                self.pad_col(col, num_rows)
            self.expand()


    def pad_col(self, col, num_rows=None):
        """Pads column to the given length or the number of rows in the grid"""
        if self.default is not None:
            if num_rows is None:
                num_rows = len(self)
            diff = num_rows - len(self.record.get(col, []))
            try:
                self.record[col].extend([self.default] * diff)
            except KeyError:
                self.record[col] = [self.default] * num_rows


    def pad_row(self, **kwargs):
        """Fills in missing keys in a row with the classwide default value"""
        if self.default is not None:
            for col in self.cols:
                kwargs.setdefault(col, self.default)
        return kwargs


    def index(self, **kwargs):
        """Finds the index of the row matching the kwargs"""
        indexes = []
        for col, refval in kwargs.items():
            for i, val in enumerate(self.record(col)):
                if val == refval:
                    indexes.append(i)
        if not indexes:
            raise IndexError('No row matches {}'.format(kwargs))
        if len(indexes) > 1:
            raise IndexError('Multiple rows match {}'.format(kwargs))
        return indexes[0]


    def append(self, **kwargs):
        """Appends a row to the grid"""
        kwargs = self.pad_row(**kwargs)
        for col, val in kwargs.items():
            val = self.coerce(col, val)
            self._check_type(col, val)
            self.record[col].append(val)
        self.expand()


    def extend(self, rows):
        """Appends multiple rows to the grid"""
        for row in rows:
            self.append(**row)


    def insert(self, index, **kwargs):
        """Inserts a row into the grid at the given index"""
        kwargs = self.pad_row(**kwargs)
        for col, val in kwargs.items():
            val = self.coerce(col, val)
            self._check_type(col, val)
            self.record[col].insert(index, val)
        self.expand()


    def replace(self, index=None, match_on=None, default='', **kwargs):
        """Replaces the row at the given index"""
        assert index is not None or match_on
        if index is None:
            index = self.index(**match_on)
        kwargs = self.pad_row(**kwargs)
        for col, val in kwargs.items():
            self.recordord(col)[i] = val
        self.expand()


    def delete(self, index=None, **kwargs):
        """Deletes the row at the given index"""
        assert index is not None or kwargs
        if index is None:
            index = self.index(**kwargs)
        for col in self.cols:
            self.pad_col(col)
            del self.record[col][index]
        self.expand()



def standardize(val):
    """Standardize the format of a value"""
    if val is None:
        val = u''
    return re.sub(r'[\W]', u'', val.upper()).upper()
