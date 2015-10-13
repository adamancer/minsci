import requests
import requests_cache
import time
import shutil


class MyRequests(object):
    """Extends the requests module with defaults for error handling"""


    def __init__(self, max_requests=100, cache=None):
        self.wait = 3    # default wait between requests
        self.count = 0   # backoffs
        self.base = 5    # backoff length in seconds
        self.max = 320   # max backoff before calling it
        self.max_requests = max_requests
        if cache:
            try:
                shutil.remove(cache + '.sqlite')
            except:
                pass
            else:
                print 'Removed old cache file'
            requests_cache.install_cache(cache)




    def backoff(self, method, url, **kwargs):
        loop = True
        while loop:
            self.response = requests.request(method, url, **kwargs)
            if self.response.status_code == 200:
                self.count = 0
                loop = self.on_response()
            else:
                loop = self.on_error(self.response.status_code)
            time.sleep(self.wait)
        return self.response




    def get(self, url, **kwargs):
        return self.backoff('GET', url, **kwargs)




    def post(self, url, **kwargs):
        return self.backoff('POST', url, **kwargs)




    def on_response(self):
        """Check for validation or TCP/IP errors

        @return boolean  return False to close the loop
        """
        return False




    def on_error(self, status_code):
        """Default backoff scheme based on Twitter's"""
        if status_code == 404:
            return False
        else:
            sleep = self.base * 2 ** self.count
            self.count += 1
            if sleep <= self.max and self.count < self.max_requests:
                print '{} error. Retrying in {}s...'.format(status_code, sleep)
                time.sleep(sleep - self.sleep)
                return True
            else:
                print 'Maximum number of retries made. Request failed.'
                return False
