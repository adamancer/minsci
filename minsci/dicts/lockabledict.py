from __future__ import unicode_literals
class LockableDict(dict):

    def __init__(self, *args, **kwargs):
        super(LockableDict, self).__init__(*args, **kwargs)
        self._locked = False


    def __setitem__(self, key, val):
        if self._locked:
            raise RuntimeError('Dictionary is locked')
        super(LockableDict, self).__setitem__(key, val)


    def lock(self):
        self._locked = True


    def unlock(self):
        self._locked = False
