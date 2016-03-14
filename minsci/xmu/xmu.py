import glob
import hashlib
import os
from copy import copy

from lxml import etree

from .fields import XMuFields, DeepDict
from ..helpers import cprint, rprint


class XMu(object):

    def __init__(self, path=None, fields=None):
        """Read and search XML export files from EMu

        Args:
            path (str): path to EMu XML report or directory containing
                multiple reports. If multiple reports are found, they
                are handled from newest to oldest.
            fields: an XMuFields object
        """
        # Class-wide switches
        self.verbose = False
        self.module = None

        # Create fields if not defined
        if fields is None:
            fields = XMuFields()
        self.fields = fields
        self.schema = fields.schema
        self.atoms = fields.atoms
        self.tables = fields.tables

        # Collect some information about the source file(s)
        if path is not None:
            # Handle a directory
            if os.path.isdir(path):
                self.files = [fp for fp in
                              glob.glob(os.path.join(path,'*.xml'))]
                self.files.sort(key=lambda fp: os.path.getmtime(fp),
                                reverse=True)
                xpaths = []
                for fp in self.files:
                    xpaths.extend(self.fields.read_fields(fp))
                self.xpaths = list(set(xpaths))
            elif path.endswith('.xml'):
                self.xpaths = self.fields.read_fields(path)
                self.files = [path]
            else:
                raise
            for path in self.xpaths:
                self.fields(path)
            self.module = self.xpaths[0].split('.')[0]
            self.newest = max([os.path.getmtime(fp) for fp in self.files])
            self.paths_found = {}  # dictionary tracking paths checked and found
        else:
            self.files = []
            cprint('Warning: No XML files specified.'
                   ' Some functions are not available.')


    def fast_iter(self, callback, report_progress=0):
        """Iterate through EMu export using callback function

        Args:
          func (str): name of callback function

        Returns:
          None
        """
        n = 0
        for fp in self.files:
            cprint('Reading {}...'.format(fp))
            context = etree.iterparse(fp, events=['end'], tag='tuple')
            for event, element in context:
                # Process children of module table only
                parent = element.getparent().get('name')
                if parent is not None and parent.startswith('e'):
                    result = callback(element)
                    if result is False:
                        del context
                        return False
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
                    n += 1
                    if report_progress and not n % report_progress:
                        print '{:,} records processed!'.format(n)
            del context
        print '{:,} records processed!'.format(n)
        return True
        # Notify user paths checked and found
        #print 'Path information:'
        #for key in sorted(self.paths_found):
        #    val = self.paths_found[key]
        #    print key + ': ', max(val)


    def find(self, *args):
        """Return value(s) for a given path in the EMu XML export

        Args:
            *args (str): strings comprising the full path to a given
              field within a single record. Each field should be a
              separate argument, i.e., ('BioEventSiteRef', 'irn')

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
            self.paths_found[xpath].append(len(results))
        except:
            self.paths_found[xpath]  = [len(results)]
        # Convert atoms to unicode
        if not 'table' in xpath:
            try:
                results = results[0]
            except IndexError:
                results = u''
        return results


    def write(self, fp, records, module='ecatalogue', handlers=None):
        """Write EMu import file based on records

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
                irn_fields.append(self.schema.pull(irn_fields[0])['alias'])
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
                bracketized = [self.fields.bracketize_path(path) for path in table]
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
                self.xwrite(row.keys()[0], row, record, module, handlers)
            except KeyError:
                raise
            row_num += 1
            if not row_num % 100:
                print '{:,} records written!'.format(row_num)
        print '{:,} records written!'.format(row_num)
        root.getroottree().write(fp, pretty_print=True,
                                 xml_declaration=True, encoding='utf-8')


    def xwrite(self, path, d, xml, module, handlers):
        try:
            d = d[path]
        except AttributeError:
            raise
        except KeyError:
            raise
        else:
            try:
                paths = d.keys()
            except AttributeError:
                atom = etree.SubElement(xml, 'atom')
                atom.set('name', path)
                atom.text = d
            else:
                if path.isnumeric():
                    # How to add group and append?
                    xml = etree.SubElement(xml, 'tuple')
                    try:
                        name = xml.getparent().get('name')
                        attr = handlers[name]
                    except KeyError:
                        pass
                    else:
                        for key in attr:
                            if attr[key] is not None:
                                xml.set(key, attr[key])
                                if key == 'row':
                                    # Get unique group ids by hashing tables
                                    tkey = '{}.{}'.format(module, name)
                                    table = self.fields.map_tables[tkey]
                                    s = '.'.join(sorted(table))
                                    h = hashlib.md5(s).hexdigest()
                                    xml.set('group', '{}_{}'.format(h, path))
                elif path.endswith(('0', '_nesttab', '_nesttab_inner', '_tab')):
                    xml = etree.SubElement(xml, 'table')
                    xml.set('name', path)
                elif path.endswith(('Ref')):
                    xml = etree.SubElement(xml, 'tuple')
                    xml.set('name', path)
                elif bool(path) and not path.startswith(('e', 'l')):
                    xml = etree.SubElement(xml, 'atom')
                    xml.set('name', path)
                for path in sorted(paths):
                    self.xwrite(path, d, xml, module, handlers)
                xml = xml.getparent()
        return xml


    def harmonize(self, new_val, old_val, path, action='fill'):
        """Harmonize values

        fill: add new value if blank
        append: append new value (either a new row or via delimiter)
        replace: replace with  new value

        Returns:
            Tuple containing the revised value and an update boolean
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


    def fill_paths(self, record):
        """Map all keys in record from alias to full path"""
        keymap = dict([(self.fields(key)['path'], key) for key in record])
        record = dict([(self.fields(key)['path'], record[key])
                        for key in record])
        return record, keymap


    def alias_paths(self, record, keymap):
        """Map all keys in record from full path to alias"""
        for key in [key for key in record.keys() if key != keymap[key]]:
            record[keymap[key]] = record[key]
            del record[key]
        return record


    def pad_tables(self, record):
        """Pad tables to same length. Use for reading-in data."""
        record, keymap = self.fill_paths(record)
        for path in record:
            try:
                related = self.fields(path)['table_fields']
            except KeyError:
                # Not a table
                pass
            else:
                paths = [path for path in related if path in record]
                if len(paths) > 1:
                    maxlen = max([len(record[path]) for path in paths
                                  if len(record[path])])
                    for path in paths:
                        record[path] += [''] * (maxlen - len(record[path]))
        return self.alias_paths(record, keymap)


def instant(subclass, module, path=None):
    """Create a simple XMu object"""
    fields = XMuFields(whitelist=module)
    fields.set_aliases(module)
    return subclass(path, fields)


def make_fields(module):
    """Create XMuFields object tailored for a given module

    Args:
        module (str): name of module

    Returns:
        XMuFields object, or None if module is not recognized
    """
    if module == 'ecatalogue':
        whitelist = [
            'ebibliography',
            'ecatalogue',
            'ecollectionevents',
            'elocations',
            'emultimedia',
            'enmnhanalysis',
            'enmnhorig',
            'enmnhtransactions',
            'eparties',
            'etaxonomy'
            ]
        expand = [
            ('ecatalogue.BioEventSiteRef', 'eparties.irn'),
            ('ecatalogue.PetChemicalAnalysisRef_tab', 'eparties.irn')
            ]
        fields = XMuFields(whitelist=whitelist, expand=expand)

        fields.set_aliases('ecatalogue')
        fields.set_aliases('ecollectionevents', 'ecatalogue.BioEventSiteRef')
        fields.set_aliases('etaxonomy', 'ecatalogue.IdeTaxonRef_tab')
        fields.set_aliases('enmnhanalysis',
                           'ecatalogue.PetChemicalAnalysisRef_tab')
        fields.set_aliases('enmnhtransactions', 'ecatalogue.AcqTransactionRef')
        fields.set_aliases('ebibliography', 'ecatalogue.BibBibliographyRef_tab')
        fields.set_aliases('emultimedia', 'ecatalogue.MulMultiMediaRef_tab')
    else:
        return None
    return fields
