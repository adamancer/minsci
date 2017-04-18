import requests
import requests_cache


requests_cache.install_cache('refs')


class BibBot(requests.Session):

    def __init__(self, *args, **kwargs):
        super(BibBot, self).__init__(*args, **kwargs)
        self.headers.update({'User-Agent': 'SmithsonianBot (mansura@si.edu)'})


    def download(self, url, path=None):
        # Verify url
        url = 'http' + url.split('http')[1]
        print 'Checking {}...'.format(url)
        try:
            # Steam is ignored when using requests_cache
            response = self.get(url, stream=True)
        except:
            raise
        else:
            if response.status_code == 200:
                if path is not None:
                    print 'Writing to {}...'.format(path)
                    with open(path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=4096):
                            if chunk:
                                f.write(chunk)
                    time.sleep(5)
                else:
                    return response.content
