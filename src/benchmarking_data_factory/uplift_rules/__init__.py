"""Uplift rules extraction subsystem for eba-workbench.

Public API (stable):
  - schema: dataclasses
  - section_picker: page scoring + regexes
  - rate_cap: resolver + refresh
  - prompt: versioned prompt registry
  - adapters: Adapter protocol + FakeAdapter for tests
  - cache: content-addressed suggestion cache
  - suggest: top-level orchestrator
"""
from benchmarking_data_factory.uplift_rules import (  # noqa: F401
    adapters,
    cache,
    prompt,
    rate_cap,
    schema,
    section_picker,
    suggest,
    table_alignment,
)
from benchmarking_data_factory.uplift_rules.suggest import SuggestConfig, suggest as run_suggest  # noqa: F401
from benchmarking_data_factory.uplift_rules.date_snapper import snap_rule_dates_to_tables  # noqa: F401
from benchmarking_data_factory.uplift_rules.table_alignment import (  # noqa: F401
    build_rule_table_alignment_issues,
    record_rule_table_alignment_issues,
)

__all__ = [
    "adapters",
    "cache",
    "prompt",
    "rate_cap",
    "schema",
    "section_picker",
    "suggest",
    "table_alignment",
    "SuggestConfig",
    "run_suggest",
    "snap_rule_dates_to_tables",
    "build_rule_table_alignment_issues",
    "record_rule_table_alignment_issues",
]
