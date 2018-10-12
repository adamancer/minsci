class Site(dict):
    bot = geobots.GeoNamesBot('mansura')

    def __init__(self, data):
        super(Site, self).__init__()
        if not data:
            pass
        elif 'LocCountry' in data:
            self.from_emu(data)
        else:
            raise ValueError(repr(data) + ' is not a Site')


    def clean(self):
        pass



    def from_emu(self, rec):
        # Add basic political info as attributes
        self.country = rec('LocCountry')
        self.state = rec('LocProvinceStateTerritory')
        self.county = rec('LocDistrictCountyShite')


    def to_emu(self):
        pass


    def match(self):
        for feature in self.features():



    def key(self, val):
        val = val.lower().strip()
        if val.endswith(' ca.'):
            val = val[:-4]


    def get_features(self, rec):
        """Identify the most specific feature populated in the record"""
        fields = [
            ('LocMineName', ['MN', 'MNAU', 'MNC', 'MNCR', 'MNCU',
                             'MNFE', 'MNN', 'MNQ', 'MNQR']),
            ('LocTownship', ['P']),
            ('LocTownship', ['L', 'S']),
            ('VolVolcanoName', ['CLDA', 'CONE', 'CRTR', 'VLC']),
            ('LocIslandName', ['ATOL', 'ISL', 'ISLS', 'ISLET',
                               'ISLF', 'ISLM', 'ISLT']),
            ('LocDistrictCountyShire', ['ADM2', 'ADM2H', 'ADM3', 'ADM3H',
                                        'ADM4', 'ADM4H', 'ADM5', 'ADM5H']),
            ('LocDistrictCountyShire', ['L']),
            ('LocMiningDistrict', ['MNA']),
            ('LocGeomorphologicalLocation', ['H', 'L', 'R', 'S',
                                             'T', 'U', 'V']),
            ('LocPreciseLocation', ['A', 'H', 'L', 'P', 'R',
                                    'S', 'T', 'U', 'V']),
            ('LocBaySound', ['BAY', 'SD']),
            ('LocIslandGrouping', ['ATOL', 'ISL', 'ISLS', 'ISLET',
                                   'ISLF', 'ISLM', 'ISLT']),
            ('LocArchipelago', ['ATOL', 'ISL', 'ISLS', 'ISLET',
                                'ISLF', 'ISLM', 'ISLT']),
            ('LocProvinceStateTerritory', ['ADM1', 'ADM1H', 'TERR']),
            ('LocProvinceStateTerritory', ['L']),
            ('LocCountry', ['PCL', 'PCLD', 'PCLF', 'PCLH', 'PCLI', 'PCLIX', 'PCLS']),
            ('LocContinent', ['CONT']),
            ('LocCountry', ['CONT'])
        ]
        # Forbid country-only matches if multiple countries are present
        country = rec('LocCountry')
        if '|' in country or isinstance(country, list) and len(country) > 1:
            fields = [f for f in fields if not f[0] == 'LocCountry']
        pattern = re.compile(r'\bOf\b', re.I)
        features = []
        for field, codes in fields:
            vals = [s.strip() for s in re.split('[:;,]', rec(field))
                    if s and not s.startswith('Locality Key')]
            for val in vals:
                if pattern.search(val) and '(' in val:
                    val = val.split('(', 1)[0].strip()
                features.append((field, val, codes))
        return features
