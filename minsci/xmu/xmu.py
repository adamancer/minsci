"""Reads and writes XML formatted for Axiell EMu"""
import glob
import hashlib
import json
import os
import re
from collections import namedtuple
from datetime import datetime

from lxml import etree

from .constants import FIELDS
from .containers import XMuRecord
from .fields import is_table, is_reference
from ..exceptions import RowMismatch
from ..helpers import cprint


Grid = namedtuple('Grid', ['fields', 'operator'])


class XMu(object):
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

    def __init__(self, path, fields=None, container=None, module=None):
        # Class-wide switches
        self.path = path
        self.keep = []
        self.verbose = False
        self.module = module
        self.from_json = False

        # Create a fields object based on the path if none provided
        if fields is None:
            fields = FIELDS
        self.fields = fields

        # DeepDict or subclass to use as container for EMu data
        if container is None:
            container = XMuRecord
        self._attributes = ['fields', 'module']
        self._container = container

        self.xpaths = []
        self.newest = []
        self._files = []
        self._paths_found = {}

        # Walk through a directory
        if path is None:
            xpaths = []
        elif os.path.isdir(path):
            self._files = [fp for fp in glob.glob(os.path.join(path, '*.xml'))]
            self._files.sort(key=lambda fp: os.path.getmtime(fp), reverse=True)
            xpaths = []
            for fp in self._files:
                xpaths.extend(self.fields.read_fields(fp))
            xpaths = list(set(xpaths))
        elif path.endswith('.xml'):
            xpaths = self.fields.read_fields(path)
            self._files = [path]
        else:
            raise Exception('Invalid path: {}'.format(path))
        # Check that all xpaths are valid according to schema
        remove = []
        for xpath in xpaths:
            path = xpath.split('/')
            try:
                self.fields(*path)
            except NameError:
                logger.warning('Removed invalid path: {}'.format(xpath))
                remove.append(path)
        self.xpaths = [xpath for xpath in xpaths if not xpath in remove]
        # Record basic metadata about the import file
        if xpaths or self.module is None:
            self.module = self.xpaths[0].split('/')[0]
            self.newest = max([os.path.getmtime(fp) for fp in self._files])
        self._paths_found = {}


    def parse(self, element):
        """Converts XML record to XMu dictionary"""
        rec = self.read(element).unwrap()
        rec.finalize()
        return rec


    def container(self, *args):
        """Wraps dict in custom container with attributes needed for export"""
        container = self._container(*args)
        for attr in self._attributes:
            setattr(container, attr, getattr(self, attr, None))
        container.finalize()
        return container


    def set_carryover(self, *args):
        """Update the list of carryover attributes"""
        self._attributes = args


    def iterate(self, element):
        """Placeholder for iteration method"""
        raise Exception('No iterate method is defined for this subclass')


    def finalize(self):
        """Placeholder for finalize method run at end of iteration"""
        pass


    def fast_iter(self, func=None, report=0, skip=0, limit=0,
                  callback=None, callback_kwargs=None, **kwargs):
        """Use callback to iterate through an EMu export file

        Args:
            func (function): name of iteration function
            report (int): number of records at which to report
                progress. If 0, no progress report is made.
            skip (int): number of records to skip before processing
            limit (int): number of record at which to stop processing the file
            callback (function): name of function to run upon completion

        Returns:
            Boolean indicating whether the entire file was processed
            successfully.
        """
        if func is None:
            func = self.iterate
        keep_going = True
        n_processed = -skip
        n_success = 0
        if skip:
            logger.info('Skipping the first {:,} records'.format(skip))
        if report:
            starttime = datetime.now()
        for fp in self._files:
            if report:
                logger.info('Reading {}...'.format(fp))
            context = etree.iterparse(fp, events=['end'], tag='tuple')
            for _, element in context:
                # Process children of module table only
                parent = element.getparent().get('name')
                if parent is not None and parent.startswith('e'):
                    n_processed += 1
                    if n_processed <= 0:
                        continue
                    result = func(element, **kwargs)
                    if result is False:
                        keep_going = False
                        break
                    elif result is not True:
                        n_success += 1
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
                    if report:
                        starttime = self._report(report,
                                                 n_processed,
                                                 n_success,
                                                 starttime)
                    if limit and not n_processed % limit:
                        logger.warning('Stopped processing before end of file'
                                       ' (limit={:,} records)'.format(limit))
                        keep_going = False
                        break
            del context
            if not keep_going:
                break
        print(('{:,} records processed!'
               ' ({:,} successful)').format(n_processed, n_success))
        self.finalize()
        if callback is not None:
            if callback_kwargs is None:
                callback_kwargs = {}
            callback(**callback_kwargs)
        return True


    def _report(self, report, n_processed, n_success, starttime):
        now = datetime.now()
        elapsed = now - starttime
        by_count = isinstance(report, int)
        if not by_count:
            report = int(report.rstrip('s'))
        if ((by_count and not n_processed % report)
            or (not by_count and (report - elapsed.total_seconds()) < 0)):
                mask = '{:,} records processed! ({:,} successful, t={}s)'
                print(mask.format(n_processed, n_success, elapsed))
                return now
        return starttime


    def autoiterate(self, keep=None, **kwargs):
        """Automatically iterates over the source file and caches the result"""
        if keep is None and self.keep:
            keep = self.keep
        if keep is not None:
            self.keep = keep
            try:
                self.load(**kwargs.get('callback_kwargs', {}))
            except (IOError, OSError, ValueError):
                callback = kwargs.pop('callback', self.save)
                self.fast_iter(callback=callback, **kwargs)
        else:
            self.fast_iter(**kwargs)


    def save(self, fp=None, encoding='utf-8'):
        """Save attributes listed in the self.keep as json"""
        if fp is None:
            fp = os.path.splitext(self.path)[0] + '.json'
        logger.info('Saving data to {}...'.format(fp))
        data = {key: getattr(self, key) for key in self.keep}
        with open(fp, 'w', encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=False, cls=ABCEncoder)


    def load(self, fp=None, encoding='utf-8'):
        """Load data from json file created by self.save"""
        if fp is None:
            fp = os.path.splitext(self.path)[0] + '.json'
        # Always recreate the JSON if XML is newer
        if os.path.getmtime(fp) <= os.path.getmtime(self.path):
            raise IOError
        logger.info('Reading data from {}...'.format(fp))
        with open(fp, 'r', encoding=encoding) as f:
            data = json.load(f)
        for attr, val in data.items():
            setattr(self, attr, val)
        self.from_json = True


    def set_keep(self, fields):
        """Sets the attributes to load/save when using JSON functions"""
        self.keep = fields


    def read1(self, root, keys=None, result=None, counter=None):
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
            # Check for unnamed tuples, which represent rows inside a table
            if name is None:
                path = tuple(keys)
                try:
                    counter[path] += 1
                except KeyError:
                    counter[path] = 0
                name = counter[path]
            keys.append(name)
            if not len(child):
                # lxml always returns ascii-encoded strings in Python 2, so
                # so convert to unicode here
                val = str(child.text) if child.text is not None else u''
                if child.tag == 'table':
                    # Handle empty tables. These happen with nested tables
                    # and possibly elsewhere.
                    result.push([], *keys)
                elif val == '\n      ' and isinstance(keys[-1], int):
                    # Handle gaps in reference tables
                    keys.append(None)
                    result.push(None, *keys)
                    keys.pop()
                else:
                    # Strip double spaces
                    while '  ' in val:
                        val = val.replace('  ', ' ')
                    result.push(val.strip(), *keys)
            else:
                result = self.read(child, keys, result)
            keys.pop()
        return result


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
        if counter is None:
            counter = {}
        if result is None:
            result = self.container()
            result[self.module] = self.container()
            self.read(root, keys, result[self.module], counter)
            return result
        for child in root:
            # Process nodes with populated descendants
            name = child.get('name')
            # Skip nodes with no populated descendants. This gets around
            # some bad XML reported by EMu for certain empty attachments,
            # but introduces a bug where empty cells are not read correctly.
            if (name is not None
                and name.endswith(('Ref', 'Ref_tab'))
                and not any([s.strip() for s in child.itertext()])):
                    continue
            # Check for unnamed tuples, which represent rows inside a table
            if name is None:
                path = tuple(keys)
                try:
                    counter[path] += 1
                except KeyError:
                    counter[path] = 0
                name = counter[path]
            keys.append(name)
            if not len(child):
                # lxml always returns ascii-encoded strings in Python 2, so
                # so convert to unicode here
                val = str(child.text) if child.text is not None else u''
                if child.tag == 'table':
                    # Handle empty tables. These happen with nested tables
                    # and possibly elsewhere.
                    result[name] = []
                elif val == '\n      ' and isinstance(keys[-1], int):
                    # Handle gaps in reference tables
                    keys.append(None)
                    try:
                        result[name] = None
                    except IndexError:
                        # Catches error if tuple is completely empty
                        result.append(self.container())
                    keys.pop()
                else:
                    # Strip double spaces
                    while '  ' in val:
                        val = val.replace('  ', ' ')
                    try:
                        result[name] = val.strip()
                    except IndexError:
                        # This exception catches an empty first row in
                        # a nested table
                        result.append(val.strip())
            else:
                if isinstance(name, int):
                    try:
                        result.append(self.container())
                    except IndexError:
                        result = [self.container()]
                    self.read(child, keys, result[-1])
                elif name.endswith(('0', '_tab', '_inner', '_nesttab')):
                    result[name] = []
                    self.read(child, keys, result[name])
                else:
                    result[name] = self.container()
                    self.read(child, keys, result[name])
            keys.pop()
        return result


    def find(self, rec, *args):
        """Return value(s) for a given path in the EMu XML export

        Args:
            rec (lxml.etree.ElementTree): XML formatted for EMu
            *args (str): strings comprising the path to a field

        Returns:
            String (for atomic field) or list (for table) containing
            value(s) along the path given by *args. Blank rows that
            follow the last populated row in a table are not populated!
        """
        xpath = self.fields('.'.join(args), self.module)['xpath']
        results = []
        for child in rec.xpath(xpath):
            if child.text:
                text = str(child.text)
                results.append(text)
            else:
                results.append(u'')
        self._paths_found.setdefault(xpath, []).append(len(results))
        # Convert atoms to unicode
        if not 'table' in xpath:
            try:
                results = results[0]
            except IndexError:
                results = u''
        return results


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
        if action not in ['append', 'fill', 'replace']:
            raise Exception('Invalid action: {}'.format(action))
        if new_val == old_val:
            return None, True
        elif action == 'fill' and not old_val:
            return new_val, False
        elif action == 'append':
            table = self.fields(path)['table']
            if table:
                return new_val, True
            else:
                return old_val.rstrip('; ') + ';' + new_val, False
        elif action == 'replace':
            return new_val, False




class ABCEncoder(json.JSONEncoder):

    def __init__(self, *args, **kwargs):
        super(ABCEncoder, self).__init__(*args, **kwargs)


    def default(self, abc):
        try:
            return abc.obj
        except AttributeError:
            return json.JSONEncoder.default(self, abc)




def check_table(rec, *args):
    """Check that the columns in a table are all the same length"""
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
    if len(set([len(arg) for arg in args if arg is not None and any(arg)])) > 1:
        raise RowMismatch(args)


def _emuize(rec, root=None, path=None, handlers=None,
            module=None, fields=None, group=None):
    """Formats record in XML suitable for EMu

    Args:
        rec (minsci.xmu.XMuRecord): contains data to be written
        root (lxml.etree.ElementTree): XML document updated as the
            record is written
        path (str):

    Return:
        EMu-formatted XML
    """
    if root is None:
        module = list(rec.keys())[0]
        root = etree.Element('table')
        root.set('name', module)
        root.addprevious(etree.Comment('Data'))
    if path is None:
        path = root.getroottree().getroot().get('name')
        root = etree.SubElement(root, 'tuple')
    if handlers is None:
        handlers = {}
    if fields is None:
        fields = rec.fields
    rec = rec[path]
    if rec is None:
        return root
    # Check if for append, prepend, and replacement operators. If found,
    # determines the necessary attributes and passes it to any immediate
    # children.
    if hasattr(path, 'endswith') and path.endswith(')'):
        path, operator = path.rstrip(')').rsplit('(', 1)
        try:
            table = fields.map_tables[(module, path)]
        except KeyError:
            # Check for tables that aren't being handled
            if path.endswith(('tab', '0')):
                raise ValueError('Unassigned column: {}.{}'.format(module, path))
        except AttributeError:
            pass
        else:
            grid_flds = '|'.join(['|'.join(field) for field in sorted(table)])
            group = Grid(grid_flds, operator)
    if isinstance(rec, (int, float, basestring)):
        atom = etree.SubElement(root, 'atom')
        # Set path to parent if is a row in a table
        if isinstance(path, int):
            path = root.getparent().get('name').rsplit('_', 1)[0].rstrip('0')
        # Test multimedia
        if rec and path in ('Multimedia', 'Supplementary'):
            open(rec, 'rb')
        # Handle empties in the supplementary table. Empties are used as
        # placekeepers but should not themselves be loaded into EMu.
        operator = root.get('row')
        if path == 'Supplementary' and not rec and operator is not None:
            parent = root.getparent()
            parent.remove(root)
            root = parent
        try:
            atom.set('name', path.rstrip('_'))
        except TypeError:
            parent = etree.tostring(root.getparent())
            raise ValueError('Path must be string. Got {} instead. Parent'
                             ' is {}'.format(path, parent))
        try:
            atom.text = str(rec)
        except UnicodeEncodeError:
            atom.text = rec
        except ValueError:
            print(rec)
            raise
    else:
        try:
            paths = list(rec.keys())
        except AttributeError:
            paths = [i for i in range(len(rec))]
        if isinstance(path, int):
            root = etree.SubElement(root, 'tuple')
            # Add append attributes if required
            if group is not None:
                hashval = (group.fields + '|{}'.format(path)).encode('utf-8')
                hashed = hashlib.md5(hashval).hexdigest()
                operator = group.operator.format(path + 1)
                if not re.match(r'^(\+|\-|\d+=)$', operator):
                    raise ValueError('Illegal operator: {}'.format(operator))
                root.set('row', operator)
                if group.operator == '+':
                    root.set('group', hashed)
                group = None
        elif is_table(path.rstrip('_')):
            root = etree.SubElement(root, 'table')
            root.set('name', path.rstrip('_'))
        elif is_reference(path):
            root = etree.SubElement(root, 'tuple')
            root.set('name', path)
        for path in _sort(paths):
            _emuize(rec, root, path, handlers, module, fields, group)
        # Get parent returns None when you hit the outermost container
        parent = root.getparent()
        if parent is not None:
            root = parent
    return root


def _sort(paths):
    """Forces fields in an export to print in a certain order

    Args:
        path (list): list of paths in the current record set

    Returns:
        Sorted list of paths
    """
    paths.sort()
    rules = {
        'NamOrganisation': ['NamPartyType', 'NamInstitution', 'NamOrganisation'],
        'OpeDateToRun': ['OpeExecutionTime', 'OpeDateToRun', 'OpeTimeToRun'],
        'ClaScientificName': ['ClaScientificNameAuto', 'ClaScientificName']
    }
    for key, group in rules.items():
        if key in paths:
            keep = []
            for path in group:
                try:
                    paths.remove(path)
                except ValueError:
                    pass
                else:
                    keep.append(path)
            paths.extend(keep)
    return paths


def _check(rec, module=None):
    """Validates a record, including tables

    Args:
        rec (dict): object data
        module (str): the backend name of an EMu module

    Returns:
        Clean version of the original record
    """
    # Ensure that the record is an XMuRecord
    if not isinstance(rec, XMuRecord):
        rec = XMuRecord(rec)
    # Ensure that the module attribute is populated
    if module is None:
        module = rec.module
    # Ensure that the fields attribute is populated
    try:
        rec.fields
    except AttributeError:
        rec.fields = FIELDS
    else:
        if rec.fields is None:
            rec.fields = FIELDS
    # Ensure that the record is expanded
    rec.expand()
    # Convert values to XMuStrings and add attributes as needed
    tables = []
    for key in list(rec.keys()):
        try:
            table = rec.fields.map_tables[(module, key.strip('+'))]
        except KeyError:
            # Check for tables that haven't been included as grids
            if key.endswith('tab'):
                logger.warning('Unassigned column: {}'.format(key))
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
    """Checks record set and formats as EMu XML

    Args:
        records (list): list of records
        module (str): name of module
    """
    if module is None:
        module = records[0].module
    root = None
    for rec in records:
        rec = _check(rec, module)
        try:
            root = _emuize(rec.expand().wrap(module), root, module=module)
        except Exception:
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
    if records:
        _writer(fp, emuize(records, module))
    else:
        logger.warning('No records found')


def _writer(fp, root):
    """Write EMu-formatted XML to file

    Args:
        root (lxml.etree.ElementTree): EMu-formatted XML. This can be
            generated using XMu.format().
        fp (str): path to file
    """
    n_records = 1
    for rec in list(root):
        rec.addprevious(etree.Comment('Row {}'.format(int(n_records))))
        n_records += 1
    root.getroottree().write(fp, pretty_print=True,
                             xml_declaration=True, encoding='utf-8')
