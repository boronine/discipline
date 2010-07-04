#!/usr/bin/python

# Use setuptools if we can
try:
    from setuptools.core import setup
except ImportError:
    from distutils.core import setup
from discipline import __version__

setup(
    name='Discipline',
    version=__version__,
    description='Discipline: model version control for Django',
    long_description="Discipline is a model version control system for " \
        "Django with admin website integration and low-level APU for " \
        "accessing objects' states at different points in time",
    author="Alexei Boronine",
    license="MIT",
    author_email="alexei.boronine@gmail.com",
    url="http://github.com/alexeiboronine/discipline",
    download_url="http://github.com/alexeiboronine/discipline/downloads",
    keywords="django versioning version control",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
    packages=[
        "discipline",
        "discipline.management",
        "discipline.management.commands",
    ],
)
