"""Tests for the fallback chain in main.get_nominated_expiry()."""
from __future__ import annotations

from unittest.mock import patch

from main import get_nominated_expiry


def _c(**kwargs) -> dict:
    """Build a minimal canonical with the supplied keys set."""
    base = {
        "agreement_id": kwargs.pop("agreement_id", "ae999999"),
        "fwc": kwargs.pop("fwc", {}),
        "sections": {
            "front_matter": kwargs.pop("front_matter", {"data": None}),
            "pay_tables": kwargs.pop("pay_tables", {"tables": []}),
        },
    }
    return base


def test_returns_none_when_nothing_is_set():
    canonical = _c()
    with patch("main.fetch_metadata_for_ae_id", return_value=None):
        assert get_nominated_expiry(canonical) is None


def test_front_matter_override_wins_over_fwc_block():
    canonical = _c(
        front_matter={"data": {"nominated_expiry": "2030-12-31"}},
        fwc={"expiry_date": "2027-09-30"},
    )
    with patch("main.fetch_metadata_for_ae_id", return_value={"Expiry Date": "2099-01-01"}):
        assert get_nominated_expiry(canonical) == "2030-12-31"


def test_fwc_canonical_block_used_when_front_matter_empty():
    canonical = _c(
        front_matter={"data": None},
        fwc={"expiry_date": "2027-09-30"},
    )
    with patch("main.fetch_metadata_for_ae_id", return_value={"Expiry Date": "2099-01-01"}):
        assert get_nominated_expiry(canonical) == "2027-09-30"


def test_table_provenance_used_when_fwc_block_empty():
    canonical = _c(
        fwc={},
        pay_tables={
            "tables": [
                {"effective_from": "2024-07-01", "provenance": {"expiry_date": "2027-09-30"}},
            ],
        },
    )
    with patch("main.fetch_metadata_for_ae_id", return_value={"Expiry Date": "2099-01-01"}):
        assert get_nominated_expiry(canonical) == "2027-09-30"


def test_bronze_csv_used_as_last_resort():
    canonical = _c(agreement_id="ae527870")
    with patch("main.fetch_metadata_for_ae_id", return_value={"Expiry Date": "2027-09-28"}):
        assert get_nominated_expiry(canonical) == "2027-09-28"


def test_empty_strings_are_skipped_not_returned():
    canonical = _c(
        front_matter={"data": {"nominated_expiry": "   "}},
        fwc={"expiry_date": ""},
        pay_tables={
            "tables": [
                {"provenance": {"expiry_date": None}},
                {"provenance": {"expiry_date": "2027-09-30"}},
            ],
        },
    )
    with patch("main.fetch_metadata_for_ae_id", return_value=None):
        assert get_nominated_expiry(canonical) == "2027-09-30"


def test_fetch_metadata_exception_is_swallowed():
    canonical = _c()

    def _boom(_ae_id):
        raise RuntimeError("bronze CSV unavailable")

    with patch("main.fetch_metadata_for_ae_id", side_effect=_boom):
        assert get_nominated_expiry(canonical) is None


def test_non_dict_sections_do_not_crash():
    canonical = {"agreement_id": "ae1", "fwc": None, "sections": None}
    with patch("main.fetch_metadata_for_ae_id", return_value=None):
        assert get_nominated_expiry(canonical) is None
