from ..xmu import XMu, write


GROUPS = XMu(path=None, module='egroups')


def write_group(module, irns_to_group, fp='groups.xml', irn=None, name=None):
    """Create EMu import for egroups based on a list of irns

    Args:
        module (str): the backend name of the module (ecatalogue, eparties, etc)
        irns_to_group (list):
        fp (str): path to write import file to
        irn (int or str): irn of existing group. Either this or name must be
            specified.
        name (str): name of new group. Either this or irn must be specified.
    """

    if irn is None and name is None:
        raise Exception('Must provide either irn or name for the group')
    group = GROUPS.container({
        'GroupType': 'Static',
        'Module': module,
        'Keys_tab': irns_to_group
    })
    if name is not None:
        group['GroupName'] = name
    if irn is not None:
        group['irn'] = irn
    write(fp, [group.expand()], 'egroups')


def group(*args, **kwargs):
    '''Convenience function to maintain functionality of older code'''
    return write_group(*args, **kwargs)
