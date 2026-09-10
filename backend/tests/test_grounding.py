from app.llm_provider import INSUFFICIENT_EVIDENCE, generate_explanation, validate_grounding


def _evidence_and_reasons():
    evidence = {
        "setpoint_c": 4.0,
        "cargo_temp_c": 10.0,
        "external_temp_c": 39.0,
        "route_delay_minutes": 45,
        "weather_data_available": True,
    }
    reasons = [
        {"factor": "temperature_deviation", "value": 6.0, "detail": "Cargo temperature 10.0C exceeds setpoint", "score_contribution": 30},
    ]
    return evidence, reasons


def test_grounded_explanation_passes_validation():
    evidence, reasons = _evidence_and_reasons()
    text = "Cargo temperature 10.0C exceeds the setpoint due to a temperature deviation."
    assert validate_grounding(text, evidence, reasons) is True


def test_ungrounded_explanation_fails_validation():
    evidence, reasons = _evidence_and_reasons()
    # Fabricated text that never engages with the real measured values.
    text = "This shipment looks fine, no issues detected anywhere on the route."
    assert validate_grounding(text, evidence, reasons) is False


def test_empty_explanation_fails_validation():
    evidence, reasons = _evidence_and_reasons()
    assert validate_grounding("", evidence, reasons) is False


def test_insufficient_evidence_literal_passes_validation():
    evidence, reasons = _evidence_and_reasons()
    assert validate_grounding(INSUFFICIENT_EVIDENCE, evidence, reasons) is True


def test_mock_provider_generates_grounded_explanation():
    evidence, reasons = _evidence_and_reasons()
    result = generate_explanation("TRK-014", "HIGH", "DIVERT_TO_FACILITY", evidence, reasons, [])
    assert result.grounded is True
    assert "10.0" in result.text
    assert result.provider == "mock"


def test_pipeline_falls_back_to_insufficient_evidence_when_ungrounded(monkeypatch):
    from app import llm_provider

    monkeypatch.setattr(llm_provider, "_mock_explanation", lambda *a, **k: "Completely unrelated fabricated text.")
    evidence, reasons = _evidence_and_reasons()
    result = generate_explanation("TRK-014", "HIGH", "DIVERT_TO_FACILITY", evidence, reasons, [])
    assert result.grounded is False
    assert result.text == INSUFFICIENT_EVIDENCE
