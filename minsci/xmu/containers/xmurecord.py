"""Subclass of DeepDict with methods specific to XMu"""
import logging
logger = logging.getLogger(__name__)

import datetime as dt
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

from nmnh_ms_tools.records import get_catnum

from ..constants import FIELDS
from ..fields import is_tab, is_ref, strip_tab
from ...dicts import DeepDict




Row = namedtuple('Row', ['irn', 'field', 'row', 'val'])
GridInfo = namedtuple('GridInfo', ['rows', 'cols'])




class XMuRecord(DeepDict):
    """Contains methods for reading data from EMu XML exports"""
    delim = '|'


    def __init__(self, *args):
        self._coerce_dicts_to = XMuRecord
        super(XMuRecord, self).__init__(*args)
        self._attributes = ['fields', 'module']
        # Set defaults for carryover attributes
        for attr in self._attributes:
            setattr(self, attr, None)
        self.fields = FIELDS
        self._grids = {}


    def __call__(self, *args):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        return self.smart_pull(*args)


    def __setitem__(self, key, val):
        """Converts non-verbatim dates to datetime objects"""
        if (
            val
            and isinstance(val, str)
            and 'Date' in key
            and 'Verbatim' not in key
        ):
                try:
                    val = dt.datetime.strptime(val, '%Y-%m-%d').date()
                except ValueError:
                    # Leave partial dates as strings
                    pass
        super(XMuRecord, self).__setitem__(key, val)


    @property
    def module(self):
        try:
            assert self._module, 'module attribute is empty'
            return self._module
        except AssertionError as e:
            try:
                return self._guess_module()
            except ValueError:
                raise e


    @module.setter
    def module(self, module):
        self._module = module


    def add(self, path, val, delim='|'):
        if isinstance(path, str):
            path = path.split('/')
        rec = self
        for i, seg in enumerate(path):
            seg_is_tab = is_tab(seg)
            seg_is_ref = is_ref(seg)
            if seg_is_tab and seg_is_ref:
                # This catches lists of irns
                if isinstance(val, list) and all([v.isnumeric() for v in val]):
                    rec.setdefault(seg, []).extend(val)
                # This catches tables with values that don't work with this func
                elif val and i == len(path) - 1:
                    raise ValueError('{}: {}'.format(path, val))
                else:
                    rec.setdefault(seg, []).append(self.clone())
                    rec = rec[seg]
            elif seg_is_ref:
                rec = rec.setdefault(seg, self.clone())
            elif path[-1] == seg:
                vals = []
                if val is not None:
                    vals = [s.strip() for s in val.split(delim)]
                else:
                    val = ''
                rec[seg] = vals if is_tab(seg) else val
            else:
                raise ValueError('{}: {}'.format(path, val))


    def setdefault(self, key, val, delim='|'):
        if '/' in key:
            raise KeyError('Illegal key: {}'.format(key))
        if is_tab(key) and not isinstance(val, list):
            val = [s.strip() for s in val.split(delim)]
        return super(XMuRecord, self).setdefault(key, val)


    def simple_pull(self, path):
        """Returns data from path in DeepDict

        Args:
            path (mixed): the path to an EMu field as a string or list

        Returns:
            Value for the given path
        """
        if isinstance(path, str):
            return self(path)
        else:
            return self(*path)


    def _guess_module(self):
        """Attempts to guess the module if no module attribute set"""
        hints = {
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
        if self._module:
            return self._module
        if len(self) == 1 and list(self.keys())[0] == 'irn':
            return None
        for dct in (hints, FIELDS.module_specific_fields):
            modules = []
            for key in self:
                try:
                    modules.append(dct[key])
                except KeyError:
                    pass
            if len(set(modules)) == 1:
                self.module = modules[0]
                return modules[0]
        raise ValueError('Could not guess module: {}'.format(self))


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
        # Retrieve simple keys
        if args[0].isalpha() and not args[0].endswith('Ref'):
            try:
                return self[args[0]]
            except KeyError:
                pass
        # Split path on period or forward slash if a single arg given
        if len(args) == 1:
            args = re.split(r'[/\.]', args[0])
        else:
            args = list(args)

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
        elif [arg for arg in args if is_tab(arg)]:
            retval = self.get_rows(*args, **kwargs)
        # Atomic references return a single dictionary, whereas atomic
        # fields return a value
        else:
            default = self.clone() if is_ref(args[-1]) else ''
            try:
                val = self.pull(*args, **kwargs)
            except KeyError:
                retval = default
            else:
                retval = val if val is not None else default
        # Update module attribute for references/attachments
        if is_ref(args[-1]):
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
            raise TypeError("Return value cannot be None")
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
            if is_tab(args[-(i+1)]):
                if i:
                    args = args[:-i]
                break
        try:
            table = self.pull(*args)
        except (KeyError, KeyError):
            return []
        else:
            rows = []
            refkey = strip_tab(list(args)[-1])
            for row in table:
                # Confirm that each row is a dict
                try:
                    row.values()
                except AttributeError:
                    # Typically this error results from trying to pull
                    # values from an unexpanded list, so retry after
                    # expanding the record
                    return self.expand().get_rows(*args)
                # Test if row only contains the refkey
                for key in row:
                    if key != refkey:
                        return table
                rows.extend(list(row.values()))
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
        labels = self(label_field)
        values = self(value_field)
        if len(values) < len(labels):
            raise ValueError('Too few values: {}, {}'.format(labels, values))
        rows = zip_longest(labels, values)
        match = standardize(match)
        return [val for label, val in rows if standardize(label) == match]


    def get_accession_number(self, legacy=False):
        """Returns the accession number for a specimen"""
        tranum = self('AcqTransactionRef', 'TraNumber')
        legnum = self('AcqTransactionRef', 'TraLegacyNumber')
        Accession = namedtuple('Accession', ['number', 'legacy_number'])
        return Accession(tranum if tranum else None, legnum if legnum else None)


    def get_identifier(self, include_code=True, include_div=False,
                       force_catnum=False):
        """Derives sample identifier based on record

        Args:
            include_code (bool): specifies whether to include museum code
            include_div (bool): specifies whetehr to include division

        Returns:
            String of NMNH catalog number or Antarctic meteorite number
        """
        ignore = {'MetMeteoriteName'} if force_catnum else {}
        catnum = get_catnum({k: v for k, v in self.items() if k not in ignore})
        if include_div:
            catnum.mask = 'include_div'
        elif include_code:
            catnum.mask = 'include_code'
        return str(catnum)


    def get_catnum(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


    def get_catalog_number(self, include_code=True, include_div=False):
        """Returns the catalog number of the current object"""
        return self.get_identifier(include_code, include_div, force_catnum=True)


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
        raise NotImplementedError


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
                mask = '{weight:.' + str(decimal_places) + 'f} {unit}'
                return mask.format(weight=weight, unit=unit)
            else:
                weight = int(weight)
                return '{weight:,} {unit}'.format(weight=weight, unit=unit)
        return ''


    def get_guid(self, kind='EZID', allow_multiple=False, strip_ark=True):
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
        if kind == 'IGSN':
            args = (kind, 'CatOtherNumbersType_tab', 'CatOtherNumbersValue_tab')
        matches = self.get_matching_rows(*args)
        # Fallback if type not exported
        if not matches:
            if kind.startswith('EZID') and not self('AdmGUIDType_tab'):
                matches = [val for val in self('AdmGUIDValue_tab')
                           if val.startswith('ark:/65665/')]
            elif kind == 'IGSN' and not self('CatOtherNumbersValue_tab'):
                matches = [val for val in self('CatOtherNumbersValue_tab')
                           if re.search(r'^NHB[A-Z0-9]{6}$', val)]
        if len(set(matches)) > 1 and not allow_multiple:
            raise ValueError('Multiple values found for {}'.format(kind))
        if strip_ark and kind.startswith('EZID'):
            arks = {
                'EZID': 'ark:/65665/3',
                'EZIDMM': 'ark:/65665/m3'
            }
            matches = [m[len(arks[kind]):] for m in matches]
        if allow_multiple:
            return matches
        else:
            try:
                return matches[0]
            except IndexError:
                return None


    def get_url(self, kind='EZID'):
        """Gets the ark link to this record"""
        ezid = self.get_guid(kind, strip_ark=False)
        if ezid:
            return 'http://n2t.net/{}'.format(ezid)


    def has_collection(self, collection, starts_with=True):
        """Checks if record belongs to a given collection"""
        collection = collection.lower()
        for coll in self('CatCollectionName_tab'):
            coll = coll.lower()
            if (coll == collection
                or (starts_with and coll.startswith(collection))):
                    return True
        return False


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


    def expand(self, *args, **kwargs):
        """Expands and verifies a flattened record"""
        self._expand(*args, **kwargs)
        self.verify()
        return self


    def coerce(self, val):
        if isinstance(val, list):
            return [self.coerce(val) for val in val]
        elif isinstance(val, (int, float)):
            return str(val)
        return val


    def delete_rows(self, key, indexes=None, conditions=None):
        """Deletes any rows matching the given conditions from a table"""
        assert is_tab(key)
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


    def grid(self, cols, default=''):
        """Creates an XMuGrid object based on this record"""
        key = '|'.join(sorted(cols)).lower()
        try:
            return self._grids[key]
        except KeyError:
            self._grids[key] = XMuGrid(self, cols=cols, default=default)
            return self._grids[key]


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


    def _expand(self, keep_empty=False, keys=None):
        """Expands a flattened record"""
        if keys is None:
            keys = list(self.keys())
        atomic = (dt.date, float, int, str)
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
        for key in keys:
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
        for key in keys:
            val = self.coerce(self[key])
            k = key.rsplit('(', 1)[0]               # key stripped of row logic
            base = key.rstrip('_').split('_', 1)[0].rsplit('(')[0].rstrip('0')
            # Confirm that data type appears to be correct
            if (key.rstrip('_').endswith(('0', 'tab', ')'))
                and not isinstance(val, list)):
                raise ValueError('{} must be a list (={})'.format(key, val))
            elif (val
                  and not key.startswith('_')
                  and not key.rstrip('_').endswith(('0', 'tab', ')', 'Ref'))
                  and not isinstance(val, atomic)):
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
                        # {Field_inner: [...]}
                        vals.append(val)
                    elif (val
                          and isinstance(val, list)
                          and isinstance(val[0], dict)):
                        # [{'irn': 1234567}, {'irn': 1234568}]
                        dicts = [self.clone(s) for s in val]
                        vals.append(self.clone({k + '_inner': dicts}))
                    else:
                        # ['a', 'b', ..., 'z']
                        vals.append(self.clone({k + '_inner': [self.clone({base: s}) for s in val]}))
                self[key] = vals
            elif (k.endswith('Ref')
                  and isinstance(val, atomic)
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
                    if isinstance(val, dt.date):
                        vals.append(self.clone({base: val}))
                    elif isinstance(val, dict) or base in val:
                        vals.append(self.clone(val)._expand(keep_empty=True))
                    else:
                        vals.append(self.clone({'irn': val}))
                self[key] = vals
            elif (is_tab(k.rstrip('_'))
                  and isinstance(val, list)
                  and any(val)
                  and any([isinstance(s, atomic) for s in val])):
                #print('{}={} parsed as mixed grid'.format(key, val))
                # Local table (all unexpanded or a mix)
                vals = []
                for val in val:
                    if isinstance(val, dt.date):
                        vals.append(self.clone({base: val}))
                    elif isinstance(val, dict) or base in val:
                        vals.append(val)
                    else:
                        vals.append(self.clone({base: val}))
                self[key] = vals
            elif (is_tab(k.rstrip('_'))
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




class XMuGrid:
    """Defines methods for working with EMu grids"""

    def __init__(self, rec, cols, default='', label=None):
        self.record = rec
        self.default = default
        self._label = label if label else cols[0]
        # Map table name
        if isinstance(cols, str):
            try:
                module, name = cols.split('.')
            except ValueError:
                module = rec.module
            try:
                cols = [c[1] for c in rec.fields.map_table_names[module][cols]]
            except KeyError:
                pp.pprint(rec.fields.list_tables(module))
                raise KeyError('Table "{}" not found!'.format(cols))
        self.cols = sorted(list(set(cols)))
        self.pad_grid()
        # Warn if column list doesn't match info in table definitions
        refcols = rec.get_table(self.cols[0])
        ref_not_cols = set(refcols) - set(cols)
        if ref_not_cols:
            logger.warning('Missing columns in grid: {}'.format(ref_not_cols))
        cols_not_ref = set(cols) - set(refcols)
        if cols_not_ref:
            logger.warning('Extra columns in grid: {}'.format(cols_not_ref))


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
            return [row[key] for row in self.rows()]
        else:
            return self.row({self.label: key})
        raise KeyError('{} not in grid'.format(key))


    def __delitem__(self, i):
        assert isinstance(i, int)
        self.remove(i)


    @property
    def label(self):
        return self._label


    @label.setter
    def label(self, col):
        if col in self.cols:
            self._label = col
        else:
            raise ValueError('Label column not found: {}'.format(col))


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
        """Forces val to list if going into a nested table"""
        if col.endswith('_nesttab') and not isinstance(val, list):
            return [val]
        return val


    def expand(self):
        """Expands the record following the old ways"""
        self.record.expand()
        missing = sorted(list(set(self.cols) - set(self.record)))
        if missing:
            raise ValueError('Missing columns from grid: {}'.format(missing))
        return self.record


    def info(self):
        """Returns the dimensions and columns in the grid"""
        return GridInfo(len(self), self.cols)


    def rows(self):
        """Converts the grid to a list of dictionaries"""
        #self.expand()
        maxlen = max([len(self.record(col)) for col in self.cols])
        return [XMuRow(self, i) for i in range(maxlen)]


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
            #self.expand()


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


    def pad_row(self, row):
        """Fills in missing keys in a row with the classwide default value"""
        if self.default is not None:
            for col in self.cols:
                row.setdefault(col, self.default)
        return row


    def row(self, row):
        """Returns the row matching the kwargs"""
        return self[self.index(row)]


    def index(self, row):
        """Finds the index of the row matching the given row dict"""
        indexes = {}
        for col, refval in row.items():
            for i, val in enumerate(self.record(col)):
                if val == refval:
                    indexes.setdefault(i, []).append(col)
        # Limit to rows matching all criteria
        indexes = [i for i, cols in indexes.items() if set(cols) == set(row)]
        # Verify matches
        if not indexes:
            raise IndexError('No row matches {}'.format(row))
        if len(indexes) > 1:
            raise IndexError('Multiple rows match {}'.format(row))
        return indexes[0]


    def append(self, row):
        """Appends a row to the grid"""
        row = self.pad_row(**row)
        for col, val in row.items():
            val = self.coerce(col, val)
            self._check_type(col, val)
            self.record[col].append(val)
        #self.expand()


    def extend(self, rows):
        """Appends multiple rows to the grid"""
        for row in rows:
            self.append(**row)


    def insert(self, index, row):
        """Inserts a row into the grid at the given index"""
        if isinstance(index, dict):
            index = self.index(index)
        row = self.pad_row(**row)
        for col, val in row.items():
            val = self.coerce(col, val)
            self._check_type(col, val)
            self.record[col].insert(index, val)
        #self.expand()


    def replace(self, index, row):
        """Replaces the row at the given index"""
        if isinstance(index, dict):
            index = self.index(index)
        row = self.pad_row(**row)
        for col, val in row.items():
            self.record(col)[i] = val
        #self.expand()


    def remove(self, index):
        """Removes the row at the given index"""
        if isinstance(index, dict):
            index = self.index(index)
        for col in self.cols:
            self.pad_col(col)
            del self.record[col][index]
        #self.expand()




class XMuRow(dict):
    """Defines methods for interacting with a row in an EMu grid"""

    def __init__(self, grid, index):
        super(XMuRow, self).__init__()
        self.grid = grid
        self.index = index
        # Populate the row at the given index
        for col in self.grid.cols:
            try:
                val = self.grid.record(col)[self.index]
            except (IndexError, KeyError):
                val = None
            self[col] = val


    def __call__(self, key):
        """Returns value at given key

        Added to maintain consistency with XMuRecord
        """
        return self.get(key, '')


    def __setitem__(self, key, val):
        """Sets item in record as well as row"""
        try:
            self.grid.record[key][self.index] = val
        except IndexError:
            self.grid.record[key].append(val)
        except KeyError:
            self.grid[key] = [val]
        except TypeError:
            raise
        super(XMuRow, self).__setitem__(key, val)




def standardize(val):
    """Standardize the format of a value"""
    if val is None:
        val = ''
    return re.sub(r'[\W]', '', val.upper()).upper()
