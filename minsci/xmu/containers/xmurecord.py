"""Subclass of DeepDict with methods specific to XMu"""

import re
from collections import namedtuple
from datetime import datetime
from itertools import izip_longest
from pytz import timezone

from dateparser import parse

from ...deepdict import DeepDict


class XMuRecord(DeepDict):
    """Contains methods for reading data from EMu XML exports"""

    def __init__(self, *args):
        super(XMuRecord, self).__init__(*args)
        self.tabends = ('0', '_nesttab', '_nesttab_inner', '_tab')
        self.refends = ('Ref', 'Ref_tab')
        self._attributes = ['fields', 'module']
        # Set defaults for carryover attributes
        for attr in self._attributes:
            setattr(self, attr, None)


    def __call__(self, *args, **kwargs):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        return self.smart_pull(*args)


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


    def smart_pull(self, *args, **kwargs):
        """Pull data from the record, formatting the result based on the path

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg

        Returns:
            Value for the given path, formatted as follows:
                An atomic field returns a string
                A reference pointing to a single field returns a string
                A simple table returns a list of values
                A reference table that specifies a field returns a list
                A reference table returns a list of XMuRecord objects
                A nested table returns a list of lists
        """
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
            try:
                val = self.pull(*args, **kwargs)
            except KeyError:
                retval = u''
            else:
                retval = val if val is not None else u''
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
                    val.module = field_data['schema']['RefTable']
            else:
                retval.module = field_data['schema']['RefTable']
        # Verify path against the schema if no value is returned. A failed
        # call does not itself return an error because not all fields will
        # be present in all records.
        if not retval:
            path = [self.module] + list(args)
            try:
                self.fields.get(*path)
            except AttributeError:
                pass
            except KeyError:
                raise KeyError('/'.join(args))
        # Last check
        if retval is None:
            raise TypeError
        return retval


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
        for i in xrange(len(args)):
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
                    rows.extend(row.values())
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
        rows = izip_longest(labels, values)
        match = standardize(match)
        return [val for label, val in rows if standardize(label) == match]


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


    def get_note(self, kind):
        """Return the note matching the given kind"""
        return self.get_matching_rows(kind,
                                      'NotNmnhType_tab',
                                      'NotNmnhText0')


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


    def get_current_weight(self, mask=''):
        weight = self('MeaCurrentWeight').rstrip('0.')
        unit = self('MeaCurrentUnit')
        if weight and unit:
            if '.' in weight:
                weight = float(weight)
                return '{weight:.2f} {unit}'.format(weight=weight, unit=unit)
            else:
                weight = int(weight)
                return '{weight:,} {unit}'.format(weight=weight, unit=unit)
        return ''


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
        """Get value from the GUID table for a given key

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
        if len(matches) > 1 and not allow_multiple:
            raise Exception('Multiple values found for {}'.format(kind))
        if allow_multiple:
            return matches
        else:
            try:
                return matches[0]
            except IndexError:
                return None


    def get_url(self):
        """Get ark link to this record"""
        ezid = self.get_guid('EZID')
        if ezid:
            return 'http://n2t.net/{}'.format(ezid)


    def wrap(self, module):
        """Wrap the XMuRecord with name of module

        Args:
            module (str): name of module to use as key

        Returns:
            Wrapped XMuRecord. In a typical use case, this means the paths
            used to retrieve data need to include the module name.
        """
        return self.clone({module: self})


    def unwrap(self):
        """Remove outermost level of XMuRecord

        This simplifies the paths needed to pull data from the record. The
        record will need to be wrapped again before writing to XML.

        Returns:
            Unwrapped XMuRecord. In a typical use case, this means the paths
            used to retrieve data do not need to include the module name.
        """
        return self[self.keys()[0]]


    def expand(self):
        """Expand a flattened record"""
        # Clear pre/append logic if record is not an update
        try:
            self['irn']
        except KeyError:
            update = False
        else:
            update = True
        # Empty atoms should be excluded from appends; they show up as empty
        # tags and will therefore erase any value currently in the table.
        # Also strips append markers from records that do not include an irn.
        for key in self.keys():
            if key.endswith(')') and not self[key]:
                del self[key]
            elif not update:
                k = key.rsplit('(', 1)[0]
                if k != key:
                    if self[key]:
                        self[k] = self[key]
                    del self[key]
        # Expand shorthand keys, including tables and simple references.
        # Keys pointing to other XMuRecord objects are left alone.
        for key in self.keys():
            val = self[key]
            k = key.rsplit('(', 1)[0]               # key stripped of row logic
            base = key.split('_', 1)[0].rstrip('(0+)') # key without table info
            # Confirm that all tables are lists
            if key.endswith(('0', 'tab', ')')) and not isinstance(val, list):
                raise ValueError('{} must be a list'.format(key))
            if k.endswith('_nesttab'):
                # Test if the table has already been expanded by looking
                # for a corresponding _nesttab_inner key
                try:
                    expanded = k + '_inner' in val[0].keys()
                    #expanded = k + '_inner' in val.keys()
                except (AttributeError, IndexError):
                    expanded = False
                if not expanded and any(val):
                    if 'Ref_' in k:
                        base = 'irn'
                    self[key] = [self.clone({
                        k + '_inner': [self.clone({base: s}) for s in val]
                        })]
            elif (k.endswith('Ref')
                  and isinstance(val, (int, str, unicode))
                  and val):
                self[key] = self.clone({'irn': val})
            elif k.endswith('Ref'):
                try:
                    self[key].expand()
                except AttributeError:
                    self[key] = self.clone(self[key]).expand()
            elif (k.endswith('Ref_tab')
                  and isinstance(val, list)
                  and any(val)
                  and isinstance(val[0], (int, str, unicode))):
                self[key] = [self.clone({'irn': s}) if s
                             else self.clone() for s in val]
            elif (k.endswith('Ref_tab')
                  and isinstance(val, list)
                  and any(val)):
                try:
                    self[key] = [self.clone(d).expand() for d in val]
                except TypeError:
                    raise
            elif (k.endswith(self.tabends)
                  and isinstance(val, list)
                  and any(val)
                  and isinstance(val[0], (int, str, unicode))):
                self[key] = [self.clone({base: s}) for s in self[key]]
            elif (k.endswith(self.tabends)
                  and isinstance(val, list)
                  and not any(val)):
                self[key] = []
        return self


    def to_refine(self):
        Row = namedtuple('Row', ['irn', 'field', 'row', 'val'])
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
                print key, vals, type(val)
        return rows


    def zip(self, *args):
        return izip_longest(*[self(arg) for arg in args])




def standardize(val):
    """Standardize the format of a value"""
    return re.sub(r'[\W]', u'', val.upper()).upper()
