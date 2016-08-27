"""Read and write XML for Axiell EMu"""

import collections
import glob
import hashlib
import os
from copy import copy
from datetime import datetime

from lxml import etree

from .deepdict import XMuRecord
from .fields import XMuFields, is_table, is_reference
from ..exceptions import PathError, RowMismatch
from ..helpers import cprint, rprint

FIELDS = XMuFields()

class XMu(object):

    def __init__(self, path, fields=None, container=None, module=None):
        """Read and search XML export files from EMu

        Attributes:
            fields (XMuFields): based on fields kwarg
            module (str): name of base module
            record (dict): the currently active record
            schema (dict): XMuFields.schema
            tables (dict): XMuFields.tables
            verbose (bool): triggers verbose output
            xpaths (list): paths from source file

        Args:
            path (str): path to EMu XML report or directory containing
                multiple reports. If multiple reports are found, they
                are handled from newest to oldest.
            fields (XMuFields): contains data about field
            container (DeepDict): class to use to store EMu data
        """
        # Class-wide switches
        self.verbose = False
        self.module = module

        # Create a fields object based on the path if none provided
        if fields is None:
            fields = FIELDS
        self.fields = fields

        # DeepDict or subclass to use as container for EMu data
        if container is None:
            container = XMuRecord
        self._container = container

        self.xpaths = []
        self.newest = []
        self._files = []
        self._paths_found = {}

        # Handle a directory
        if path is None:
            xpaths = []
        elif os.path.isdir(path):
            self._files = [fp for fp in glob.glob(os.path.join(path,'*.xml'))]
            self._files.sort(key=lambda fp: os.path.getmtime(fp), reverse=True)
            xpaths = []
            for fp in self._files:
                xpaths.extend(self.fields.read_fields(fp))
            xpaths = list(set(xpaths))
        elif path.endswith('.xml'):
            xpaths = self.fields.read_fields(path)
            self._files = [path]
        else:
            raise
        # Check that all xpaths are valid according to schema
        remove = []
        for i in xrange(len(xpaths)):
            path = xpaths[i].split('/')
            try:
                self.fields(*path)
            except:
                cprint('Removed invalid path: {}'.format('/'.join(path)))
                remove.append(path)
        self.xpaths = [xpath for xpath in xpaths if not xpath in remove]
        # Record basic metadata about the import file
        if xpaths or self.module is None:
            self.module = self.xpaths[0].split('/')[0]
            self.newest = max([os.path.getmtime(fp) for fp in self._files])
        self._paths_found = {}


    def container(self, *args):
        container = self._container(*args)
        container.fields = self.fields
        container.module = self.module
        return container


    def fast_iter(self, func, report=0, stop=0, callback=None):
        """Use callback to iterate through an EMu export file

        Args:
            func (function): name of iteration function
            report (int): number of records at which to report
                progress. If 0, no progress report is made.
            stop (int): number of record at which to stop
            callback (function): name of function to run upon completion

        Returns:
            Boolean indicating whether the entire file was processed
            successfully.
        """
        if report:
            starttime = datetime.now()
        n = 0
        for fp in self._files:
            if report:
                cprint('Reading {}...'.format(fp))
            context = etree.iterparse(fp, events=['end'], tag='tuple')
            for event, element in context:
                # Process children of module table only
                parent = element.getparent().get('name')
                if parent is not None and parent.startswith('e'):
                    result = func(element)
                    if result is False:
                        del context
                        return False
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
                    n += 1
                    if report and not n % report:
                        now = datetime.now()
                        dt = now - starttime
                        starttime = now
                        print '{:,} records processed! (t={}s)'.format(n, dt)
                    if stop and not n % stop:
                        del context
                        return False
            del context
        print '{:,} records processed!'.format(n)
        if callback is not None:
            callback()
        return True


    def read(self, root, keys=None, result=None, counter=None):
        """Read an EMu XML record to a dictionary

        This is much faster than iterating through the XMu.xpaths list.

        Args:
            root (lxml.etree): an EMu XML record
            keys (list): parents of the current key
            result (XMuRecord): path-keyed representation of root updated as
                the record is read
            counter (dict): tracks row counts by path

        Returns:
            Path-keyed dictionary representing root
        """
        if keys is None:
            keys = [self.module]
        if result is None:
            result = self.container()
        if counter is None:
            counter = {}
        for child in root:
            name = child.get('name')
            # Check for tuples
            if name is None:
                path = tuple(keys)
                try:
                    counter[path] += 1
                except KeyError:
                    counter[path] = 0
                name = counter[path]
            keys.append(name)
            if not len(child):
                # lxml always returns ascii-encoded strings in Python2, so
                # so convert to unicode here
                val = unicode(child.text) if child.text is not None else u''
                # Handle gaps in tables where the fields are also references
                if val == '\n      ' and isinstance(keys[-1], int):
                    keys.append(None)
                    result.push(None, *keys)
                    keys.pop()
                else:
                    result.push(val.strip(), *keys)
            else:
                result = self.read(child, keys, result)
            keys.pop()
        return result


    def find(self, record, *args):
        """Return value(s) for a given path in the EMu XML export

        Args:
            record (lxml.etree.ElementTree): EMu-formated XML
            *args (str): strings comprising the path to a field

        Returns:
            String (for atomic field) or list (for table) containing
            value(s) along the path given by *args. Blank rows that
            follow the last populated row in a table are not populated!
        """
        xpath = self.fields('.'.join(args), self.module)['xpath']
        results = []
        for child in self.record.xpath(xpath):
            if child.text:
                text = unicode(child.text)
                results.append(text)
            else:
                results.append(u'')
        try:
            self._paths_found[xpath].append(len(results))
        except:
            self._paths_found[xpath]  = [len(results)]
        # Convert atoms to unicode
        if not 'table' in xpath:
            try:
                results = results[0]
            except IndexError:
                results = u''
        return results


    # TODO: Deprecated in favor of below, but need to integrate the handler
    # and validation functions.
    '''
    def write(self, fp, records, module='ecatalogue', handlers=None):
        """Write EMu import file based on records

        Writes both new and update import files; including an irn triggers
        an update. Recordsets can mix and match create and update.

        Args:
            fp (str): path to which to write the import
            records (dict): records to Write
            module (str): module to import to
            handlers (dict): field-keyed dictionary with instructions for
                special handling. Key is the name of the table.
        """
        if handlers is not None:
            orig_handlers = {}
            for key in handlers:
                if handlers[key] == 'append':
                    orig_handlers[key] = {'row': '+'}
                elif handlers[key] == 'overwrite':
                    orig_handlers[key] = {'row': None}
                elif handlers[key] == 'prepend':
                    orig_handlers[key] = {'row': '-'}
                else:
                    rprint('Inavlid handler: {}'.format(key))
        else:
            orig_handlers = {}
        root = etree.Element('table')
        root.set('name', module)
        root.addprevious(etree.Comment('Data'))

        row_num = 1
        for rid in sorted(records.keys(), key=lambda s:str(s).zfill(1024)):
            # Check for irn. If populated, treat as an update, in which the
            # default behavior for fields is overwrite and for tables is
            # group append. This can be overridden using the handlers dict.
            irn_fields = ['{}.irn'.format(module)]
            try:
                irn_fields.append(self.fields(irn_fields[0])['alias'])
            except KeyError:
                pass
            for key in irn_fields:
                try:
                    irn = records[rid][key]
                except KeyError:
                    pass
                else:
                    if bool(irn):
                        update = True
                        break
            else:
                update = False
            # Set up handlers
            handlers = copy(orig_handlers)
            # Rekey to full paths
            row = DeepDict()
            tables = {}
            #print rid
            #cprint(records[rid].keys())
            #print '-' * 60
            for alias in records[rid].keys():
                update_field = update
                # Incude values if populated
                val = records[rid][alias]
                try:
                    orig_path = self.fields(alias)['path']
                except KeyError:
                    # These two prefixes have no exactly corresponding
                    # EMu field and can safely be ignored. Any data
                    # they contain should be mapped as part of validation.
                    if not alias.startswith(('NoEMu', 'RowNumber')):
                        print 'Error: {}'.format(alias)
                        path = '.'.join('.'.split(alias)[:-1])
                        raise
                    continue
                # FIXME: Generalize to all ref tables
                if (orig_path.startswith('ecatalogue.BioEventSiteRef')
                    and orig_path != 'ecatalogue.BioEventSiteRef.ecollectionevents.irn'):
                    update_field = True
                # Check for special handling for tables
                if update_field:
                    keys = [cmp for cmp in orig_path.split('.')  if cmp.endswith(
                            ('0', '_nesttab', '_nesttab_inner', '_tab'))]
                    for key in keys:
                        try:
                            handlers[key]['row']
                        except KeyError:
                            # Exclude inner part of nested tables
                            if not key.endswith('_inner'):
                                handlers.setdefault(key, {})['row'] = '+'
                        except TypeError:
                            # FIXME: This is hacky
                            pass
                try:
                    populated = any(val)
                except TypeError:
                    populated = any(str(val))
                if populated or update_field:
                    # Exclude paths that start with the wrong module
                    if not orig_path.startswith(module):
                        continue
                    path = self.fields.bracketize_path(orig_path)
                    if '{0}' in path:
                        for i in xrange(len(val)):
                            row.push(path.format(i), val[i])
                        if not len(val) and update_field:
                            row.push(path.format(0), '')
                    else:
                        row.push(path, val)
                    # Identify fields that are part of the same table
                    try:
                        table = self.fields(orig_path)['table_fields']
                    except KeyError:
                        pass
                    else:
                        tables.setdefault(hash(table), []).append(orig_path)
            # Get length of longest table
            row_paths = row.pathfinder()
            lengths = []
            for path in row_paths:
                try:
                    lengths.append(max([int(cmp) for cmp in path.split('.')
                                        if cmp.isnumeric()]))
                except ValueError:
                    pass
            try:
                i_max = max(lengths)
            except ValueError:
                i_max = 0
            # Clean up tables
            for key in tables:
                table = tables[key]
                bracketized = [self.fields.bracketize_path(path)
                               for path in table]
                # Fill table based on data from this row
                temp = []
                for path in bracketized:
                    i = 0
                    while i <= i_max:
                        ipath = path.format(i)
                        if ipath in row_paths:
                            temp.append(ipath)
                        i += 1
                table = sorted(list(set(temp)))
                rmpaths = []  # list of paths to delete
                # Check for irn. Delete other reference fields if irn found.
                # This should handle tables automatically.
                irns = [fld for fld in table if fld.endswith('.irn')]
                for irn in irns:
                    prefix = '.'.join(irn.split('.')[:-1]) + '.'
                    rmpaths.extend([path for path in table if not path == irn
                                    and not '.' in path.replace(prefix, '')])
                # Delete completely empty references
                n = len([path for path in table if len(path.split('.')) > 2
                         and 'Ref' in path.split('.')[-3]])
                if n:
                    for path in table:
                        val = row.pull(path)
                        if bool(val):
                            break
                    else:
                        rmpaths.extend(table)
                # Delete everything in rmpaths
                for path in set(rmpaths):
                    row.pluck(path)
            root.append(etree.Comment('Row {}'.format(row_num)))
            record = etree.SubElement(root, u'tuple')
            try:
                self._write(row.keys()[0], row, record, module, handlers)
            except KeyError:
                raise
            row_num += 1
            if not row_num % 100:
                print '{:,} records written!'.format(row_num)
        print '{:,} records written!'.format(row_num)
        root.getroottree().write(fp, pretty_print=True,
                                 xml_declaration=True, encoding='utf-8')
    '''


    def harmonize(self, new_val, old_val, path, action='fill'):
        """Harmonize new values with existing values on the same path

        Args:
            new_val (str): new or replacement value
            old_val (str): existing value
            path (str): path to field in XMuSchema
            action: can be one of 'fill' (add new value if blank), 'append'
                (append new value using either a new row or delimiter), or
                'replace'. The default is fill.

        Returns:
            Tuple containing (revised value, update boolean)
        """
        action = action.lower()
        if not action in ['append', 'fill', 'replace']:
            raise
        if new_val == old_val:
            return None, True
        elif action == 'fill' and not bool(old):
            return new_val, False
        elif action == 'append':
            table = self.fields(path)['table']
            if table:
                return new_val, True
            else:
                return old_val.rstrip('; ') + ';' + new_val, False
        elif action == 'replace':
            return new_val, False


class XMuString(unicode):

    def __init__(self, *args, **kwargs):
        super(XMuString, self).__init__(*args, **kwargs)
        self._dict = {}


    def get(self, key):
        return self._dict[key]


    def set(self, key, val):
        self._dict[key] = val


    def delete(self, key):
        del self._dict[key]


def check_table(rec, *args):
    try:
        return check_columns(*[rec.smart_pull(arg) for arg in args])
    except TypeError:
        rec.pprint()
        raise


def check_columns(*args):
    """Check if columns in the same table are the same length

    Args:
        *args: Lists of value for each column
    """
    if len(set([len(arg) for arg in args if arg is not None and len(arg)])) > 1:
        raise RowMismatch(args)


def _emuize(record, root=None, path=None, handlers=None,
            module=None, fields=None, group=None):
    """Formats record in XML suitable for EMu

    Args:
        record (minsci.xmu.XMuRecord): contains data to be written
        root (lxml.etree.ElementTree): XML document updated as the
            record is written
        path (str):

    Return:
        EMu-formatted XML
    """
    if root is None:
        module = record.keys()[0]
        root = etree.Element('table')
        root.set('name', module)
        root.addprevious(etree.Comment('Data'))
    if path is None:
        path = root.getroottree().getroot().get('name')
        root = etree.SubElement(root, 'tuple')
    if handlers is None:
        handlers = {}
    if fields is None:
        fields = record.fields
    record = record[path]
    # Check if for append, prepend, and replacement operators. If found,
    # determines the necessary attributes and passes it to any immediate
    # children.
    if hasattr(path, 'endswith') and path.endswith(')'):
        path = path.rstrip('(+)')
        try:
            table = fields.map_tables[(module, path)]
        except KeyError:
            # Check for tables that aren't being handled
            if path.endswith('tab'):
                print 'Unassigned column: {}'.format(path)
        except AttributeError:
            pass
        else:
            group = '|'.join(['|'.join(field) for field in sorted(table)])
    if isinstance(record, (int, str, unicode)):
        atom = etree.SubElement(root, 'atom')
        atom.set('name', path.rstrip('_'))
        try:
            atom.text = str(record)  # FIXME
        except UnicodeEncodeError:
            atom.text = record
    else:
        try:
            paths = record.keys()
        except AttributeError:
            paths = [i for i in xrange(len(record))]
        if isinstance(path, (int, long)):
            root = etree.SubElement(root, 'tuple')
            # Add append attributes if required
            if group is not None:
                group = hashlib.md5(group + '|{}'.format(path)).hexdigest()
                root.set('row', '+')
                root.set('group', group)
                group = None
        elif is_table(path):
            root = etree.SubElement(root, 'table')
            root.set('name', path)
        elif is_reference(path):
            root = etree.SubElement(root, 'tuple')
            root.set('name', path)
        for path in _sort(paths):
            _emuize(record, root, path, handlers, module, fields, group)
        # Get parent returns None when you hit the outermost container
        parent = root.getparent()
        if parent is not None:
            root = parent
    return root


def _sort(paths):
    paths.sort()
    if 'OpeDateToRun' in paths:
        group = ('OpeExecutionTime', 'OpeDateToRun', 'OpeTimeToRun')
        for path in group:
            paths.remove(path)
        paths.extend(group)
    return paths



def _check(rec, module=None):
    # Check for irn, formatting the record to update if present
    if module is None:
        module = rec.module
    try:
        rec.fields
    except AttributeError:
        print 'Warning: Could not check tables'
        return rec
    else:
        if rec.fields is None:
            print 'Warning: Could not check tables'
            return rec
    # Convert values to XMuStrings and add attributes as needed
    tables = []
    for key in rec.keys():
        try:
            table = rec.fields.map_tables[(module, key.strip('+'))]
        except KeyError:
            # Check for tables that aren't being handled
            if key.endswith('tab'):
                print 'Unassigned column: {}'.format(key)
            # Convert strings to XMuStrings
            #path, val = rec.smart_drill(key)[0]
            #rec.push(rec.pull(*path), *path)
        else:
            # Assign row and group attributes if appropriate
            fields = [field[1] for field in table]
            if key.endswith('+'):
                fields = [field + '+' for field in fields]
            tables.append(fields)
    # Verify that all columns in tables are the correct length
    for table in tables:
        check_table(rec, *table)
    return rec


def emuize(records, module=None):
    """

    Args:
        records (list): list of records
        module (str): name of module
    """
    if module is None:
        module = records[0].module
    checked = [_check(rec, module) for rec in records]
    root = None
    for rec in checked:
        try:
            root = _emuize(rec.wrap(module), root, module=module)
        except:
            rec.pprint()
            raise
    return root


def write(fp, records, module=None):
    """Convenience function for formatting and writing EMu XML

    Args:
        fp (str): path to file
        records (list): list of XMuRecord() objects
        module (str): name of module
    """
    _writer(fp, emuize(records, module))


def _writer(fp, root):
    """Write EMu-formatted XML to file

    Args:
        root (lxml.etree.ElementTree): EMu-formatted XML. This can be
            generated using XMu.format().
        fp (str): path to file
    """
    n = 1
    for rec in list(root):
        rec.addprevious(etree.Comment('Row {}'.format(int(n))))
        n += 1
    root.getroottree().write(fp, pretty_print=True,
                             xml_declaration=True, encoding='utf-8')
