from setuptools import setup

setup(name='minsci',
      version='0.1',
      description='Tools for data management in Mineral Sciences at NMNH',
      classifiers = [
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7'
      ]
      url='https://github.com/adamancer/minsci.git',
      author='adamancer',
      author_email='mansura@si.edu',
      license='MIT',
      packages=['minsci'],
      install_requires = [
          'inflect',
          'lxml',
          'nameparser',
          'natsort',
          'pillow',
          'pymongo',
          'pyodbc',
          'pyglet'
      ],
      include_package_data=True,
      zip_safe=False)
