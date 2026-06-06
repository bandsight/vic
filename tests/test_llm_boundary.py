from benchmarking_data_factory.workbench.llm_boundary import (
    is_llm_error,
    llm_failure_detail,
    provider_status,
    vision_required_detail,
)


def test_provider_status_marks_missing_anthropic_key_as_blocked():
    status = provider_status({}, "claude-sonnet-4-6")

    assert status["provider"] == "anthropic"
    assert status["ready"] is False
    assert status["vision_capable"] is False
    assert status["message"] == "ANTHROPIC_API_KEY not set"
    assert vision_required_detail(status)["status"] == "blocked"


def test_llm_failure_detail_strips_error_prefix_but_preserves_action():
    detail = llm_failure_detail(
        "ERROR: TimeoutError: request timed out",
        action="extract_pay_table_page",
        message="Pay-table extraction failed.",
        provider="anthropic",
        model="claude-sonnet-4-6",
    )

    assert is_llm_error("ERROR: no key")
    assert detail["status"] == "llm_error"
    assert detail["action"] == "extract_pay_table_page"
    assert detail["reason"] == "TimeoutError: request timed out"
