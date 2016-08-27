"""Subclass of dictionary designed to read/store at depth"""
import copy
from collections import Iterable, Mapping

from ...exceptions import PathError
from ...helpers import cprint, rprint


ENDPOINTS = basestring, int, long, float


class DeepDict(dict):

    def __init__(self, *args):
        super(DeepDict, self).__init__(*args)


    def __call__(self, *args):
        """Shorthand for DeepDict.pull(*args)"""
        return self.pull(*args)


    def pull(self, *args):
        """Returns data from the path stipulated by *args

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg

        Returns:
            Value for the given path, if exists
        """
        d = self
        for arg in args:
            try:
                d = d[arg]
            except KeyError:
                raise PathError('/'.join(args))
            except TypeError:
                raise PathError('/'.join(args))
        return d


    def path(self, path, delimiter='/'):
        """Call DeepDict.pull() by passing the path as a delimtied string

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg
            delimiter (str): the character used to delimit the path

        Returns:
            Value for the given path, if exists
        """
        return self.pull(*path.split(delimiter))


    def push(self, val, *args):
        """Add data to the path stipulated by *args

        Args:
            val (mixed): the value to add. Must be a DeepDict or subclass
                thereof if dict-like.
            *args: the path to a value in the dictionary, one component
                per arg. If the last arg is None, the value is not added.
        """
        if isinstance(val, Mapping) and not isinstance(val, DeepDict):
            val = self.__class__(val)
        d = self
        i = 0
        while i < (len(args) - 1):
            if isinstance(args[i+1], (int, long)):
                d = d.setdefault(args[i], [])
                try:
                    d = d[args[i+1]]
                except IndexError, KeyError:
                    d.append(self.__class__())
                    d = d[args[i+1]]
                i += 1
            else:
                d = d.setdefault(args[i], self.__class__())
            i += 1
        if args[-1] is not None:
            d[args[-1]] = val


    def pluck(self, *args):
        """Remove the path stipulated by *args

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg
        """
        args = list(args)
        first = True
        while len(args):
            d = self
            last = args.pop()
            for arg in args:
                d = d[arg]
            if first:
                # The first value is always deleted. After that, empty
                # containers are deleted until a populated one is found.
                val = d.pop(last)
                first = False
            elif isinstance(last, (int, long)) and any(d):
                # Lists with any true-like values are left intact
                pass
            elif not _any(d[last]):
                del d[last]
            else:
                break
        #self.pprint()


    def prune(self, d=None, path=None):
        if path is None:
            d = self
            path = []
        if isinstance(d, basestring):
            # Any non-empty string is considered true
            if not d.strip():
                self.pluck(*path)
            else:
                return True
        elif isinstance(d, (int, long, float)):
            # Any number-like value is considered true
            return True
        elif not d:
            self.pluck(*path)
        else:
            try:
                keys = d.keys()
                is_list = False
            except AttributeError:
                keys = range(len(d))[::-1]  # reverse order, see below
                is_list = True
            for key in keys:
                # DeepDict.pluck() is aggressive, so keys can disappear
                # before they are reached in this loop
                path.append(key)
                try:
                    result = self.prune(d[key], path)
                except KeyError:
                    pass
                path.pop()
                # Stop processing a list if a value is found. This
                # is based on table structure in EMu, where values higher
                # in a column may be blank if values lower in the same
                # column are populated.
                if is_list and result is True:
                    break


    def pprint(self, pause=False):
        """Pretty prints the DeepDict object

        Args:
            pause (bool): if True, waits for user input before continuing
        """
        if pause:
            rprint(self)
        else:
            cprint(self)


def _any(val):
    """Tests if value or any value therein is populated

    Args:
        val (mixed): value to test

    Return:
        True if any value is true-like or 0, otherwise False
    """
    try:
        if val is 0 or 0 in val:
            return True
    except TypeError:
        pass
    return any(val)


def _all_endpoints(iterable):
    """Tests if all values in iterable are a valid end type

    Args:
        iterable (iterable): list of types

    Returns:
        True if all values in iterable are true-like, otherwise False
    """
    return all([True if val is None or isinstance(val, ENDPOINTS) else False
                for val in iterable])


def _all_mappings(iterable):
    """Tests if all values in iterable are a valid end type

    Args:
        iterable (iterable): list of types

    Returns:
        True if all values in iterable are true-like, otherwise False
    """
    return all([True if isinstance(val, Mapping) else False
                for val in iterable])


def _any_value(obj, results=None):
    if results is None:
        results = []
    if isinstance(obj, ENDPOINTS):
        results.append(_any(obj))
        return results
    elif isinstance(obj, Mapping):
        keys = obj.keys()
    elif isinstance(obj, Iterable):
        keys = xrange(len(obj))
    for key in keys:
        results = _any_value(obj[key], results)
    return results
