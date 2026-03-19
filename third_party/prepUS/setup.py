from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

version = {}
with open(path.join(here, "prepUS", "__version__.py")) as f:
    exec(f.read(), version)

setup(
    name="prepUS",
    version=version["__version__"],
    description="Utility script for ultrasound videos pre-processing.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Chop1/prepUS",
    author="MEYER Adrien",
    license="Apache Software License 2.0",
    packages=find_packages(),
    python_requires=">=3.6",
    # sonocrop doit être installé séparément avec --no-deps
    install_requires=["sonocrop"],
    entry_points={
        "console_scripts": [
            "prepUS=prepUS.cli:main",
        ],
    },
)
