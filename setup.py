#!/usr/bin/env python

import re
from setuptools import setup, find_packages


# Get the version from the main script
version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open("wayback_machine_archiver/archiver.py").read(),
    re.M,
).group(1)


# Try to import pypandoc to convert the readme, otherwise ignore it
try:
    import pypandoc
    long_description = pypandoc.convert_file("README.md", "rst", format="md")
except ImportError:
    long_description = ""

# Configure the package
setup(
    name="wayback-machine-archiver",
    version=version,
    description="A Python script to submit web pages to the Wayback Machine for archiving.",
    long_description=long_description,
    author="Alexander Gude",
    author_email="alex.public.account@gmail.com",
    url="https://github.com/agude/wayback-machine-archiver",
    license="MIT",
    platforms=["any"],
    packages=["wayback_machine_archiver"],
    entry_points={
        "console_scripts": [
            "archiver=wayback_machine_archiver.archiver:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Utilities",
    ],
    keywords=[
        "Internet Archive",
        "Wayback Machine",
    ],
    install_requires=[
        "requests",
    ],
    setup_requires=[
        "pypandoc",
        "pytest-runner",
    ],
    tests_require=["pytest"],
    python_requires=">=2.6, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, <4",
)
