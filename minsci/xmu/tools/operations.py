"""Schedules operations using the EMu Operations module"""
from datetime import timedelta

from dateparser import parse

from ...xmu import XMu, MinSciRecord, write


class Operation(XMu):
    """Contains methods to construct an Operations import file"""

    def __init__(self, *args, **kwargs):
        super(Operation, self).__init__(*args, **kwargs)
        self.module = 'eoperations'
        #self.fields = FIELDS
        self.group = []
        self.records = {}


    def read_notes(self, element):
        """Read notes from EMu record"""
        rec = self.parse(element)
        self.records[rec('irn')] = rec('NotNotes').rstrip('. ')


    def retired_merged(self, element, lookup):
        """Writes import to retire merged records

        Args:
            element (etree.XML): an EMu record as XML
            lookup (dict): contains existing notes keyed to irn
        """
        rec = self.parse(element)
        module = rec('OpeModule')
        if self.module is None:
            self.module = module
        elif module != self.module:
            raise Exception('Multiple modules in record set')
        # Check if all records have been processed
        if rec('NumberToProcess') == rec('NumberProcessed'):
            for irn in rec('IrnsToBeProcessedRef_tab', 'IrnsToBeProcessedRef'):
                notice = ('Retired: Duplicate of'
                          ' irn {}').format(rec('MerTargetRef'))
                try:
                    # Construct a new note from the existing note and the
                    # retirement notice
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


def write_operation(func, module, username, records, date,
                    outpath='operations.xml'):
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
    write(outpath, operations, 'eoperations')


def merge(module, username, primary, duplicates,
          mask=None, date=None, delay=0):
    """Creates an operation to merge a set of duplicates

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
    operation = OPERATIONS.container({
        'MerTargetRef_': primary('irn'),
        'OpeName': mask.format(**primary) if mask is not None else 'Merge',
        'OpeType': 'Merge',
        'OpeModule': module,
        'OpeExecutionTime': 'Yes',
        'OpeRunAsUser': username,
        'OpeNotifyCompleteRef_tab': [
            OPERATIONS.container({'AddEmuUserId' : username})
            ]
        })
    _set_operation_time(operation, date, delay)
    for rec in duplicates:
        operation.setdefault('IrnsToBeProcessedRef_tab_', []).append(rec('irn'))
    return operation.expand()


def delete(module, username, irns_to_delete, name='Delete', date=None, delay=0):
    """Creates an operation to delete a set of records

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
    operation = OPERATIONS.container({
        'OpeName': name,
        'OpeType': 'Delete',
        'OpeModule': module,
        'OpeExecutionTime': 'Yes',
        'OpeRunAsUser': username,
        'OpeNotifyCompleteRef_tab': [
            OPERATIONS.container({'AddEmuUserId' : username})
            ]
        })
    _set_operation_time(operation, date, delay)
    for rec in irns_to_delete:
        operation.setdefault('IrnsToBeProcessedRef_tab', []).append(rec('irn'))
    return operation.expand()


def retire_merged(merged_path, record_path, output='retire.xml'):
    """Write EMu import to retire merged records

    Args:
        merged_path (str):
        record_path (str): path to records(?)
        output (str): path to EMu import file containing the retired records
    """
    # Check for existing notes in the records slated for retirement
    records = Operation(record_path, container=MinSciRecord)
    records.fast_iter(records.read_notes, report=10000)
    # Prepare the update file
    merged = Operation(merged_path, container=MinSciRecord)
    merged.fast_iter(merged.retired_merged, report=1000, lookup=records.records)
    if merged.group:
        write(output, merged.group, merged.module)


def _set_operation_time(operation, date=None, delay=None):
    """Calculates start time for the current operation

    Used to stagger operations throughout the delay. The passed operation is
    modified in place.

    Args:
        operation (xmu.DeepDict): data about the current operation
        date (datetime.datetime): the base date/time for a set of operations
        delay (int): the number of seconds between operations

    Returns:
        The operation data modified to include a starttime
    """
    if delay is not None:
        #date = date.replace(hour=6, minute=31, second=0, microsecond=0)
        date += timedelta(seconds=delay)
        operation['OpeExecutionTime'] = 'No'
        operation['OpeDateToRun'] = date.strftime('%Y-%m-%d')
        operation['OpeTimeToRun'] = date.strftime('%H:%M:%S')
    elif date is not None:
        operation['OpeExecutionTime'] = 'No'
        operation['OpeDateToRun'] = date.strftime('%Y-%m-%d')
        operation['OpeTimeToRun'] = date.strftime('00:00:00')
    return operation
