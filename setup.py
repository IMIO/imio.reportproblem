"""Shim so that the package can be a zc.buildout develop egg.

Every bit of metadata lives in ``pyproject.toml``, in PEP 621 form; setuptools
reads it from there and this file adds nothing. It exists only because
zc.buildout's ``develop`` runs ``setup.py`` directly, which a PEP 517 only
package cannot satisfy -- the iMio buildouts check this package out into
``src/`` and develop-install it, and without this file that fails with
``FileNotFoundError: setup.py``.
"""

from setuptools import setup


setup()
