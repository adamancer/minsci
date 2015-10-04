import os

from minsci.mosaic import selector
from minsci.mosaic import mosey

path = os.path.join(os.path.expanduser('~'), 'Dropbox', '_mosaics')

# Handle user input
#path = os.path.join(path, 'Choteau')
#selector = selector.Selector(path)
#params = selector.get_job_settings()
#selector.select(*params)

mosey(path, jpeg=True)
