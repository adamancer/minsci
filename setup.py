from setuptools import setup

setup(name='minsci',
      version='0.1',
      description='Tools for data management in Mineral Sciences at NMNH',
      url='http://windingway.org/minsci',
      author='adamancer',
      author_email='mansura@si.edu',
      license='MIT',
      packages=['minsci'],
      install_requires = [
          'lxml',
          'nameparser',
          'pymongo',
          'pyodbc'
      ],
      include_package_data=True,
      zip_safe=False)
