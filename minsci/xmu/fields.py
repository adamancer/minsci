import cPickle as serialize
import datetime
import glob
import os
import re
import collections
from copy import copy

from ..helpers import cprint, dedupe, rprint


class DeepDict(dict):

    def __init__(self, terminate=False, mapping=None):
        if mapping is not None:
            super(DeepDict, self).__init__(mapping)
        self.terminate = terminate


    def pull(self, path=None):
        d = self
        if path is not None:
            for key in path.split('.'):
                try:
                    d = d[key]
                except KeyError:
                    raise
        return d


    def push(self, path, val):
        d = self
        keys = path.split('.')
        last = keys.pop()
        for key in keys:
            d = d.setdefault(key, DeepDict())
        d[last] = val


    def pluck(self, path):
        # Requires full path, not just an alias
        try:
            alias = copy(path)
            path = self[path]['path']
        except KeyError:
            pass
        else:
            del self[alias]
        path = path.split('.')
        paths = ['.'.join(path[:i]) for i in xrange(1,len(path)+1)]
        for path in paths[::-1]:
            val = self.pull(path)
            if not isinstance(val, DeepDict) or not len(val):
                d = self
                keys = path.split('.')
                last = keys.pop()
                for key in keys:
                    try:
                        d = d[key]
                    except KeyError:
                        raise
                del d[last]
                #print 'Deleted {}'.format(path)
            elif len(val) >= 1:
                break


    def appush(self, path, val):
        """Create or extend list for the given path"""
        d = self
        keys = path.split('.')
        last = keys.pop()
        for key in keys:
            d = d.setdefault(key, DeepDict())
        try:
            d.setdefault(last, []).extend(val)
        except AttributeError:
            raise


    def dedupe(key, lower=True):
        """Dedupes list while maintaining order and case"""
        lst = self.pull(key)
        orig = copy(lst)
        if lower:
            lst = [val.lower() for val in lst]
        keep = [i for i in xrange(len(lst)) if not lst[i] in lst[:i]]
        self.push(key, [orig[i] for i in keep])


    def walk(self, callback, path=None, d=None, root=None):
        if d is None:
            d = self
            root = []
        try:
            d = d.pull(path)
        except AttributeError:
            raise
        except KeyError:
            raise
        else:
            if path is not None:
                root.append(path)
            try:
                keys = d.iterkeys()
            except AttributeError:
                raise
            else:
                if not d.terminate:
                    for path in keys:
                        paths = self.walk(callback, path, d, root)
                else:
                    callback(d)
            try:
                root.pop()
            except IndexError:
                pass



    def pathfinder(self, path=None, d=None, root=None, paths=None):
        if d is None:
            d = self
            root = []
            paths = []
        try:
            d = d.pull(path)
        except AttributeError:
            raise
        except KeyError:
            raise
        else:
            if path is not None:
                root.append(path)
            try:
                keys = d.iterkeys()
            except AttributeError:
                paths.append('.'.join(root))
            else:
                if not d.terminate:
                    for path in keys:
                        paths = self.pathfinder(path, d, root, paths)
                else:
                    paths.append('.'.join(root))
            try:
                root.pop()
            except IndexError:
                pass
        return paths




class XMuFields(object):

    def __init__(self, fp=None, whitelist=None, blacklist=None, expand=None,
                 pickle=False, suppress_pickle_warning=False):
        """Creates object containing metadata about fields in EMu

        Args:
            fp (str): path to EMu schema file. If None, defaults to
                a copy of the schema stored in files.
            whitelist (list): list of EMu modules to include. If None,
                anything not on the blacklist is included.
            blacklist (list): list of EMu modules to exclude. If None,
                no modules are specifically excluded.
            expand (tuple): tuple of tuples (startswith, endswith)
                used by the second iteration of the expand function
            pickle (tuple): if True, check for cached XMuFields object or
                cache the new object if cached object not found. If False,
                don't check for or create cache. If None, create but don't
                check for cache.


        Attributes:
            self.schema (dict): path-keyed dicts of field data
            self.atoms (dict): module-keyed lists of paths to atomic fields
            self.tables (dict): module-keyed lists of paths to tables
            self.map_tables (dict): path-keyed lists of paths to tables
        """
        self.verbose = False
        self.basepath = os.path.dirname(__file__)
        self.fpath = os.path.join(self.basepath, 'files')
        if pickle is True:
            if not suppress_pickle_warning:
                rprint('***WARNING: The cache feature uses pickle. The'
                       ' pickle module is not secure against erroneous'
                       ' or maliciously constructed data. Never unpickle'
                       ' data received from an untrusted or unauthenticated'
                       ' source.***')
            cprint('Checking for pickled XMuFields object...')
            try:
                with open('fields.p', 'rb') as f:
                    fields = serialize.load(f)
            except IOError:
                cprint('No cache found!')
                pickle = None  # None is different than False
            except:
                cprint('Cache is in the wrong format!')
                pickle = None
            else:
                try:
                    self.schema = fields['schema']
                    self.atoms = fields['atoms']
                    self.tables = fields['tables']
                    self.map_tables = fields['map_tables']
                    self.hashed_tables = fields['hashed_tables']
                    self.aliases = fields['aliases']
                except KeyError:
                    print 'Could not read cache!'
                    pickle = None
        if not pickle:
            if fp is None:
                fp = os.path.join(self.fpath, 'NMNH-schema.pl')

            schema = self._read_schema(fp, whitelist, blacklist)
            self.schema, self.atoms = self._enhance_schema(schema)

            # Read tables
            self.tables = {}         # maps tables to modules
            self.map_tables = {}     # maps container paths to fields
            self.hashed_tables = {}  # maps hash of tables to tables
            self.tables = self._read_tables()

            cprint('Expanding references...')
            self._expand_references()
            if expand is not None:
                for e in expand:
                    self._expand_references(e[0], e[1])

            # FIXME: Map table fields not specified in the tables folder

            self._map_fields_to_tables()  # adds table fields to schema dict

            self.master = copy(self.schema)
            try:
                self.aliases = self._map_aliases(tuple(whitelist))
            except TypeError:
                self.aliases = self._map_aliases()
            self.modules = {}
        # Dump fields object as json
        if pickle is None:
            cprint('Caching XMuFields object...')
            fields = {
                'schema': self.schema,
                'atoms': self.atoms,
                'tables': self.tables,
                'map_tables': self.map_tables,
                'hashed_tables': self.hashed_tables,
                'aliases': self.aliases,
            }
            with open('fields.p', 'wb') as f:
                serialize.dump(fields, f)
        cprint('Finished reading field data!')


    def __call__(self, path, module=None):
        """Returns data for a given path/alias"""
        try:
            return self.schema.pull(self.get_path(path, module))
        except KeyError:
            raise Exception('PathError: {}'.format(path))


    def _read_schema(self, fp, whitelist, blacklist):
        """Reads EMu schema file to dictionary

        The EMu schema file includes (but is not limted to) these parameters:
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

        Args:
            See init for a description of the arguments for this function.

        Returns:
            Dictionary with information about the XML schema:
            {module : {field: { param_1: value_1,.., param_n: value_n}}}
        """

        cprint('Reading EMu schema from {}...'.format(fp))
        # These regexes are used to split the .pl file into
        # modules and fileds
        re_module = re.compile('\te[a-z]+ =>.*?\{.*?\n\t\}', re.DOTALL)
        re_field = re.compile("'[A-z].*?\},", re.DOTALL)
        re_lines = re.compile('[A-z].*,', re.DOTALL)
        try:
            with open(fp, 'rb') as f:
                modules = re_module.findall(f.read())
        except OSError:
            raise Exception('{} not found'.format(fp))
        schema = {}
        for module in sorted(modules):
            module_name = module.split('\n')[0].strip().split(' ')[0]
            if ((whitelist is not None and not module_name in whitelist)
                or (blacklist is not None and module_name in blacklist)):
                #cprint(' Skipped {}'.format(module_name))
                continue
            schema[module_name] = {}
            fields = re_field.findall(module)
            for field in fields:
                d = {}
                lines = [s.strip() for s in field.split('\n')
                         if bool(s.strip())]
                field_name = lines[0].split(' ')[0].strip('"\'')
                lines = lines[2:len(lines)-1]
                for line in lines:
                    try:
                        key, val = [s.strip('",\'') for s in line.split(' => ')]
                    except:
                        pass
                    else:
                        d[key] = val.decode('cp1252')
                # I think the ItemName field appears only for fields that
                # are editable in EMu, so use it to cull the copy fields, etc.
                try:
                    d['ItemName']
                except KeyError:
                    #cprint('Skipped {}.{}'.format(module_name, field_name))
                    continue
                schema[module_name][field_name] = d
        return schema


    def _enhance_schema(self, emu_schema):
        """Enhances schema with path and table information

        Returns:
            Tuple containing the following:
                schema (dict)
                atoms (dict): dict of lists containing atom paths
                tables (dict): dict of lists containing table paths
        """
        schema = DeepDict()
        atoms = {}
        tables = {}
        aliases = {}
        for module in emu_schema:
            atoms[module] = []
            tables[module] = []
            for field in emu_schema[module]:
                field_data = emu_schema[module][field]
                # Determine full path to field
                path = [module]
                name = module
                for key in ['ColumnName', 'ItemName', 'ItemBase',
                            'RefTable', 'RefKey']:
                    try:
                        val = field_data[key]
                    except KeyError:
                        pass
                    else:
                        if path[-1].endswith('_nesttab'):
                            path.append(val.rstrip('0') + '_nesttab_inner')
                            if not val.endswith(('0', 'Ref')):
                                path.append(val)
                        elif not (val.endswith('Ref')
                                and name.endswith('Ref_tab')):
                            # Skip ItemName for references. This allows their
                            # paths to match the EMu import/export schema.
                            path.append(val)
                        name = val
                # Reworked dedupe function to check against preceding value
                keep = [i for i in xrange(len(path))
                        if not i or path[i] != path[i-1]]
                path = '.'.join([path[i] for i in keep])
                xpath = self.get_xpath(path)
                # Check if data is grid. The table check is simplistic.
                tabends = ('0', '_nesttab', '_tab')
                table = bool(len([s for s in path.split('.')
                             if s.endswith(tabends)]))
                # Create simple schema
                scheme = {
                    'name' : name,
                    'module' : module,
                    'path' : path,
                    'xpath' : xpath,
                    'schema' : emu_schema[module][field],
                    'table' : table
                }
                schema.push(path, DeepDict(True, scheme))
                if not table:
                    atoms[module].append(path)
        return schema, atoms


    def _read_tables(self):
        """Update table data from text files in files/tables"""
        tables = {}
        for fp in glob.iglob(os.path.join(self.fpath, 'tables', 'e*.txt')):
            module_name = os.path.splitext(os.path.basename(fp))[0]
            _tables = {}
            with open(fp, 'rb') as f:
                for line in [line.strip() for line in f.read().splitlines()
                             if ',' in line and not line.startswith('#')]:
                    table, field = line.split(',')
                    field = '{}.{}'.format(module_name, field)
                    try:
                        _tables[table].append(field)
                    except KeyError:
                        _tables[table] = [field]
            for table in _tables.values():
                self.add_table(table)
            tables[module_name] = [tuple(sorted(t)) for t in _tables.values()]
        return tables


    def _map_tables(self):
        """Update path-keyed table map"""
        cprint('Mapping tables...')
        for module in self.tables:
            for table in self.tables[module]:
                for path in table:
                    try:
                        paths = self.schema.pathfinder(path=path)
                    except KeyError:
                        cprint(' {} not found when mapping tables'.format(path))
                    else:
                        for path in paths:
                            data = self.schema.pull(path)
                            data['related'] = table
                            self.schema.push(path, data)
                            self.map_tables[path] = table


    def _map_fields_to_tables(self):
        """Add table data to field data in self.schema"""
        cprint('Mapping tables...')
        for module in self.tables:
            for table in self.tables[module]:
                paths = []
                for path in table:
                    try:
                        paths.extend(self.schema.pathfinder(path))
                    except KeyError:
                        pass
                paths.sort
                fields = tuple(paths)
                for path in paths:
                    path = self(path)['path']
                    data = self.schema.pull(path)
                    data['table_fields'] = fields
                    self.schema.push(path, data)
        # Capture one-column tables
        for path in self.schema.pathfinder():
            data = self(path)
            if data['table'] and not 'table_fields' in data:
                data['table_fields'] = path,


    def _expand_references(self, startswith=None, endswith=None):
        """Expand references in schema to provide full paths to linked modules

        The first pass extends any path ending with an irn. Subsequent
        passes are limited to the fields specified in the expand argument
        in __init__; otherwise the schema expands geometrically.

        path: the path to the

        Args:
            startswith (str): limit expansion to fields starting with this
            endswith (str): limit expansion to fields ending with this

        """
        if endswith is None:
            endswith = '.irn'
        if startswith is not None:
            paths = self.schema.pathfinder(path=startswith)
            startswith = startswith.split('.')
        else:
            paths = self.schema.pathfinder()
        paths = [path for path in paths
                 if path.endswith(endswith) and path.count('.') > 1]

        # Run before the root of the schema is polluted by aliases
        modules = {}
        for module in self.schema:
            modules[module] = self.schema.pathfinder(module)

        i = 0
        hints = {}  # holds cached field data lookups
        t1 = datetime.datetime.now()
        for path in sorted(paths):
            cmps = path.split('.')[:-1]
            ref_module = cmps.pop()      # module being referenced
            try:
                orig_module = cmps[0]  # referencing module
            except IndexError:
                # No referencing field supplied
                orig_module = ''
                orig_path = ''
            else:
                orig_path = '.'.join(cmps)  # path to the original reference
            try:
                ref_paths = modules[ref_module]
            except KeyError:
                #cprint(' {} not found'.format(ref_module))
                continue
            # Identify reference tables
            atoms_only = False
            if len(path) and 'Ref_tab' in orig_path:
                atoms_only = True
            tabends = ('0', '_nesttab', '_tab')
            for ref_path in ref_paths:
                # Set full path from the referencing module to referenced field
                full_path = '.'.join([orig_path, ref_path])
                # Get field data for the reference path
                try:
                    field_data = hints[ref_path]
                except KeyError:
                    field_data = self.schema.pull(ref_path)
                    hints[ref_path] = field_data
                # Limit reference tables to atomic fields only. Nested
                # tables produce some nasty complexities that are beyond
                # the scope of this script to deal with, so only atomic
                # fields are considsered for reference tables.
                if atoms_only and field_data['table']:
                    #cprint('Skipped table in ref table: {}'.format(ref_path))
                    continue
                try:
                    self.schema.pull(full_path)
                except KeyError:
                    # Full path does not exist, so we need to add it based
                    # on data from the referenced field. Pull and update a
                    # copy of the field data stored under the full path.
                    field_data = copy(field_data)
                    field_data['path'] = full_path
                    field_data['xpath'] = self.get_xpath(full_path)
                    field_data['table'] = self.is_table(full_path)
                    self.schema.push(full_path, field_data)
                    # Identify most specific table path for the full path
                    tab_path = []
                    cmps = ref_path.split('.')
                    for x in xrange(len(cmps)):
                        if cmps[x].endswith(tabends):
                            tab_path = cmps[:i+1]
                    if len(tab_path):
                        # If referenced path is part of a table, expand it if
                        # it hasn't been expanded already
                        tab_path = '.'.join(tab_path)
                        # Check if this table has already been expanded.
                        try:
                            self.map_tables[tab_path]
                        except KeyError:
                            # It hasn't. Does it belong to an existing table?
                            try:
                                fields = copy(self.map_tables[orig_path])
                            except KeyError:
                                # No table exists for referenced path, so
                                # add a one-field table
                                fields = [orig_path]
                                self.add_table(fields)
                            # Create table for full path based on
                            # referenced path
                            fields = [tab_path + '.' + fld for fld in fields]
                            self.add_table(fields)
            i += 1
            if not i % 100:
                dt = datetime.datetime.now() - t1
                t1 = datetime.datetime.now()
                cprint(' {:,} references expanded (t={})'.format(i, dt))
        cprint('{:,} references expanded'.format(i))


    def _map_aliases(self, module=None):
        """Update schema with user-defined aliases based on files/aliases.txt

        Aliases can be called directly from schema. Additional aliases
        can be set using set_aliases().
        """
        cprint('Reading user-defined aliases...')
        aliases = {}
        with open(os.path.join(self.fpath, 'aliases.txt')) as f:
            for line in [line.strip() for line in f.read().splitlines()
                         if ',' in line and not line.startswith('#')]:
                alias, path = line.split(',')
                # Exclude shortcuts to other modules if module specified
                if module is not None and not path.startswith(module):
                    continue
                try:
                    d = self.schema.pull(path)
                except KeyError:
                    cprint(' Alias error: Path not found: {}'.format(alias))
                else:
                    #cprint('{} => {}'.format(alias, path))
                    d['alias'] = alias
                    self.schema.push(alias, d)
                    aliases[alias] = True
                    try:
                        table = self(path)['table_fields']
                    except KeyError:
                        if self.is_table(path):
                            cprint((' Alias error: Related table not'
                                    ' found: {}'.format(alias)))
                    # Not needed. Table included in data already.
                    #else:
                    #    self.map_table_fields[alias] = table
        return aliases


    def return_key(self, key):
        """Return key matching or containing search term"""
        try:
            cprint(self.schema[key])
        except KeyError:
            paths = [path for path in self.schema if key in path]
            if len(paths):
                cprint(u'Partial matches:')
                print '\n'.join(sorted(paths))


    def set_aliases(self, ref_module, ref_field=''):
        """Update schema with aliases from a reference field to a module

        Args:
            ref_module (str): name of module to reference
            ref_field (str): name of reference to map alises to
        """
        paths = self.schema.pathfinder(ref_module)
        aliases = {}
        for path in sorted(paths):
            field = path.split('.')[1]
            alias = field.rstrip('0').split('_')[0]
            try:
                aliases[alias].append(path)
            except KeyError:
                aliases[alias] = [path]
        for alias in sorted(aliases.keys()):
            if len(aliases[alias]) == 1:
                path = '{}.{}'.format(ref_field, aliases[alias][0]).lstrip('.')
                try:
                    self.schema.pull(path)
                except KeyError:
                    cprint('{} not found in schema'.format(path), self.verbose)
                else:
                    try:
                        self.schema.pull(alias)
                    except KeyError:
                        cprint('{} => {}'.format(alias, path), self.verbose)
                        field_data = self.schema.pull(path)
                        field_data['alias'] = alias
                        self.schema.push(alias, field_data)
                        self.aliases[alias] = False
                    else:
                        cprint('{} found in schema'.format(alias), self.verbose)


    def set_alias(self, alias, path):
        self.schema.push(alias, self.schema.pull(path))


    def reset_aliases(self):
        """Update schema to reset all aliases set using set_aliases()"""
        self.schema = copy(self.master)


    def add_table(self, fields):
        """Update containers with new table"""
        module = fields[0].split('.')[0]
        tkey = []
        for cmp in fields[0].split('.'):
            tkey.append(cmp)
            if self.is_table(cmp):
                break
        fields.sort
        fields = tuple(fields)
        hkey = hash(fields)
        try:
            self.hashed_tables[hkey]
        except KeyError:
            self.tables.setdefault(module, []).append(fields)
            self.hashed_tables[hkey] = fields
        for field in fields:
            self.map_tables[field] = fields


    def is_table(self, path):
        """Assess whether a path points to a table

        Args:
            path (str): period-delimited path to a given field

        Returns:
            Boolean
        """
        tabends = ('0', '_nesttab', '_nesttab_inner', '_tab')
        return bool(len([s for s in path.split('.') if s.endswith(tabends)]))


    def is_ref(self, path):
        """Assess whether a path is a reference

        Args:
            path (str): period-delimited path to a given field

        Returns:
            Boolean
        """
        refends = ('Ref')
        return bool(len([s for s in path.split('.') if s.endswith(refends)]))


    def bracketize_path(self, path):
        """Mark tuples in given path with {0}"""
        cmps = path.split('.')
        path = [cmps[0]]
        for i in xrange(1, len(cmps)):
            this = cmps[i]
            last = cmps[i-1]
            if last.endswith(('0', '_nesttab', '_nesttab_inner', '_tab')):
                path.append('{0}')
            path.append(this)
        return '.'.join(path)


    def get_path(self, path, module=None):
        """Convert EMu export xpath to XMuFields path"""
        if module is not None and not path.startswith(module):
            path = '{}.{}'.format(module, path)
        try:
            return self.schema.pull(path)['path']
        except KeyError:
            d = self.schema
            temp = []
            for key in path.split('.'):
                try:
                    d = d[key]
                except KeyError:
                    keys = d.keys()
                    if len(d) == 1 and keys[0].startswith(('e','l')):
                        d = d[keys[0]][key]
                        temp.append(keys[0])
                    else:
                        #cprint('Original path: {}'.format(path))
                        #cprint('Derived path : {}'.format('.'.join(temp)))
                        raise
                temp.append(key)
        return '.'.join(temp)


    def get_xpath(self, path):
        """Convert XMuFields path to EMu export xpath"""
        xpath = []
        for name in [name for name in path.split('.')
                     if not name.startswith(('e', 'l'))]:
            if self.is_table(name):
                xpath.append("table[@name='{}']".format(name))
                xpath.append('tuple')
            elif self.is_ref(name):
                xpath.append("tuple[@name='{}']".format(name))
            else:
                xpath.append("atom[@name='{}']".format(name))
        return '/'.join(xpath)
