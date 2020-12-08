"""Writes import for egroups based on a list of irns"""
from ..xmu import XMu, write


GROUPS = XMu(path=None, module='egroups')


def write_group(module, irns, fp='group.xml', irn=None, name=None):
    """Create EMu import for egroups based on a list of irns

    Args:
        module (str): the backend name of the module (ecatalogue, eparties, etc)
        irns (list): list of irns to include in the group
        fp (str): path to write import file to
        irn (int or str): irn of existing group. Either this or name must be
            specified.
        name (str): name of new group. Either this or irn must be specified.
    """
    if irn is None and name is None:
        raise ValueError('Must provide either irn or name for the group')
    if not module in list(GROUPS.fields.schema.keys()):
        raise ValueError('{} is not a valid module'.format(module))
    if not irns:
        raise ValueError('No irns provided')
    group = GROUPS.container({
        'GroupType': 'Static',
        'Module': module,
        'Keys_tab': irns
    })
    if name is not None:
        group['GroupName'] = name
    if irn is not None:
        group['irn'] = irn
    write(fp, [group.expand()], 'egroups')
