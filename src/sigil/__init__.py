"""Sigil: scrape -> validate -> flag social posts against platform policy.

A single installable package exposing:
  * ``sigil`` CLI (validate / report / stats / scrape)
  * ``sigil-scheduler`` long-running runner + collector + validator + status loops
    (select a subset with ``--only``)
  * ``sigil-validator`` shortcut for ``sigil-scheduler --only validator``
  * ``sigil-migrate`` SQL migration runner
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
