"""Reads and returns information about EMu's schema"""

import json as serialize
import glob
import os
import re

from ..deepdict import DeepDict
from ..helpers import cprint


class XMuFields(object):
    """Reads and stores metadata about fields in EMu

    Args:
        schema_path (str): path to EMu schema file. If None, looks for
            a copy of the schema stored in files.
        whitelist (list): list of EMu modules to include. If None,
            anything not on the blacklist is included.
        blacklist (list): list of EMu modules to exclude. If None,
            no modules are excluded.
        cache (str): path to cache file. If specified, script will
            check there for a cache file and create one if it isn't found.
        verbose (bool): triggers verbose output

    Attributes:
        schema (dict): path-keyed dicts of field data
        tables (dict): module-keyed lists of paths to tables
        map_tables (dict): path-keyed lists of paths to tables
        verbose (bool): triggers verbose output
    """

    def __init__(self, schema_path=None, whitelist=None, blacklist=None,
                 cache=False, verbose=False):
        self.verbose = verbose
        self._fpath = os.path.join(os.path.dirname(__file__), 'files')
        if cache:
            cache_file = cache
            cprint('Checking for cached XMuFields object...')
            try:
                with open(cache_file, 'rb') as f:
                    fields = serialize.load(f)
            except IOError:
                cprint('No cache found!')
                cache = None  # None is different than False
            except KeyError:
                cprint('Cache is not JSON!')
                cache = None
            else:
                try:
                    self.schema = fields['schema']
                    self.tables = fields['tables']
                    self.map_tables = fields['map_tables']
                    self.hashed_tables = fields['hashed_tables']
                    #self.aliases = fields['aliases']
                except KeyError:
                    print 'Could not read cache!'
        if not cache:
            if schema_path is None:
                schema_path = os.path.join(self._fpath, 'NMNH-schema.pl')
            cprint('Reading EMu schema...')
            # Extend schema based on source file, if specified. This
            # tries to assure that any paths in the source file are included
            # in the resulting XMuFields object.
            self.schema = self._read_schema(schema_path, whitelist, blacklist)
            # Tables are stored as tuples
            self.tables = {}              # maps tables to modules
            self.map_tables = {}          # maps container paths to fields
            self.hashed_tables = {}       # maps hash of tables to tables
            self.tables = self._read_tables()
            self._map_fields_to_tables()  # adds table fields to schema dict
        # Dump fields object as json
        if cache is None:
            cprint('Caching XMuFields object...')
            fields = {
                'schema': self.schema,
                'tables': self.tables,
                'map_tables': self.map_tables,
                'hashed_tables': self.hashed_tables,
                #'aliases': self.aliases,
            }
            with open(cache_file, 'wb') as f:
                serialize.dump(fields, f)
        cprint('Finished reading field data!')


    def __call__(self, *args):
        """Shorthand for :py:func:`~XMuFields.get(*args)`"""
        return self.get(*args)


    def get(self, *args):
        """Return data for an EMu export path

        Modified from DeepDict.pull() to jump to a different module when
        a reference is encountered.

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg

        Returns:
            Dictionary with information about the given path
        """
        d = self.schema
        i = 0
        while i < len(args):
            try:
                d = d[args[i]]
            except KeyError:
                try:
                    d = self.schema[d['schema']['RefTable']]
                except KeyError:
                    raise KeyError('/'.join(args))
            else:
                i += 1
        return d


    def _read_schema(self, fp, whitelist=None, blacklist=None):
        """Reads EMu schema file to dictionary

        See the class for details about the arguments used by this function.

        The EMu schema file includes (but is not limted to) the following:
            ColumnName: Name of field, table, or reference in current module
            DataKind: dkAtom, dkNested, dkTable, dkTuple
            DataType: Currency, Date, Float, Integer, Latitude,
                Longitude, String, Text, Time, UserId, UserName
            ItemName: Field name in current module
            RefLink: Name with Ref
            RefKey: Field used to link with other module
            LookupName: Name of lookup list. Appears only in highest field
                in a given lookup hierarchy.
            LookupParent: The name of next highest field in a lookup hierarchy.

        Returns:
            Dictionary with information about the XML schema
        """
        # Regexes are used to split the .pl file into modules and fields
        re_module = re.compile(r'\te[a-z]+ =>.*?\{.*?\n\t\}', re.DOTALL)
        re_field = re.compile(r"'[A-z].*?\},", re.DOTALL)
        #re_lines = re.compile(r'[A-z].*,', re.DOTALL)
        try:
            with open(fp, 'rb') as f:
                modules = re_module.findall(f.read())
        except OSError:
            raise Exception('{} not found'.format(fp))
        schema = DeepDict()
        for module in sorted(list(modules)):
            module_name = module.split('\n')[0].strip().split(' ')[0]
            # Check module name against whitelist and blacklist
            if (blacklist is not None and module_name in blacklist
                    or whitelist is not None and not module_name in whitelist):
                continue
            schema[module_name] = {}
            fields = re_field.findall(module)
            for field in fields:
                schema_data = {}
                lines = [s.strip() for s in field.split('\n')
                         if bool(s.strip())]
                #field_name = lines[0].split(' ')[0].strip('"\'')
                lines = lines[2:len(lines)-1]
                for line in lines:
                    try:
                        key, val = [s.strip('",\'') for s in line.split(' => ')]
                    except ValueError:
                        pass
                    else:
                        schema_data[key] = val.decode('cp1252')
                schema_data['ModuleName'] = module_name
                # ItemName appears only for fields that are editable in EMu
                # (I think), so use it to cull copy fields, etc.
                try:
                    schema_data['ItemName']
                except KeyError:
                    #cprint('Skipped {}.{}'.format(module_name, field_name))
                    continue
                # Get additional information about this field
                path = self._derive_path(schema_data)
                field_data = {
                    'path': '/'.join(path),
                    'table': is_table(*path),
                    'schema': schema_data
                }
                schema.push(field_data, *path)
        return schema


    @staticmethod
    def _derive_path(schema_data):
        """Derive full path to field based on EMu schema

        Args:
            schema_data (dict): field-specific data from the EMu schema file

        Returns:
            String with slash-delimited path
        """
        path = [schema_data['ModuleName']]
        for key in ['ColumnName', 'ItemName', 'ItemBase']:
            try:
                val = schema_data[key]
            except KeyError:
                pass
            else:
                # Nested tables
                if path[-1].endswith('_nesttab'):
                    path.append(val.rstrip('0') + '_nesttab_inner')
                    if not val.endswith(('0', 'Ref')):
                        path.append(val)
                # Skip ItemName for references. This allows their
                # paths to match the EMu import/export schema.
                elif not (val.endswith('Ref') and key == 'ItemName'):
                    path.append(val)
        # Reworked dedupe function to check against preceding value
        keep = [i for i in xrange(len(path)) if not i or path[i] != path[i-1]]
        return tuple([path[i] for i in keep])


    def _read_tables(self):
        """Read data about tables from text files in files/tables"""
        tables = {}
        for fp in glob.iglob(os.path.join(self._fpath, 'tables', 'e*.txt')):
            module_name = os.path.splitext(os.path.basename(fp))[0]
            _tables = {}
            with open(fp, 'rb') as f:
                for line in [line.strip() for line in f.read().splitlines()
                             if ',' in line and not line.startswith('#')]:
                    table, column = line.split(',')
                    column = (module_name, column)
                    _tables.setdefault(table, []).append(column)
                    # Map nested tables as well
                    if column[1].endswith('_nesttab'):
                        table += 'Inner'
                        column = (column[0], column[1], column[1] + '_inner')
                        _tables.setdefault(table, []).append(column)
            for table in _tables.values():
                self.add_table(table)
            tables[module_name] = [tuple(sorted(t)) for t in _tables.values()]
        return tables


    '''
    def _map_tables(self):
        """Update path-keyed table map"""
        cprint('Mapping tables...')
        for module in set(self.tables.keys()) & set(self.schema.keys()):
            for table in self.tables[module]:
                for column in table:
                    try:
                        paths = self.schema.pathfinder(path=path)
                    except KeyError:
                        raise Exception('Table Error: {} not a valid'
                                        ' column'.format(column))
                    else:
                        for path in paths:
                            data = self.schema(path)
                            data['related'] = table
                            self.schema.push(path, data)
                            self.map_tables[path] = table
    '''


    def _map_fields_to_tables(self):
        """Add table data to field data in self.schema"""
        cprint('Mapping tables...')
        for module in set(self.tables.keys()) & set(self.schema.keys()):
            for table in self.tables[module]:
                for column in table:
                    data = self.schema(*column)
                    data['columns'] = table
                    self.schema.push(data, *column)
        # Capture one-column tables
        #for path in self.schema.pathfinder():
        #    data = self(path)
        #    if data['table'] and not 'columns' in data:
        #        data['columns'] = path,


    def _map_aliases(self, module=None):
        """Update schema with user-defined aliases based on files/aliases.txt

        Aliases can be called directly from schema. Additional aliases
        can be set using set_aliases().

        Args:
            module (str): name of base module

        Returns:
            Dict of {alias: path} pairs
        """
        cprint('Reading user-defined aliases...')
        aliases = {}
        with open(os.path.join(self._fpath, 'aliases.txt')) as f:
            for line in [line.strip() for line in f.read().splitlines()
                         if ',' in line and not line.startswith('#')]:
                alias, path = line.split(',')
                # Exclude shortcuts to other modules if module specified
                if module is not None and not path.startswith(module):
                    continue
                try:
                    d = self.schema(path)
                except KeyError:
                    cprint(' Alias error: Path not found: {}'.format(alias))
                else:
                    #cprint('{} => {}'.format(alias, path))
                    d['alias'] = alias
                    self.schema.push(alias, d)
                    aliases[alias] = True
                    try:
                        self(path)['columns']
                    except KeyError:
                        if is_table(path):
                            cprint((' Alias error: Related table not'
                                    ' found: {}'.format(alias)))
                    # Not needed. Table included in data already.
                    #else:
                    #    self.map_columns[alias] = table
        return aliases


    @staticmethod
    def get_xpath(*args):
        """Reformat plain-text path to xpath

        Args:
            path (str): an XMuFields path

        Returns:
            Path string reformatted as in an EMu export
        """
        xpath = []
        for arg in args:
            if is_table(arg):
                xpath.append("table[@name='{}']".format(arg))
                xpath.append('tuple')
            elif is_reference(arg):
                xpath.append("tuple[@name='{}']".format(arg))
            else:
                xpath.append("atom[@name='{}']".format(arg))
        return '/'.join(xpath)


    @staticmethod
    def read_fields(fp):
        """Reads paths from the schema in an EMu XML export

        Args:
            fp (str): path to the EMu XML report

        Returns:
            List of paths in the EMu schema
        """
        paths = []
        schema = []
        with open(fp, 'rb') as f:
            for line in f:
                schema.append(line.rstrip())
                if line.strip() == '?>':
                    break
        schema = schema[schema.index('<?schema')+1:-1]
        containers = ['schema']
        for field in schema:
            kind, field = [s.strip() for s in field.rsplit(' ', 1)]
            if kind in ('table', 'tuple'):
                containers.append(field)
                continue
            if field == 'end':
                containers.pop()
            else:
                paths.append('/'.join(containers[1:] + [field]))
        return paths


    def set_alias(self, alias, path):
        """Add alias: path to self.schema

        Args:
            alias (str): name of alias
            path (str): path to alias

        """
        self.schema.push(alias, self.schema(path))


    '''
    def reset_aliases(self):
        """Update schema to remove all aliases set using set_aliases()"""
        self.schema = copy(self.master)
    '''


    def add_table(self, columns):
        """Update table containers with new table

        Args:
            columns (list): columns in the table being added
        """
        module = columns[0][0]
        columns.sort()
        columns = tuple(columns)
        hkey = hash(columns)
        try:
            self.hashed_tables[hkey]
        except KeyError:
            self.tables.setdefault(module, []).append(columns)
            self.hashed_tables[hkey] = columns
        for column in columns:
            self.map_tables[column] = columns


def is_table(*args):
    """Assess whether a path points to a table

    Args:
        path (str): period-delimited path to a given field

    Returns:
        Boolean
    """
    tabends = ('0', '_nesttab', '_nesttab_inner', '_tab')
    return bool(len([s for s in args if s.endswith(tabends)]))


def is_reference(*args):
    """Assess whether a path is a reference

    Args:
        path (str): period-delimited path to a given field

    Returns:
        Boolean
    """
    refends = ('Ref', 'Ref_tab')
    return bool(len([s for s in args if s.endswith(refends)]))
