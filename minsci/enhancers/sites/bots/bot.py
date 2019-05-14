import os
import time

import requests
import requests_cache


class Bot(requests_cache.CachedSession):
    """Methods to handle and retry HTTP requests for georeferencing"""

    def __init__(self, wait, *args, **kwargs):
        self.quiet = kwargs.pop('quiet', False)
        super(Bot, self).__init__(*args, **kwargs)
        self.wait = wait


    def _retry(self, func, *args, **kwargs):
        """Retries failed requests using a simple exponential backoff"""
        for i in range(8):
            try:
                response = func(*args, **kwargs)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                seconds = 30 * 2 ** i
                print('Retrying in {:,} seconds...'.format(seconds))
                time.sleep(seconds)
            else:
                if not response.from_cache:
                    #if not self.quiet:
                    #    print('Resting up for the big push...')
                    time.sleep(self.wait)
                return response
        raise Exception('Maximum retries exceeded')
