from datetime import timedelta

from dateparser import parse

from .groups import group
from ..deepdict import MinSciRecord
from ..xmu import XMu, write




class Operation(XMu):

    def __init__(self, *args, **kwargs):
        super(Operation, self).__init__(*args, **kwargs)
        self.module = None
        self.group = []
        self.records = {}


    def iterrec(self, element):
        rec = self.read(element).unwrap()
        self.records[rec('irn')] = rec('NotNotes').rstrip('. ')


    def itermerged(self, element, lookup):
        rec = self.read(element).unwrap()
        module = rec('OpeModule')
        if self.module is None:
            self.module = module
        elif module != self.module:
            raise Exception('Multiple modules in record set')
        if rec('NumberToProcess') == rec('NumberProcessed'):
            for irn in rec('IrnsToBeProcessedRef_tab', 'IrnsToBeProcessedRef'):
                notice = 'Retired: Duplicate of irn {}'.format(rec('MerTargetRef'))
                try:
                    note = '\n\n'.join([s for s in [lookup[irn], notice]])
                except KeyError:
                    # IRN doesn't exist, so nothing to do
                    pass
                else:
                    self.group.append(self.container({
                        'irn': irn,
                        'NotNotes': note.lstrip('. ').lstrip(),
                        'SecRecordStatus': 'Retired'
                    }))
        else:
            return True




OPERATIONS = Operation(path=None, module='eoperations')


def operate(func, module, username, records, date, outpath='operations.xml'):
    """Writes an EMu import file containing a set of operations

    Args:
        func (callable): the function used to create the operation
        module (str): the backend name for an EMu module
        username (str): the user whose account will be used to import and run
            the operation
        records (list): a list of records to be operated upon
        date (mixed): the date on which to run the operation as either a
            datetime.datetime object or a parseable date string
        outpath (str): the path to which to write the import file
    """
    try:
        date = parse(date)
    except AttributeError:
        pass
    operations = [func(module, username, date=date, delay=60*i, **rec)
                  for i, rec in enumerate(records)]
    write(fp, operations, 'eoperations')


def merge(module, username, primary, duplicates,
          name_key=None, date=None, delay=0):
    """Create an operation to merge a set of duplicates

    Args:
        module (str): the backend name for an EMu module
        username (str): the user whose account will be used to import and run
            the operation
        primary (int): the irn of the primary record (i.e., the record to
            merged the duplicated into)
        duplicates (list): list of irns to merge into the primary record
        name_key (str): the EMu field name, if any, used to name the operation
        date (datetime.datetime): the base date/time for a set of operations
        delay (int): the number of seconds to between operations

    Returns:
        xmu.DeepDict object containing the merge operation
    """
    op = OPERATIONS.container({
        'MerTargetRef_': primary('irn'),
        'OpeName': primary(name_key) if name_key is not None else 'Merge',
        'OpeType': 'Merge',
        'OpeModule': module,
        'OpeExecutionTime': 'Yes',
        'OpeRunAsUser': username,
        'OpeNotifyCompleteRef_tab': [
            OPERATIONS.container({'AddEmuUserId' : username})
            ]
        })
    _set_operation_time(op, date, delay)
    for rec in duplicates:
        op.setdefault('IrnsToBeProcessedRef_tab', []).append(rec('irn'))
    return op.expand()


def delete(module, username, irns_to_delete, name_key=None, date=None, delay=0):
    """Create an operation to delete a set of records

    Args:
        module (str): the backend name for an EMu module
        username (str): the user whose account will be used to import and run
            the operation
        irns_to_delete (list): list of irns to delete
        name_key (str): the EMu field name, if any, used to name the operation
        date (datetime.datetime): the base date/time for a set of operations
        delay (int): the number of seconds to between operations

    Returns:
        xmu.DeepDict object containing the delete operation
    """
    op = OPERATIONS.container({
        'OpeName': primary(name_key) if name_key is not None else 'Delete',
        'OpeType': 'Delete',
        'OpeModule': module,
        'OpeExecutionTime': 'Yes',
        'OpeRunAsUser': username,
        'OpeNotifyCompleteRef_tab': [
            OPERATIONS.container({'AddEmuUserId' : username})
            ]
        })
    _set_operation_time(op, date, delay)
    for rec in duplicates:
        op.setdefault('IrnsToBeProcessedRef_tab', []).append(rec('irn'))
    return op.expand()


def retire_merged(merged_path, record_path, output='retire.xml'):
    """Write EMu import to retire merged records

    Args:
        merged_path (str):
        record_path (str): path to records(?)
        output (str): path to EMu import file containing the retired records
    """
    # Get data from report at record_path
    records = XMu(record_path, container=MinSciRecord)
    records.fast_iter(records.iterrec, report=10000)
    # Prepare the update file
    merged = XMu(merged_path, container=MinSciRecord)
    merged.fast_iter(merged.itermerged, report=1000, lookup=records.records)
    if merged.group:
        write(output, merged.group, merged.module)




def _set_operation_time(op, date=None, delay=None):
    """Calculates start time for the current operation

    Used to stagger operations throughout the delay. Modifies the passed op
    in place.

    Args:
        op (xmu.DeepDict): data about the current operation
        date (datetime.datetime): the base date/time for a set of operations
        delay (int): the number of seconds between operations

    Returns:
        The operation data modified to include a starttime
    """
    if delay is not None:
        date = date.replace(hour=6, minute=31, second=0, microsecond=0)
        date += timedelta(seconds=delay)
        op['OpeExecutionTime'] = 'No'
        op['OpeDateToRun'] = date.strftime('%Y-%m-%d')
        op['OpeTimeToRun'] = date.strftime('%H:%M:%S')
    elif date is not None:
        op['OpeExecutionTime'] = 'No'
        op['OpeDateToRun'] = date.strftime('%Y-%m-%d')
        op['OpeTimeToRun'] = date.strftime('00:00:00')
    return op
