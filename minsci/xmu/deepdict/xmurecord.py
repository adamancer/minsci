"""Subclass of DeepDict with methods specific to XMu"""

from .deepdict import DeepDict
from ...exceptions import PathError

class XMuRecord(DeepDict):

    def __init__(self, *args):
        super(XMuRecord, self).__init__(*args)
        self.tabends = ('0', '_nesttab', '_nesttab_inner', '_tab')
        self.fields = None
        self.module = None
        self.found = []


    def __call__(self, *args, **kwargs):
        """Shorthand for XMuRecord.smart_pull(*args)"""
        return self.smart_pull(*args)


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
        """
        # Reference tables return a list of dictionaries, unless a field
        # is specified, in which case they return a list of values
        if [arg for arg in args if arg.endswith('Ref_tab')]:
            retval = self.get_reference(*args, **kwargs)
        # One-dimensional tables return a list of values
        elif [arg for arg in args if arg.endswith(self.tabends)]:
            retval = self.get_rows(*args, **kwargs)
        # Atomic references return a single dictionary, whereas atomic
        # fields return a value
        else:
            try:
                val = self.pull(*args, **kwargs)
            except PathError:
                retval = ''
            else:
                retval = val if val is not None else ''
        # Verify path against the schema if no value is returned. A failed
        # call does not itself return an error because not all fields will
        # be present in all records.
        if not retval:
            path = [self.module] + list(args)
            try:
                self.fields.schema(*path)
            except AttributeError:
                pass
            except KeyError:
                raise PathError('/'.join(args))
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


    def get_rows(self, *args, **kwargs):
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
                break
        if i:
            args = args[:-i]
        try:
            table = self.pull(*args)
        except:
            return []
        else:
            rows = []
            for row in table:
                try:
                    rows.extend(row.values())
                except AttributeError:
                    print args
                    self.pprint()
                    raise
            return rows


    def get_reference(self, *args, **kwargs):
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
        except PathError:
            return []
        else:
            if ref and key is None:
                return ref
            elif ref:
                rows = []
                for row in ref:
                    try:
                        rows.append(row[key])
                    except KeyError:
                        rows.append([])
                return rows


    def wrap(self, module):
        """Wrap the XMuRecord with name of module

        Args:
            module (str): name of module to use as key

        Returns:
            Wrapped XMuRecord. In a typical use case, this means the paths
            used to retrieve data need to include the module name.
        """
        return self.__class__({module: self})


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
        # Empty keys should be excluded from appends; they show up as empty
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
            if k.endswith('_nesttab'):
                # Test if the table has already been expanded by looking
                # for a corresponding _nesttab_inner key
                try:
                    expanded = k + '_inner' in val[0].keys()
                except (AttributeError, IndexError):
                    expanded = False
                if not expanded and any(val):
                    if 'Ref_' in k:
                        base = 'irn'
                    self[key] = [self.__class__({
                            k + '_inner': [self.__class__({base: s})
                                           for s in val]
                        })]
            elif k.endswith('Ref') and isinstance(val, (int, str, unicode)):
                self[key] = self.__class__({'irn': val});
            elif (k.endswith('Ref_tab')
                  and isinstance(val, list)
                  and any(val)
                  and isinstance(val[0], (int, str, unicode))):
                self[key] = [self.__class__({'irn': s}) for s in val];
            elif (k.endswith(self.tabends)
                  and isinstance(val, list)
                  and any(val)
                  and isinstance(val[0], (int, str, unicode))):
                self[key] = [self.__class__({base: s}) for s in self[key]]
        return self


    def flatten(self):
        pass
