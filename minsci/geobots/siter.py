DEBUG = False

COUNTRIES = {
    'East Germany': 'Germany',
    'West Germany': 'Germany'
}

ENDING_MAP = {
    'LocCountry': 'admin',
    'LocProvinceStateTerritory': 'admin',
    'LocDistrictCountyShire': 'admin',
    'LocArchipelago': 'islands',
    'LocIslandGrouping': 'islands',
    'LocIslandName': 'islands',
    'LocMineName': 'mine'
}


class XMu(xmu.XMu):

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.bot = geobots.GeoNamesBot('mansura')
        self.updates = []  # results is a list of self.containers
        db_path = os.path.join(self.dirname(self.__file__), 'files', 'preferred.db')
        self.preferred = PreferredSites(db_path)
        self.test_vals = []
        if DEBUG:
            self.test_vals = self.preferred.get_test_values()


    def finalize(self):
        self.preferred.close()


    def iterate(self, element):
        rec = self.parse(element)
        if DEBUG and not rec('LocCountry') in self.test_vals:
            return True
        rec = self.clean_rec(rec)
        # Identify the most specific feature in the record
        features = self.get_features(rec)
        misses = []
        for i, feature in enumerate(features):
            field, val, codes = feature
            matches = self.match_feature(rec, field, val, codes)
            if len(matches) == 1:
                # Check for existing sites
                operator = self.find_existing_stations(rec)
                if isinstance(operator, bool):
                    return operator
                self.construct_update(rec('irn'), matches, field, operator, i)
                break


    def iter2(self, element):
        try:
            self.countries
        except AttributeError:
            self.countries = {}
        rec = self.parse(element)
        rec = self.clean_rec(rec)
        countries = rec('LocCountry').split('|')
        for country in countries:
            if not country or country in self.countries:
                return True
            codes = ['PCL', 'PCLD', 'PCLF', 'PCLH', 'PCLI', 'PCLIX', 'PCLS']
            matches = self.match_feature(rec, 'LocCountry', country, codes)
            gid = None
            if matches:
                gid = matches[0]['geonameId'] if matches else None
            print country, '=>', gid
            self.countries[country] = gid



    def match_feature(self, rec, field, val, codes):
        """Matches a single feature in GeoNames"""
        # Query GeoNames
        country, state, county = self.get_general_info(rec, field)
        kind = ENDING_MAP.get(field)
        try:
            response = self.bot.search(normalize_name(val, kind, True), country,
                                       **{self.feature_kind(codes): codes})
        except RuntimeError:
            print 'Out of credits!'
            return False
        # Filter and write matches
        matches = self.filter_matches(response, val, kind,
                                      country, state, county)
        if country is not None and len(country) > 20:
            country = country[:17] + '...'
        if val is not None and len(val) > 20:
            val = val[:17] + '...'
        locality = ', '.join([s for s in (county, state, country) if s])
        if len(matches) == 1:
            mask = u'Hit: {} ({})'
        else:
            mask = u'Miss: {{}} ({{}}) [{} matches on {}]'.format(len(matches), rec('irn'))
        print mask.format(val, locality).encode('utf-8').replace(' ()', '')
        return matches


    def clean_rec(self, rec):
        # Get rid of circa modifier on admin areas
        for key in ('LocCountry', 'LocProvinceStateTerritory',
                    'LocDistrictCountyShire', 'LocTownship'):
            val = rec(key)
            if val.endswith(' Ca.') and val.count('Ca.') == 1:
                rec[key] = val[:-4]
        # Get preferred values for certain names. Run multiple times to
        # catch changes in countries, etc. on previous passes.
        orig = {key: val for key, val in rec.iteritems()}
        for i in xrange(3):
            update = {}
            for field in self.preferred.keys:
                preferred = self.preferred.get_preferred(rec, field)
                if preferred:
                    fld, val = preferred
                    if field in self.preferred.replace:
                        update[field] = val
                    else:
                        # Append value if not a country, state, or island
                        update.setdefault(field, '')
                        update[field] = update[field] + u'; {}'.format(val)
                        update[field] = update[field].strip('; ')
            rec.update(update)
        # Look for duplicated data
        if rec('LocContinent') == rec('LocCountry') and rec('LocCountry') != 'Australia':
            rec['LocCountry'] = ''
        # Track changes to the record
        if DEBUG and orig != rec:
            keys = sorted(list(set(rec.keys() + orig.keys())))
            print '-' * 60
            for key in keys:
                if rec.get(key) != orig.get(key):
                    print u'{}: {} => {}'.format(key, orig.get(key), rec.get(key))
            #raw_input()
        return rec


    def enhance_site(self, geonames_id):
        try:
            matches = self.bot.get_by_id(geonames_id)
        except RunTimeError:
            return False
        else:
            self.construct_update(matches, )
            return True


    


    def parse_label(self, field):
        label = []
        for char in field[3:]:
            if char == char.upper():
                label.append(' ')
            label.append(char)
        label = ''.join(label).strip().lower()
        if label.startswith(('district', 'province')):
            label = label.replace(' ', '/')
        return label


    def feature_kind(self, codes):
        """Test if feature code or class"""
        classes = [code for code in codes if len(code) == 1]
        codes = [code for code in codes if len(code) != 1]
        if classes and codes:
            raise ValueError('Mixed codes and classes: {}'.format(codes))
        return 'featureClass' if classes else 'featureCode'


    def find_existing_stations(self, rec):
        # Check for existing station
        source = rec('LocSiteNumberSource')
        gid = None
        if source and source == 'GeoNames':
            gid = rec('LocSiteStationNumber')
        # Check for existing Sites Notes
        sites_notes = rec('NteType_tab')
        label = 'Sites Notes'
        try:
            i = sites_notes.index(label)
        except ValueError:
            operator = '+'
        else:
            operator = '{}='.format(i + 1)
        if gid is not None and not sites_notes:
            return self.enhance_site(gid)
        return operator


    def get_general_info(self, rec, field):
        fields = [
            'LocCountry',
            'LocProvinceStateTerritory',
            'LocDistrictCountyShire'
            ]
        country = None
        if not field in fields[:1]:
            country = rec('LocCountry')
            country = COUNTRIES.get(country, country)
        state = None
        if not field in fields[:2]:
            state = rec('LocProvinceStateTerritory')
        county = None
        if not field in fields:
            county = rec('LocDistrictCountyShire')
        return country, state, county


    def filter_matches(self, response, val, kind, countries,
                       state=None, county=None):
        filtered = response.filter_matches(countries=countries,
                                           state=state,
                                           county=county)
        return filtered.match_name(val, kind)



    def construct_update(self, irn, matches, field, operator='+', i=0):
        matched_on = matches.matched_on
        site = matches.get_site_data()[0]
        if field == 'GeoNames ID':
            manual = 'anually '
            crtiera = ''
        else:
            matched_on = [self.parse_label(field)] + matched_on[::-1]
            manual = ''
            criteria = 'based on {}'.format(oxford_comma(matched_on))
        note = (u'M{}atched to {} ({}) in'
                 ' {} {}').format(manual, site.names[0], site.id,
                                  site.source, criteria).strip()
        if i:
            note += ('. This record contains other, more specific locality'
                     ' information that could not be matched automatically.')
        self.updates.append(self.container({
            'irn': irn,
            'LocRecordClassification': site.code if site.code else site.kind,
            'LocSiteStationNumber': site.id,
            'LocSiteNumberSource': site.source,
            'LocSiteName_tab': site.names,
            'LatGeoreferencingNotes0': [note]
        }).expand())
