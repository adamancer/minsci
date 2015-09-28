class Sqlizer:




    def __init__(self, db, charset='utf8', collation='utf8_general_ci'):
        # Create database object
        self.db = db
        self.charset = charset
        self.collation = collation
        self.query = []
        self.spec = {}



        
    def get_header(self):
        self.query += [
            '-- ' + self.db + ' database',
            '--',
            'SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";',
            'SET time_zone = "+00:00";',
            '',
            '/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;',
            '/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;',
            '/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;',
            '/*!40101 SET NAMES utf8 */;',
            '',
            '--',
            '-- Database: `' + self.db + '`',
            '--',
            '',
            'DROP DATABASE IF EXISTS `' + self.db + '`;',
            'CREATE DATABASE `' + self.db + '`' +\
            'DEFAULT CHARACTER SET ' + self.charset  + ' COLLATE ' + self.collation + ';',
            'USE `' + self.db + '`;',
            'FLUSH TABLES;',
            ''
            ]




    def define_fields(self, data):
        # Determine field types based on a LIST of DICTS
        # Analyze data to assign data types
        params = {}
        for row in data:
            # Need to know if a number, max value, and length
            for field in row.keys():
                # Create param entry if does not exist
                try:
                    params[field]
                except:
                    params[field] = { 'length': 0, 'kind' : 'num' }
                # Check boolean
                if row[field].lower() == 'true':
                    row[field] = 1
                elif row[field].lower() == 'false':
                    row[field] = 0
                # Check length
                field_len = len(unicode(row[field]))
                try:
                    if field_len > params[field]['length']:
                        params[field]['length'] = field_len
                except:
                    params[field]['length'] = field_len
                # Check type
                try:
                    float(row[field])
                except:
                    params[field]['kind'] = 'str'
                                    
                    
        # Define fields based on length
        fields = {}
        for field in params:
            length = params[field]['length'] + 1
            kind = params[field]['kind']
            # Is boolean
            if length == 2 and kind == 'num':
                fields[field] = {
                    'definition' : 'TINYINT(1)',
                    'quoted' : False
                    }
            # Is text/memo
            elif length > 255:
                fields[field] = {
                    'definition' : 'TEXT',
                    'quoted' : True
                    }
            # Is varchar
            else:
                fields[field] = {
                    'definition' : 'VARCHAR(' + str(length) + ')',
                    'quoted' : True
                    }
            # Add collation
            try:
                fields[field]['definition'] += self.spec[field]
            except:
                pass
        # Return fields
        return fields




    def create_table(self, table, data, spec={}):
        self.spec = spec # special handling for fields (field name: sql code)
        # Write query to create table based on a LIST of DICTS
        # Define fields
        fields = self.define_fields(data)
        # Get field list in proper order
        for row in data:
            field_list = row.keys()
            break
        # Generate complete field definitions
        definitions = []
        for field in fields:
            definitions.append('\t`' + field + '` ' +\
                               fields[field]['definition'])
        # Initialize queries
        q = [
            '',
            '-- --------------------------------------------------------',
            '',
            '--',
            '-- Table: `' + table + '`',
            '--',
            '',
            'DROP TABLE IF EXISTS `' + table + '`;',
            'CREATE TABLE `' + table + '` (',
            ',\n'.join(definitions),
            ') ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci;',
            '',
            '--',
            '-- Populate data for table `' + table + '`',
            '--'
            ]
        # Add data
        start_insert = [
            '',
            'INSERT INTO `' + table + '` (`' +\
            '`, `'.join(field_list) + '`) VALUES'
            ]
        q += start_insert
        i = 1
        for row in data:
            # Chunk insert every hundred records
            if not i % 100:
                # Replace trailing comma with semicolon
                last = q.pop()
                q.append(last.rstrip(',') + ';')
                q += start_insert
            line = []
            for field, s in row.iteritems():
                s = self.escape_unicode(s)
                if fields[field]['quoted']:
                    s = "'" + s + "'"
                line.append(s)
            q.append('(' + ', '.join(line) + '),')
            i += 1
        # Replace trailing comma with semicolon
        last = q.pop()
        q.append(last.rstrip(',') + ';')
        # Return query
        self.query += q




    def escape_unicode(self, s, escape_char='\\'):
        # String literals to escape before printing
        escape_these = [
            "'",
            '"',
            '\\',
            '%',
            '_'
            ]
        # String literals to print as-is
        print_these = [
            '\b',
            '\n',
            '\r',
            '\t'
            ]
        # Test for unicode
        if not isinstance(s, unicode):
            s = unicode(s)
        # Append escape sequence
        for code in escape_these:
            s = s.replace(code, '[ESCAPEPREFIX]' + code)
        s = s.replace('[ESCAPEPREFIX]', escape_char)
        # Format characters to print
        arr = [repr(c)[2:len(repr(c)) - 1]
               if c in print_these
               else c
               for c in list(s)]
        # Return string
        return ''.join(arr)
            

    
    
