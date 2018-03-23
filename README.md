MinSci Toolkit
==============

A collection of tools written in Python 2.7 to wrangle data in Axiell EMu for
Mineral Sciences at NMNH.


Installation
------------

The minsci package exists on PyPI, but I don't do well keeping it up-to-date,
so it's better to install directly from github. Python 2.7 and git are both
required. Once you have those installed, run the following from your command
prompt:

```
cd /path/to/directory
git clone https://github.com/adamancer/minsci
cd minsci
python setup.py install
```

Once you've finished installing the package, there are a few clean up steps
that you can do to better tailor things to your EMu:

+ Copy your institution's schema.pl file to minsci/xmu/files. This allows the
  script to validate paths when reading and writing data.
+ Define grids in minsci/xmu/files/tables. This allows the script to verify
  that all columns have the right number of rows. **The default grids are
  NMNH-specific and should be deleted and replaced.** It's a good idea to
  define any grids you'll be writing to.


Basic usage
-----------

Most common operations involved subclassing XMu to read an export file. A
very basic framework for this operation is:

```python
from minsci import xmu

class XMu(xmu.XMu):

    def __init__(self, *args, **kwargs):
        super(XMu, self).__init__(*args, **kwargs)
        self.records = {}


    def iterate(self, element):
        rec = self.parse(element)
        # Do stuff...

xmudata = XMu('xmldata.xml')
xmudata.fast_iter(report=1000)
```

Examples of common operations, include a sample EMu export file, are provided
in https://github.com/adamancer/minsci/tree/master/minsci/examples.
