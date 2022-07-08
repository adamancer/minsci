from ..containers.transactionrecord import TransactionRecord, TransactionItem
from ..xmu import XMu
from ..tools.emultimedia.cataloger import Cataloger




class TMu(XMu):
    """Combines all transaction items for one transction"""

    def __init__(self, *args, **kwargs):
        super(TMu, self).__init__(*args, **kwargs)
        self._container = kwargs.pop('container', TransactionItem)
        self.transactions = {}
        self.acquisitions = {}
        self.disposals = {}
        self.loans = {}
        self.for_scientific_study = {}
        self.errors = []
        # Set attributes to save when using autoiterate
        self.keep = [
            'transactions',
            'acquisitions',
            'disposals',
            'loans',
            'for_scientific_study',
            'errors',
        ]


    @staticmethod
    def read_config(fp):
        TransactionRecord.read_config(fp)


    @staticmethod
    def read_catalog(fp):
        def summarize(rec):
            return {
                'catnum': rec.get_catnum(include_div=True),
                'division': rec.get_division(),
                'primary_collection': rec('StaPrimaryCollection'),
                'collections': rec('CatCollectionName_tab'),
            }
        TransactionItem.catalog = Cataloger(fp, summarize=summarize)


    def iterate(self, element):
        """Combines transactions with their transaction items"""
        rec = self.parse(element)
        # Exclude cancelled transctions
        if rec.transaction('TraStatus') == 'CANCELLED':
            return
        self.transactions[rec.transaction('TraNumber')] = rec.transaction
        # Verify that the record maps to a deparment. Do this now so that
        # that we don't read the whole file before getting to an error.
        rec.transaction.division()


    def finalize(self):
        """Splits transactions into acquisitions, disposals, and loans"""
        unknown =[]
        for tranum, transaction in self.transactions.items():
            subtype = transaction.get('TraSubtype').upper()
            if transaction.get('TraType') == 'ACQUISITION':
                self.acquisitions[tranum] = transaction
            elif transaction.get('TraType') == 'DISPOSAL':
                self.disposals[tranum] = transaction
                if transaction.for_scientific_study():
                    self.for_scientific_study[tranum] = transaction
            elif transaction.get('TraType') == 'LOAN OUTGOING':
                self.loans[tranum] = transaction
                if transaction.for_scientific_study():
                    self.for_scientific_study[tranum] = transaction

            for item in transaction.tr_items:
                if "Unknown" in item.collection():
                    unknown.append(
                        str(item.__class__({k: v for k, v in item.items()
                                            if k != 'TraTransactionRef'})))

        with open("unknown_collections.txt", "w", encoding="utf-8") as f:
            for item in unknown:
                f.write(item + "\n\n--------\n\n")
