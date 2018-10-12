class PreferredSites(object):

    def __init__(self, fp):
        self.conn = sqlite3.connect(fp)
        self.conn.row_factory = dict_factory
        self.cursor = self.conn.cursor()
        self.create_table()
        # Get fields
        self.cursor.execute('SELECT DISTINCT pr_field FROM preferred')
        self.keys = [m['pr_field'] for m in self.cursor.fetchall()]
        self.replace = ('LocCountry',
                        'LocProvinceStateTerritory',
                        'LocIslandName')


    def get_test_values(self):
        self.cursor.execute('SELECT DISTINCT pr_country FROM preferred'
                            ' WHERE pr_state IS NULL')
        countries = []
        for country in [m['pr_country'] for m in self.cursor.fetchall()]:
            countries.extend(country.split('|'))
        return countries


    def normalize(self, val):
        val = val.rstrip('? ')
        for term in (' Ca.', ' (?)'):
            if val.endswith(term):
                val = val[:-len(term)]
        return val if val else None


    def get_values(self, rec, field):
        vals = {
            'field': field,
            'country': rec('LocCountry'),
            'state': rec('LocProvinceStateTerritory'),
            'island': rec('LocIslandName')
        }
        return {k: self.normalize(v) for k, v in vals.iteritems()}


    def create_table(self):
        mask = '''
            CREATE TABLE preferred
            (field TEXT,
             value TEXT,
             country TEXT,
             state TEXT,
             island TEXT,
             PRIMARY KEY (field, value, country, state, island)
             )'''
        try:
            self.cursor.execute(mask)
        except sqlite3.OperationalError:
            pass


    def get_preferred(self, rec, field):
        values = self.get_values(rec, field)
        wheres = ['country = ? and state = ? and island = ?']
        vals = [field, values['country'], values['state'], values['island']]
        if values['country']:
            wheres.append('country = ? and state Is Null and island Is Null')
            vals.append(values['country'])
        if values['state']:
            wheres.append('country = ? and state =? and island Is Null')
            vals.extend([values['country'], values['state']])
        if values['island']:
            wheres.append('country = ? and state Is Null and island = ?')
            vals.extend([values['country'], values['island']])
        where = ' OR '.join(['({})'.format(w) for w in wheres])
        # Insert prefix
        where = re.sub(r'(\b)([a-z])', r'\1pr_\2', where.replace(' and ', ' AND '))
        mask = ('SELECT * FROM preferred'
                ' WHERE pr_field = ? AND ({})').format(where)
        self.cursor.execute(mask, tuple(vals))
        matches = self.cursor.fetchall()
        if len(matches) == 1:
            return matches[0]['pr_field'], matches[0]['pr_value']
        elif matches:
            # Look for the most specific matching record
            for key in ('pr_island', 'pr_state'):
                subset = [m for m in matches if m.get(key)]
                if len(subset) == 1:
                    return subset[0]['pr_field'], subset[0]['pr_value']
            raise ValueError('Multiple matches found: {}'.format(matches))
        return None


    def set_preferred(self, rec, field):
        vals = self.get_values(rec, field)
        keys = ['{}=?'.format(key) for key in sorted(vals.keys())]
        vals = [vals[key] for key in sorted(vals.keys())]
        mask = 'INSERT OR IGNORE INTO preferred SET {}'.format(', '.join(keys))
        #self.cursor.execute(mask, vals)
        self.conn.commit()


    def close(self):
        self.cursor.execute('VACUUM')
        self.conn.commit()
        self.conn.close()


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
