# -*- coding: utf-8 -*-
"""Helper functions used throughout the minsci module"""
import csv
import datetime as dt
import io
import os
import re
import string
import sys
from copy import copy, deepcopy
from pprint import pprint
from textwrap import fill
try:
    from itertools import zip_longest
except ImportError as e:
    from itertools import izip_longest as zip_longest

import inflect
from nameparser import HumanName
from pytz import timezone
from unidecode import unidecode




def sort_by_reference(lst, order):
    """Reorder list to match order of another list"""
    return sorted(sorted(lst), key=lambda x: _sorter(x, order))


def _sorter(key, order):
    """Returns index in order that starts with key.

    Returns -1 if key not found.
    """
    try:
        return [x for x in range(0, len(order))
                if key.startswith(order[x])][0]
    except KeyError:
        print('Ordering error: {} does not exist in order list'.format(key))
        return -1


def prompt(text, validator, confirm=False,
           helptext='No help text provided', errortext='Invalid response!'):
    """Prompts for and validates user input

    Args:
        text (str): the prompt to present to the user
        validator (mixed): the dict, list, or string used to validate the
            repsonse
        confirm (bool): if true, user will be prompted to confirm value
        helptext (str): text to show if user response is "?"
        errortext (str): text to return if user response does not validate

    Return:
        Validated response to prompt
    """
    # Prepare string
    text = '{} '.format(text.rstrip())
    # Prepare validator
    if isinstance(validator, str):
        validator = re.compile(validator, re.U)
    elif isinstance(validator, dict) and sorted(validator.keys()) == ['n', 'y']:
        text = '{}({}) '.format(text, '/'.join(list(validator.keys())))
    elif isinstance(validator, dict):
        keys = list(validator.keys())
        keys.sort(key=lambda s: s.zfill(100))
        options = ['{}. {}'.format(key, validator[key]) for key in keys]
    elif isinstance(validator, list):
        options = ['{}. {}'.format(i + 1, val) for
                   i, val in enumerate(validator)]
    else:
        raise ValueError('Validator must be dict, list, or str.')
    # Validate response
    loop = True
    num_loops = 0
    while loop:
        # Print options
        try:
            options
        except UnboundLocalError:
            pass
        else:
            print('-' * 60 + '\nOPTIONS\n-------')
            for option in options:
                cprint(option)
            print('-' * 60)
        # Prompt for value
        val = input(text)#.decode(sys.stdin.encoding)
        if val.lower() == 'q':
            print('User exited prompt')
            sys.exit()
        elif val.lower() == '?':
            print(fill(helptext))
            loop = False
        elif isinstance(validator, list):
            try:
                result = validator[int(val) - 1]
            except IndexError:
                pass
            else:
                if num_loops >= 0:
                    loop = False
        elif isinstance(validator, dict):
            try:
                result = validator[val]
            except KeyError:
                pass
            else:
                loop = False
        else:
            try:
                validator.search(val).group()
            except AttributeError:
                pass
            else:
                result = val
                loop = False
        # Confirm value, if required
        if confirm and not loop:
            try:
                result = str(result)
            except UnicodeEncodeError:
                result = str(result)
            loop = prompt('Is this value correct: "{}"?'.format(result),
                          {'y' : False, 'n' : True}, confirm=False)
        elif loop:
            print(fill(errortext))
        num_loops += 1
    # Return value as unicode
    return result


def localize_datetime(timestamp, timezone_id='US/Eastern',
                      mask='%Y-%m-%dT%H:%M:%S'):
    """Loclaizes timestamp to specified timezone

    Returns:
        Localized datetime as formatted according to the mask
    """
    localized = timezone(timezone_id).localize(timestamp)
    if mask is not None:
        return localized.strftime(mask)
    return localized


def write_emu_search(mask, catnums, output='search.txt'):
    nums = list({str(n).split('-')[0] for n in catnums})
    nums.sort(key=lambda n: int(n))
    if mask.endswith('.txt'):
        mask = open('mask.txt', 'r').read()
    search = ['\t(\n\t\tCatNumber = {}\n\t)'.format(cn) for cn in nums]
    with open(output, 'w') as f:
        f.write(mask.format('\n\tor\n'.join(search)))
    print('The following catalog records were not found:')
    print('\n'.join(sorted(nums)))




class FileLike:

    def __init__(self, filelike, zip_file=None):
        self.path = None
        self.zip_info = None
        self.zip_file = None
        if zip_file:
            self.zip_info = filelike
            self.zip_file = zip_file
        else:
            self.path = os.path.realpath(filelike)


    def __str__(self):
        return self.path if self.path else self.zip_info.filename


    def open(self, mode='r', encoding=None):
        """Opens a file or ZipInfo object"""
        if not self.zip_info:
            return open(self.path, mode=mode, encoding=encoding)
        stream = self.zip_file.open(self.zip_info, mode.rstrip('b'))
        if encoding:
            return ByteDecoder(stream, encoding)
        return stream


    def getmtime(self):
        """Returns last modification datetime from a file or ZipInfo object"""
        try:
            return dt.datetime.fromtimestamp(int(os.path.getmtime(self.path)))
        except TypeError:
            return dt.datetime(*self.zip_info.date_time)




class ByteDecoder:
    """File-like context manager that encodes a binary stream from a zip file"""

    def __init__(self, stream, encoding):
        self._stream = stream
        self._encoding = encoding


    def __iter__(self):
        for line in self._stream:
            yield line.decode(self._encoding)


    def __enter__(self):
        return self


    def __exit__(self, exc_type, exception, traceback):
        if exception:
            raise exception
        self._stream.close()
