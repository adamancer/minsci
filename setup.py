from setuptools import setup, find_packages

# Read long_description from file
try:
    long_description = open('README.rst', 'r').read()
except:
    long_description = ('Please see https://github.com/adamancer/minsci.git'
                        ' for more information about the MinSci Toolkit.')

setup(name='minsci',
      version='0.50',
      description='Tools for data management in Mineral Sciences at NMNH',
      long_description=long_description,
      classifiers = [
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7'
      ],
      url='https://github.com/adamancer/minsci.git',
      author='adamancer',
      author_email='mansura@si.edu',
      license='MIT',
      packages=find_packages(),
      install_requires=[
          'bibtexparser',
          'dateparser',
          'inflect',
          'lxml',
          'nameparser',
          'pillow',
          'pymongo',
          'pyodbc',
          'pytz',
          'requests',
          'requests_cache',
          'unidecode'
      ],
      setup_requires=[
          'bibtexparser',
          'dateparser',
          'inflect',
          'lxml',
          'nameparser',
          'pillow',
          'pymongo',
          'pyodbc',
          'pytz',
          'requests',
          'requests_cache',
          'unidecode'
      ],
      include_package_data=True,
      entry_points={
          'console_scripts' : [
              'minsci = minsci.portal.__main__:main'
          ]
      },
      zip_safe=False)