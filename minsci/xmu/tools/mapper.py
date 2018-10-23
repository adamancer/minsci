"""Alias handling for processing EMu data that doesn't use full paths"""
from __future__ import unicode_literals

from past.builtins import basestring
from builtins import object
import os

from ...xmu import XMu, MinSciRecord, is_table, is_reference


class FieldMapper(object):
    """Map field aliases to full paths in EMu

    Attributes:
        aliases (dict): maps aliases to full paths in EMu schema
        module (str): the name of the EMu module being matched against
        references (dict): maps aliases to reference fields
        schema (dict): the EMu schema
        tables (dict): maps columns to table fields

    Args:
        module (str): the name of the module being matched against
    """

    def __init__(self, module):
        xmudata = XMu(None, module=module, container=MinSciRecord)
        self.schema = xmudata.fields.schema
        self.module = module
        self.aliases = {}
        self.paths = {}
        self.read_aliases(self.module)
        self.tables = {}
        self.references = {}
        self._safe = False  # True if fields have been verified


    def __call__(self, field, schema_path=False):
        """Convenience function calling the get_path function"""
        return self.get_path(field, schema_path)


    def read_aliases(self, module):
        """Read aliases for the given module from file

        Args:
            module (str): the backend name of an EMu module

        Returns:
            A dict mapping aliases to paths
        """
        aliases = {}
        fp = os.path.join('mapper', '{}.txt'.format(module))
        with open(fp, 'r') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                try:
                    alias, path = [s.strip() for s in line.split(':', 1)]
                except ValueError:
                    pass
                else:
                    if path:
                        path = path.split('/')
                        self.set_alias(alias, path)
        return aliases


    def set_alias(self, alias, path):
        """Sets the path for a given alias in class-wide lookups

        Args:
            alias (str): the alias to assign to the given path
            path (str or iterable): the full path
        """
        # Standardize the form of the path
        if isinstance(path, basestring):
            path = [path]
        path = tuple(path)
        # Verify the given path
        paths = [path]
        try:
            schema_path = tuple(self.get_data(*path)['path'].split('/'))
        except KeyError:
            # The path check fails for reference tables. This does not cause
            # any obvious downstream issues.
            pass
        else:
            paths.append(schema_path)
            # If alias points to a table, add that path as well
            if [field for field in schema_path if is_table(field)]:
                paths.append(schema_path[:-1])
        # Set aliases
        self.aliases[alias] = path
        for path in paths:
            try:
                self.paths[path]
            except KeyError:
                self.paths[path] = alias


    def get_path(self, alias, schema_path=False):
        """Returns the path for a given alias

        Args:
            alias (str): the alias for a given path
            schema_path (bool): if true, uses the format needed for schema

        Returns:
            If schema_path is True, returns a list containing the path. If
            not, returns a tuple with the path formatted for schema.
        """
        if schema_path:
            return tuple(self.get_data(alias)['path'].split('/'))
        else:
            try:
                return list(self.aliases[alias])
            except KeyError:
                return list(self._guess_path(alias))


    def get_alias(self, path):
        """Returns the alias for a given path

        Args:
            path (str): the full path to an EMu field

        Returns:
            Alias for a given path, if it exists
        """
        if isinstance(path, basestring):
            path = [path]
        return self.paths[tuple(path)]


    def _guess_path(self, alias):
        """Attempts to guess the path for an unrecognized field"""
        suffixes = ['', '0', '_tab', '_nesttab', 'Ref', 'Ref_tab']
        for field in [alias + suffix for suffix in suffixes]:
            try:
                self.schema[self.module][field]
            except KeyError:
                pass
            else:
                path = [field]
                if is_table(field) and not is_reference(field):
                    path.append(field.split('_', 1)[0].rstrip('0'))
                self.set_alias(alias, path)
                return path
        raise Exception('{} {}'.format(alias, 0))


    def get_data(self, *args):
        """Returns data for a given path or alias"""
        val = self.schema[self.module]
        # Check if first key is an alias
        if len(args) == 1 and val.get(args[0]) is None:
            args = self.get_path(args[0])
        for arg in args:
            val = val[arg]
            # Test for references (changes in module)
            try:
                val = self.schema[val['schema']['RefTable']]
            except (KeyError, TypeError):
                pass
        return val


    def get_tables(self, fields):
        """Map columns in tables

        Args:
            fields (list): list of fields and aliases

        Returns:
            List of tables
        """
        tables = {}
        for field in fields:
            path = self(field)
            if is_table(*path):
                col = [col for col in path if is_table(col)][0]
                tables.setdefault(col, []).append(field)
        self.tables = tables
        return tables


    def get_references(self, fields):
        """Map columns in references

        Args:
            fields (list): list of fields and aliases

        Returns:
            List of references
        """
        references = {}
        for field in fields:
            path = self(field)
            if is_reference(*path):
                col = [col for col in path if is_reference(col)][0]
                references.setdefault(col, []).append(field)
        self.references = references
        return references


    def expand(self, rec):
        """Expand fields in record based on known aliases

        This should be used instead of the DeepDict.expand() function for
        records constructed from spreadsheets using the Mineral Sciences
        alias set.

        Args:
            rec (dict): record data
        """
        for field in list(rec.keys()):
            if rec[field]:
                path = self(field)
                if isinstance(path, list) and len(path) > 1:
                    d = rec
                    last = path.pop()
                    for segment in path:
                        container = [] if is_table(segment) else {}
                        try:
                            d = d.setdefault(segment, container)
                        except AttributeError:
                            try:
                                d = d[0].setdefault(segment, container)
                            except IndexError:
                                d.append({})
                                d = d[0].setdefault(segment, container)
                    if isinstance(rec[field], list):
                        # This conditional tries to handle atomic references
                        # inside a reference table. In this case, the list
                        # index applies to the reference table, and the
                        # internal reference is atomic.
                        if ((is_reference(segment) or '_nesttab' in path)
                                and not is_table(segment)):
                            if len(rec[field]) > 1:
                                raise Exception('Reference length error')
                            d[last] = rec[field][0]
                        else:
                            for i, val in enumerate(rec[field]):
                                try:
                                    d[i][last] = val
                                except KeyError:
                                    d = [{last: val}]
                                except IndexError:
                                    d.append({last: val})
                    else:
                        d[last] = rec[field]
                    del rec[field]
            else:
                del rec[field]
        return rec
