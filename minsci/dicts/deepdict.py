"""Subclass of dictionary designed to read/store at depth"""
from __future__ import unicode_literals
import pprint as pp
from collections import Mapping


ENDPOINTS = basestring, int, long, float


class DeepDict(dict):
    """Read and retrieve keys from a dict of arbitary depth"""

    def __init__(self, *args):
        super(DeepDict, self).__init__(*args)
        self._attributes = []


    def __call__(self, *args):
        """Shorthand for DeepDict.pull(*args)"""
        return self.pull(*args)


    def __str__(self):
        return pp.pformat(self)


    def clone(self, obj=None):
        """Creates empty instance of DeepDict with key attributes copied over

        The attributes to copy are stored in the DeepDict._attributes, which
        can be defined when initializing a subclass.

        Args:
            obj (dict): a dict to convert into a DeepDict

        Returns:
            Empty DeepDict or subclass thereof
        """
        if obj is not None:
            clone = self.__class__(obj)
        else:
            clone = self.__class__()
        # Add carryover attributes
        for attr in self._attributes:
            setattr(clone, attr, getattr(self, attr, None))
        clone.finalize()
        return clone


    def finalize(self):
        """Runs any functions that require a carryover attribute"""
        pass


    def pull(self, *args):
        """Returns data from the path stipulated by args

        Args:
            args: the path to a value in the dictionary, with one component
                of that path per arg

        Returns:
            Value for the given path, if exists
        """
        val = self
        for arg in args:
            try:
                val = val[arg]
            except KeyError:
                raise KeyError('/'.join(args))
            except TypeError:
                raise KeyError('/'.join(args))
        return val


    def path(self, path, delimiter='/'):
        """Calls DeepDict.pull() by passing the path as a delimited string

        Args:
            path: the path to a value in the dictionary, with one component
                of that path per arg
            delimiter (str): the character used to delimit the path
                if given as a string

        Returns:
            Value for the given path, if exists
        """
        return self.pull(*path.split(delimiter))


    def push(self, val, *args):
        """Adds data to the path stipulated by *args

        Args:
            val (mixed): the value to add
            *args: the path to a value in the dictionary, one component
                per arg. If the last arg is None, the value is not added.
        """
        if isinstance(val, Mapping) and not isinstance(val, DeepDict):
            val = self.clone(val)
        mapping = self
        i = 0
        while i < (len(args) - 1):
            if isinstance(args[i+1], (int, long)):
                mapping = mapping.setdefault(args[i], [])
                try:
                    mapping = mapping[args[i+1]]
                except (IndexError, KeyError):
                    mapping.append(self.clone())
                    mapping = mapping[args[i+1]]
                i += 1
            else:
                mapping = mapping.setdefault(args[i], self.clone())
            i += 1
        if args[-1] is not None:
            mapping[args[-1]] = val


    def pluck(self, *args):
        """Removes all keys and values along the given path

        Args:
            *args: the path to a value in the dictionary, with one component
                of that path per arg
        """
        args = list(args)
        first = True
        while len(args):
            mapping = self
            last = args.pop()
            for arg in args:
                mapping = mapping[arg]
            if first:
                # The first value encountered is always deleted. After that,
                # empty containers are deleted until a populated one is found.
                mapping.pop(last)
                first = False
            elif isinstance(last, (int, long)) and any(mapping):
                # Lists with any true-like values are left intact
                pass
            elif not _any(mapping[last]):
                del mapping[last]
            else:
                break
        #self.pprint()


    def prune(self, mapping=None, path=None):
        """Deletes the branch of the mapping specified by path

        FIXME: The argument structure here is confusing
        FIXME: This vs. pluck?

        Args:
            mapping (DeepDict): the DeepDict object to prune. If None, uses the
                current object.
            path (list): the path to prune
        """
        assert path is not None
        if path is None:
            mapping = self
            path = []
        if isinstance(mapping, basestring):
            # Any non-empty string is considered true
            if not mapping.strip():
                self.pluck(*path)
            else:
                return True
        elif isinstance(mapping, (int, long, float)):
            # Any number-like value is considered true (so zeroes are kept)
            return True
        elif not mapping:
            self.pluck(*path)
        else:
            try:
                keys = mapping.keys()
                is_list = False
            except AttributeError:
                keys = range(len(mapping))[::-1]  # reverse order, see below
                is_list = True
            for key in keys:
                # DeepDict.pluck() is aggressive, so keys can disappear
                # before they are reached in this loop
                path.append(key)
                try:
                    result = self.prune(mapping[key], path)
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
            pause (bool): specifies whether to pause script after printing
        """
        pp.pprint(self)
        if pause:
            raw_input('Paused. Press ENTER to continue.')


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
