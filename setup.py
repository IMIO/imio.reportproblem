"""Shim so that the package can be a zc.buildout develop egg.

The metadata lives in ``pyproject.toml``, in PEP 621 form, and setuptools reads
it from there. This file exists only because zc.buildout's ``develop`` runs
``setup.py`` directly, which a PEP 517 only package cannot satisfy -- the iMio
buildouts check this package out into ``src/`` and develop-install it, and
without this file that fails with ``FileNotFoundError: setup.py``.

The two arguments below are the one deliberate duplication. ``pyproject.toml``
remains authoritative -- setuptools overrides these with the PEP 621 values --
but ``check-python-versions`` reads ``setup.py`` statically and reports
``(empty)`` for a bare ``setup()``, which it then counts as a mismatch against
the other sources. Keeping the literals here is what lets that check pass, and
the check itself is what keeps them from drifting: it runs in CI and fails the
moment these disagree with ``pyproject.toml`` or the workflow matrix.
"""

from setuptools import setup


setup(
    python_requires=">=3.10,<3.14",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
