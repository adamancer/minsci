from setuptools import setup

# Read long_description from file
try:
    long_description = open('README.rst', 'rb').read()
except:
    long_description = ('Please see https://github.com/adamancer/minsci.git'
                        ' for more information about the MinSci Toolkit.')

setup(name='minsci',
      version='0.30',
      description='Tools for data management in Mineral Sciences at NMNH',
      long_description=long_description,
      classifiers = [
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7'
      ],
      url='https://github.com/adamancer/minsci.git',
      author='adamancer',
      author_email='mansura@si.edu',
      license='MIT',
      packages=['minsci', 'minsci.geotaxa', 'minsci.xmu'],
      install_requires = [
          'inflect',
          'lxml',
          'nameparser',
          'natsort',
          'pymongo',
          'pyodbc'
      ],
      include_package_data=True,
      zip_safe=False)
