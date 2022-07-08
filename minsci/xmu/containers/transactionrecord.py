import datetime as dt
import os
import re
from collections import namedtuple

import yaml

from nmnh_ms_tools.records import get_catnum

from .xmurecord import XMuRecord




INACTIVE = ['CANCELLED', 'SUSPENDED']
IN_PREP = ['IN PROCESS', 'READY FOR PROOF', 'APPROVED']
OPEN = ['OPEN', 'OPEN PENDING']
CLOSED = ['CLOSED', 'CLOSED BALANCED', 'CLOSED PENDING', 'CLOSED UNBALANCED']
STATUSES = set(INACTIVE + IN_PREP + OPEN + CLOSED)

Email = namedtuple('Email', ['source', 'email'])
Shipment = namedtuple('Shipment', ['irn', 'number', 'items', 'acknowledged'])




class TransactionItem(XMuRecord):
    """Container for transaction item data"""
    catalog = None
    divs = {'MET', 'MIN', 'PET'}
    code_to_div = {
        'MS': 'DMS',
        'NASA': 'MET',
        'REF': 'PET',
        'REF:CPX': 'PET',
        'REF:OPX': 'PET',
        'SMS': 'PET',
        'USNM': 'MET'
    }
    _transactions = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = 'enmnhtransactionitems'


    @property
    def transaction(self):
        return self['TraTransactionRef']


    def finalize(self):
        """Sets the transaction attribute once the data is read"""
        try:
            tranum = self['TraTransactionRef']['TraNumber']
        except KeyError:
            pass
        else:
            try:
                self['TraTransactionRef'] = self._transactions[tranum]
            except KeyError:
                self['TraTransactionRef'] = TransactionRecord(self['TraTransactionRef'])
                self['TraTransactionRef']['ItmItemRef_tab'] = []
                self._transactions[tranum] = self['TraTransactionRef']

            # Add item to the items grid in transactions. This allows transaction
            # reports to use save/load methods in XMu.
            item = self.__class__({k: v for k, v in self.items() if k.startswith("Itm")})
            self['TraTransactionRef']['ItmItemRef_tab'].append(item)


    def count(self, default=1):
        """Returns object count for this item"""
        try:
            return int(self('ItmObjectCount'))
        except ValueError:
            return default


    def is_outstanding(self):
        """Check if loaned object has been returned"""
        return self['ItmObjectCountOutstanding'] != '0'


    def division(self, check_collection=True):
        """Guesses division"""
        try:
            divs = self._get_divisions(self('ItmCatalogueRef', 'irn'))
            if len(set(divs)) == 1 and divs[0] in self.divs:
                return divs[0]
        except KeyError:
            pass
        div = self.code_to_div.get(self('ItmMuseumCode'), self('ItmMuseumCode'))
        if div in self.divs:
            return div
        if check_collection:
            div = self.collection()[:3].rstrip(':')
            div = self.code_to_div.get(div, div)
            if div in self.divs:
                return div
        return 'DMS'


    def collection(self):
        """Guesses collection"""
        keys = [
            self('ItmCatalogueRef', 'irn'),
            get_catnum(self('ItmCatalogueNumber'))
        ]
        for key in keys:
            try:
                colls = self.get_collections(key)
            except (AttributeError, KeyError, TypeError):
                pass
            else:
                if len(set(colls)) == 1:
                    return colls[0]
                if 'PET: Reference Standards' in colls:
                    return 'PET: Reference Standards'
                if colls:
                    break
        else:
            colls = []
        # Catch some common collections without catalog numbers
        patterns = {
            # Specimen numbers
            r'\b[A-Z]{3}[A-Z ] ?\d{5,6}( ?,\d{1,2})?\b': 'MET: Antarctics',
            r'\b115472-\d+': 'PET: Volcanological Reference',
            r'\b(FRB|GOR|JJG|PHN)[ \-]\d+[A-Z]?\b': 'PET: Ultramafic Xenoliths',
            r'\bVG\b': 'PET: Sea Floor Rocks',
            # Named collections
            r'\bBoyd\b': 'PET: Ultramafic Xenoliths',
            r'\bClague\b': 'PET: Sea Floor Rocks',
            r'\bWilshire\b': 'PET: Ultramafic Xenoliths',
            # Keywords
            r'\b[Dd]iamonds?\b': 'MIN: Gems',
            r'\bBakelite mount\b': 'MIN: Unknown',
            r'\bFrom analyzed powders\b': 'MET: Non-Antarctics',
            r'\b[Ll]avas?\b': 'MET: Volcanological Reference',
            r'\b[Mm]anganese [Nn]odules?\b': 'PET: Sea Floor Rocks',
            r'\b[Tt]ektites?\b': 'MET: Tektites',
            r'\b[Xx]enoliths?\b': 'PET: Ultramafic Xenoliths',

        }
        val = '|'.join([self(k) for k in ['ItmCatalogueNumber',
                                          'ItmDescription',
                                          'ItmObjectName']])
        for pattern, coll in patterns.items():
            if re.search(pattern, val):
                return coll
        # Look for meteorite names
        div = self.division(check_collection=False)
        if div == 'MET' and re.match(r'[A-z ]+', self('ItmObjectName')):
            return 'MET: Non-Antarctics'
        # Could not match collection, but try to get the division at least
        if div == 'DMS':
            divs = [c[:3] for c in colls if c]
            if len(set(divs)) == 1:
                div = divs[0]
        return '{}: Unknown'.format(div)


    def _get_divisions(self, key):
        """Maps an IRN or catalog number to the matching divisions"""
        if self.catalog:
            return [rec['division'] for rec in self.catalog.get(key, [])]
        return []


    def _get_collections(self, key):
        """Maps an IRN or catalog number to the matching collections"""
        collections = []
        if self.catalog:
            for rec in self.catalog.get(key, []):
                if any(['Standards' in c for c in rec['collections']]):
                    collections.append('PET: Reference Standards')
                else:
                    collections.append(rec['primary_collection'])
        return collections




class TransactionRecord(XMuRecord):
    """Container for transaction and transaction item data"""
    config = None
    divs = TransactionItem.divs

    def __init__(self, *args, **kwargs):
        super(TransactionRecord, self).__init__(*args, **kwargs)
        self.module = "enmnhtransactions"
        self.level = 'default'
        self.obscure = False

        self["ItmItemRef_tab"] = [TransactionItem(i) for i in self("ItmItemRef_tab")]


    @property
    def tr_items(self):
        return self("ItmItemRef_tab")


    @staticmethod
    def read_config(fp):
        TransactionRecord.config = parse_config(fp)


    def dunns(self):
        """Gets all unique dunns for this transaction"""
        return sort_mixed_dates(self('LoaDunningDate0'))


    def extensions(self):
        """Gets all unique extensions for this transaction"""
        return sort_mixed_dates(self('LoaExtensionNewDueDate0'))


    def count_items(self):
        """Counts transaction items"""
        count = 0
        for item in self.tr_items:
            count += item.count()
        return count


    def count_dunns(self):
        """Gets the number of dunns since the current due date"""
        dunn_dates = self.dunns()
        due_date = self.due_date()
        num_dunns = len([d for d in dunn_dates if d > due_date])
        # Set escalation level based on number of dunning letters sent already
        if (1 <= num_dunns <= self.config['escalate']
            or (num_dunns and not self.config['escalate'])):
                self.level = 'warn'
        elif num_dunns > self.config['escalate']:
            self.level = 'escalate'
        return num_dunns


    def date_open(self):
        """Gets the date at which the transaction was opened"""
        for key in ['TraDateOpen']:
            date_open = self(key)
            if date_open:
                return date_open


    def due_date(self):
        """Gets the current due date of the loan"""
        due_dates = sort_mixed_dates([self('TraDueDate')] + self.extensions())
        due_dates = [d for d in due_dates if d]
        try:
            due_date = due_dates[-1]
        except (IndexError, TypeError):
            # Enforce a due date of three years after opened/inserted if no
            # due date was given
            if self.is_open() and self('TraType') == 'LOAN OUTGOING':
                print('{}: No due date'.format(self('TraNumber')))
                due_date = add_years(self.date_open(), 3)
            else:
                return
        return due_date


    def is_being_prepared(self):
        """Checks if transaction is being prepared"""
        return (
            self('SecRecordStatus') == 'Active'
            and self('TraStatus') in IN_PREP
        )


    def is_open(self):
        """Checks if loan is open"""
        return (
            self('SecRecordStatus') == 'Active'
            and self('TraStatus') in OPEN
            and not self('TraDateClosed')
        )


    def is_closed(self):
        """Checks if a transaction is closed"""
        return (
            self('SecRecordStatus') == 'Active'
            and self('TraStatus') in CLOSED
        )


    def is_active(self):
        """Checks if a transaction is active"""
        try:
            return self.is_closed() or self.is_open()
        except AssertionError:
            return False


    def is_inactive(self):
        """Checks if a transaction is cancelled or suspended"""
        return (
            self('SecRecordStatus') != 'Active'
            or self('TraStatus') in INACTIVE
        )


    def is_overdue(self, overdue_date=None):
        """Checks if the loan is overdue based on due and extensions dates"""
        if not self.is_active():
            return False
        if overdue_date is None:
            overdue_date = self.config['overdue_date']
        if isinstance(overdue_date, str):
            overdue_date = dt.datetime.strptime(overdue_date, '%Y-%m-%d').date()
        due_date = self.due_date()
        dunn_dates = self.dunns()
        # Check if this loan has been dunned within the past thirty days
        today = dt.datetime.now().date()
        if dunn_dates and (today - dunn_dates[-1]).days <= 30:
            return False
        # Transactions with the wrong type or status are never flagged overdue
        if (not due_date
            or not self.is_open()
            or self('TraType') != 'LOAN OUTGOING'):
                return False
        return due_date < overdue_date


    def is_outgoing_loan(self):
        """Checks if transaction is an outgoing loan"""
        return self('TraType') == 'LOAN OUTGOING'


    def for_scientific_study(self):
        """Checks if transaction is for scientific analysis"""
        subtype = self('TraSubtype').upper()
        if self('TraType') == 'LOAN OUTGOING':
            return subtype in {None, 'ANALYSIS', 'SCIENTIFIC STUDY'}
        elif self('TraType') == 'DISPOSAL':
            return subtype in {'ANALYSIS', 'SCIENTIFIC STUDY'}
        raise ValueError('Only loans and disposals can be for scientific study')


    def acknowledged(self):
        """Checks if all shipments have been acknowledged"""
        if self('TraType') == 'LOAN OUTGOING' or self.for_scientific_study():
            acked = []
            for item in self.tr_items:
                for shipment in item('ProShipmentRef_tab'):
                    acked.append(bool(shipment('DatAcknowledgementDate')))
            all_acked = all(acked)
            if all_acked and not self.is_closed():
                print('{TraNumber}: Acknowledged but not closed'.format(**self))
            return all_acked
        return False


    def contact(self, key=None, role='Primary'):
        """Shorthand method returning metadata about the primary contact"""
        fakes = {
            'Primary': self._fake_contact('Dr. Charlie Scientist'),
            'Original': self._fake_contact('Dr. Tyler Scientist')
        }
        contacts = self('TraTransactorsContactRef_tab')
        roles = self('TraTransactorsRole_tab')
        for contact, role_ in zip(contacts, roles):
            if role_ == role:
                if self.obscure:
                    contact = fakes[role]
                return contact if key is None else contact(key)
        # Check for deceased contacts
        if role == 'Original':
            for contact, role_ in zip(contacts, roles):
                if role_ == 'Primary' and contact('BioDeathDate'):
                    if self.obscure:
                        contact = fakes[role]
                    return contact if key is None else contact(key)


    def orig_contact(self, key=None):
        """Returns original contact for the loan"""
        orig_contact = self.contact(key=key, role='Original')
        if not orig_contact:
            return self.contact(key)
        return orig_contact


    def email(self):
        """Returns email address for the contact"""
        if self.obscure:
            return Email('Person', 'scientist@science.edu')
        try:
            email = self.contact('AddEmail')
            if email:
                return Email('Person', email)
            # Use the organizational email, but only if this loan has been
            # dunned more than once since its last extension
            email = self.organization('AddEmail')
            if email and self.count_dunns() > 2:
                return Email('Organization', email)
        except AttributeError:
            pass


    def contact_org(self):
        """Shorthand method returning the affiliation of the primary contact"""
        if self.obscure:
            return 'Science University'
        orgs = self.contact('AffAffiliationRef_tab.NamOrganisation')
        current = self.contact('AffCurrent_tab')
        if orgs and current:
            for org, current in zip(orgs, current):
                if current == 'Yes':
                    return org


    def organization(self, key='NamOrganisation'):
        """Shorthand method returning name of the primary organization"""
        if self.obscure:
            return 'Science University'
        try:
            org = self('TraTransactorsOrganizationRef_tab')[0]
        except IndexError:
            pass
        else:
            return org if key is None else org(key)


    def get_country(self):
        """Gets the country to which the loan was sent"""
        country = self.organization(key='AddPhysCountry')
        if not country:
            country = self.organization(key='AddPostCountry')
        if not country:
            for item in self.tr_items:
                try:
                    country = item['ProShipmentRef_tab'][0]['ShpCountry']
                    break
                except (IndexError, KeyError):
                    pass
        return country


    def division(self):
        """Determines the division responsible for this transaction"""
        divs = [item.division() for item in self.tr_items]
        if len(set([d for d in divs if d])) == 1 and divs[0] in self.divs:
            return divs[0]
        # Guess the collection based on the initiator
        try:
            initiator = self('TraInitiatorsRef_tab')[0]
        except IndexError:
            # Catches empty initiator grid
            vals = []
        else:
            vals = [
                [initiator('NamFullName')],
                initiator('AffAffiliationRef_tab', 'NamBranch'),
                initiator('AffAffiliationRef_tab', 'NamOrganisation')
            ]
        for val in vals:
            for val in val:
                try:
                    return self.config['initiators'][val]
                except (KeyError, TypeError):
                    pass
        if vals:
            print('Unaffiliated: {NamFullName}'.format(**initiator))
        code = self.config['initiators'].get('default')
        if not code:
            name = vals[0][0]
            raise ValueError('Unaffiliated initiator: {}'.format(name))
        return code


    def collections(self):
        """Determines subcollections for items in this transaction"""

        # Anything assigned to SMS is assign to Reference Standards
        if self.division() == "SMS":
            return {"PET: Reference Standards": len(self.tr_items)}

        collections = {}
        for item in self.tr_items:
            coll = item.collection()
            try:
                collections[coll] += item.count()
            except KeyError:
                collections[coll] = item.count()
        return collections


    def get_collections_contact(self):
        """Identifies the person to contact about a collection"""
        code = self.division()
        contact = self.config['contacts'][self.config['map_contacts'][code]]
        contact['address'] = self.format_address(code)
        return {'coll_' + k: v for k, v in contact.items()}


    def format_address(self, val):
        """Formats the address for a given contact"""
        try:
            contact = self.config['contacts'][val]
        except KeyError:
            contact = self.config['contacts'][self.config['map_contacts'][val]]
        dept = contact.get('dept')
        div = contact.get('div')
        kwargs = {
            'dept': 'Department of {}'.format(dept) if dept else '',
            'div': 'Division of {}'.format(div) if div else '',
            'mrc': str(contact['mrc']).zfill(4)
        }
        return re.sub(r'\n+', '<br />', self.config['address'].format(**kwargs))




def parse_config(fp):
    """Parses the dunning configuration file"""
    config = yaml.safe_load(open(fp, 'r', encoding='utf-8'))
    config['me'] = config['contacts'][config['dunner']]
    # Check overdue date
    if not config['overdue_date']:
        now = dt.datetime.now()
        config['overdue_date'] = dt.date(now.year, now.month, now.day - 1)
    # Confirm that contact emails are consistent
    for key, contact in config['contacts'].items():
        if key != contact['email']:
            raise ValueError('config.yml: Key does not match email'
                             ' for {}'.format(key))
    # Validate dept/div codes against map_contacts
    try:
        config['exclude'] = [s.strip() for s in config['exclude'].split(',')]
    except AttributeError:
        config['exclude'] = []
    for code in config['exclude']:
        if not code in config['map_contacts']:
            raise ValueError('Unrecognized department code: {}'.format(code))
    return config


def add_years(date, num_years=1):
    """Adds number of years to a date, checking for Feb 29 errors"""
    try:
        return date.replace(year=date.year + num_years)
    except ValueError:
        if date.month == 2 and date.day == 29:
            return date.replace(year=date.year + num_years, month=3, day=1)
        raise


def sort_mixed_dates(dates):
    """Sorts mix of dates and date strings"""
    datedict = {}
    for date in dates:
        try:
            key = date.strftime('%Y-%m-%d')
        except AttributeError:
            key = str(date)
        datedict[key] = date
    return [datedict[k] for k in sorted(datedict.keys())]
