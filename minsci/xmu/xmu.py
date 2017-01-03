"""Reads and writes XML formatted for Axiell EMu"""

import glob
import hashlib
import json
import os
from collections import namedtuple
from datetime import datetime

from lxml import etree

from .containers import XMuRecord
from .fields import XMuFields, is_table, is_reference
from ..exceptions import RowMismatch
from ..helpers import cprint


FIELDS = XMuFields()
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
            self._files.sort(os.path.getmtime, reverse=True)
            xpaths = []
            for fp in self._files:
                xpaths.extend(self.fields.read_fields(fp))
            xpaths = list(set(xpaths))
        elif path.endswith('.xml'):
            xpaths = self.fields.read_fields(path)
            self._files = [path]
        else:
            raise Exception('Invalid path')
        # Check that all xpaths are valid according to schema
        remove = []
        for xpath in xpaths:
            path = xpath.split('/')
            try:
                self.fields(*path)
            except NameError:
                cprint('Removed invalid path: {}'.format('/'.join(path)))
                remove.append(path)
        self.xpaths = [xpath for xpath in xpaths if not xpath in remove]
        # Record basic metadata about the import file
        if xpaths or self.module is None:
            self.module = self.xpaths[0].split('/')[0]
            self.newest = max([os.path.getmtime(fp) for fp in self._files])
        self._paths_found = {}


    def parse(self, element):
        """Converts XML record to XMu dictionary"""
        return self.read(element).unwrap()


    def container(self, *args):
        """Wraps dict in custom container with attributes needed for export"""
        container = self._container(*args)
        container.fields = self.fields
        container.module = self.module
        return container


    def iterate(self, element):
        """Placeholder for iteration method"""
        raise Exception('No iterate method is defined for this subclass')


    def finalize(self):
        """Placeholder for finalize method run at end of iteration"""
        pass


    def fast_iter(self, func=None, report=0, stop=0, callback=None, **kwargs):
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
        if func is None:
            func = self.iterate
        if report:
            starttime = datetime.now()
        keep_going = True
        n_total = 0
        n_success = 0
        for fp in self._files:
            if report:
                cprint('Reading {}...'.format(fp))
            context = etree.iterparse(fp, events=['end'], tag='tuple')
            for _, element in context:
                # Process children of module table only
                parent = element.getparent().get('name')
                if parent is not None and parent.startswith('e'):
                    n_total += 1
                    result = func(element, **kwargs)
                    if result is False:
                        keep_going = False
                        break
                    elif result is not True:
                        n_success += 1
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
                    if report and not n_total % report:
                        now = datetime.now()
                        elapsed = now - starttime
                        starttime = now
                        print ('{:,} records processed! ({:,}'
                               ' successful, t={}s)').format(n_total,
                                                             n_success,
                                                             elapsed)
                    if stop and not n_total % stop:
                        keep_going = False
                        break
            del context
            if not keep_going:
                break
        print '{:,} records processed! ({:,} successful)'.format(n_total,
                                                                 n_success)
        if callback is not None:
            callback()
        self.finalize()
        return True


    def save(self, fp=None):
        """Save attributes listed in the self.keep as json"""
        if fp is None:
            fp = os.path.splitext(self.path)[0] + '.json'
        print 'Saving data to {}...'.format(fp)
        data = {key: getattr(self, key) for key in self.keep}
        json.dump(data, open(fp, 'wb'))


    def load(self, fp=None):
        """Load data from json file created by self.save"""
        if fp is None:
            fp = os.path.splitext(self.path)[0] + '.json'
        print 'Reading data from {}...'.format(fp)
        data = json.load(open(fp, 'rb'))
        for attr, val in data.iteritems():
            setattr(self, attr, val)
        self.from_json = True


    def set_keep(self, fields):
        """Sets the attributes to load/save when using JSON functions"""
        self.keep = fields


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
                # lxml always returns ascii-encoded strings in Python 2, so
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
                text = unicode(child.text)
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
    if len(set([len(arg) for arg in args if arg is not None and len(arg)])) > 1:
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
        module = rec.keys()[0]
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
    # Check if for append, prepend, and replacement operators. If found,
    # determines the necessary attributes and passes it to any immediate
    # children.
    if hasattr(path, 'endswith') and path.endswith(')'):
        path, operator = path.rstrip(')').rsplit('(', 1)
        try:
            table = fields.map_tables[(module, path)]
        except KeyError:
            # Check for tables that aren't being handled
            if path.endswith('tab'):
                print 'Unassigned column: {}'.format(path)
        except AttributeError:
            pass
        else:
            grid_flds = '|'.join(['|'.join(field) for field in sorted(table)])
            group = Grid(grid_flds, operator)
    if isinstance(rec, (int, long, float, basestring)):
        atom = etree.SubElement(root, 'atom')
        try:
            atom.set('name', path.rstrip('_'))
        except AttributeError:
            parent = etree.tostring(root.getparent())
            raise ValueError('Path must be string. Got {} instead. Parent'
                             ' is {}'.format(path, parent))
        try:
            atom.text = str(rec)  # FIXME
        except UnicodeEncodeError:
            atom.text = rec
    else:
        try:
            paths = rec.keys()
        except AttributeError:
            paths = [i for i in xrange(len(rec))]
        if isinstance(path, (int, long)):
            root = etree.SubElement(root, 'tuple')
            # Add append attributes if required
            if group is not None:
                hashed = (hashlib.md5(group.fields +\
                          '|{}'.format(path)).hexdigest())
                root.set('row', group.operator)
                if group.operator == '+':
                    root.set('group', hashed)
                group = None
        elif is_table(path):
            root = etree.SubElement(root, 'table')
            root.set('name', path)
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
    for key, group in rules.iteritems():
        if key in paths:
            for path in group:
                try:
                    paths.remove(path)
                except ValueError:
                    pass
            paths.extend(group)
    return paths


def _check(rec, module=None):
    """Validate the data in a record, including tables

    Args:
        rec (xmu.DeepDict): object data
        module (str): the backend name of an EMu module

    Returns:
        Clean version of the original record
    """
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
    """Checks record set and formats as EMu XML

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
    if records:
        _writer(fp, emuize(records, module))
    else:
        print 'xmu.write: No records found'


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
