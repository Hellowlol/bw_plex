# coding=UTF-8

"""
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

import os
from setuptools import setup

# Possibly convert the README.md to .rst-format
try:
    import pypandoc
    README = pypandoc.convert('README.md', 'rst')
except ImportError:
    print("warning: pypandoc module not found, could not convert Markdown to RST")
    README = open('README.md', 'r').read()


REQ = ['librosa',
       'plexapi',
       'joblib',
       'numpy',
       'docopt',
       'click',
       'scipy',
       'matplotlib',
       'psutil',
       'profilehooks',
       'sqlalchemy',
       'configobj',
       'youtube-dl',
       'beautifulsoup4',
       'html5lib'
]


setup(
    name='bw_plex',

    # Version number is automatically extracted from Git
    # https://pypi.python.org/pypi/setuptools_scm
    # https://packaging.python.org/en/latest/single_source_version.html
    use_scm_version=True,
    setup_requires=['setuptools_scm', 'pypandoc'],
    #version='0.0.1',

    description='Skip intros.',
    long_description=README,

    # The project's main homepage.
    url='https://github.com/Hellowlol/bw_plex',

    # Author details
    author='hellowlol',
    author_email='hellowlol1@gmail.com',

    # Choose your license
    license='GPL3',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: End Users/Desktop',
        'Environment :: Console',
        'Topic :: Multimedia :: Video',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        # Specify the Python versions you support here.
        'Programming Language :: Python :: 2.7',
    ],

    # What does your project relate to?
    keywords='skip intro plex',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=['bw_plex'],


    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=REQ,

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'dev': ['pypandoc']
        #'test': ['pytest', 'codecov', 'pytest-cov'],
    },

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'bwplex=bw_plex.plex:cli',
        ]
    },


)
