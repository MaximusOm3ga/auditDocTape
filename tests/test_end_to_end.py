import pytest
from app.agents.conflict_detector import detect_conflicts, values_conflict, severity, filter_superseded_pairs
from app.agents.validator import validate_claim, ValidationError
from app.agents.verifier import numeric_conflict_analysis, verify_invoice_vs_contract


class TestClaimExtraction:

    def test_valid_claim_extraction(self):
        claim = {
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "unit": "days",
            "confidence": 0.95
        }
        assert validate_claim(claim, "contract") is True
    
    def test_invalid_predicate_rejection(self):
        claim = {
            "subject": "Vendor_A",
            "predicate": "billing_window",
            "value": "30",
            "value_type": "number",
            "confidence": 0.95
        }
        
        with pytest.raises(ValidationError):
            validate_claim(claim, "contract")
    
    def test_missing_required_field(self):
        claim = {
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value_type": "number",
        }
        
        with pytest.raises(ValidationError):
            validate_claim(claim, "contract")
    
    def test_invalid_confidence(self):
        claim = {
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "confidence": 1.5  # Invalid
        }
        
        with pytest.raises(ValidationError):
            validate_claim(claim, "contract")


class TestConflictDetection:

    def test_genuine_conflict_detection(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "doc_id": "doc_1",
            "claim_id": "claim_1",
            "effective_date": "2025-01-01"
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "45",
            "value_type": "number",
            "doc_id": "doc_2",
            "claim_id": "claim_2",
            "effective_date": "2025-01-01"
        }
        
        assert values_conflict(claim_a, claim_b) is True
    
    def test_numeric_tolerance(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "contract_value",
            "value": "1000.00",
            "value_type": "currency",
            "doc_id": "doc_1"
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "contract_value",
            "value": "1000.50",
            "value_type": "currency",
            "doc_id": "doc_2"
        }
        
        assert values_conflict(claim_a, claim_b) is False
    
    def test_type_mismatch_no_conflict(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "renewal_date",
            "value": "2025-12-31",
            "value_type": "date",
            "doc_id": "doc_1"
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "renewal_date",
            "value": "2025-12-31",
            "value_type": "string",
            "doc_id": "doc_2"
        }
        
        assert values_conflict(claim_a, claim_b) is False
    
    def test_same_doc_no_conflict(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "doc_id": "doc_1",
            "claim_id": "claim_1"
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "45",
            "value_type": "number",
            "doc_id": "doc_1",
            "claim_id": "claim_2"
        }
        
        conflicts = detect_conflicts([claim_a, claim_b])
        assert len(conflicts) == 0
    
    def test_entity_isolation(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "doc_id": "doc_1",
            "claim_id": "claim_1"
        }
        
        claim_b = {
            "entity": "Vendor_B",
            "subject": "Vendor_B",
            "predicate": "payment_terms_days",
            "value": "45",
            "value_type": "number",
            "doc_id": "doc_2",
            "claim_id": "claim_2"
        }
        
        conflicts = detect_conflicts([claim_a, claim_b])
        assert len(conflicts) == 0
    
    def test_severity_scoring_high_stakes_predicate(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "60",
            "value_type": "number",
        }
        
        sev_low = severity(claim_a, claim_b)
        
        claim_c = claim_a.copy()
        claim_c["predicate"] = "contract_value"
        claim_d = claim_b.copy()
        claim_d["predicate"] = "contract_value"
        
        sev_high = severity(claim_c, claim_d)
        
        assert sev_high > sev_low


class TestSupersessionHandling:

    def test_supersession_filtering(self):
        claim_from_original = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "30",
            "value_type": "number",
            "doc_id": "contract_v1",
            "claim_id": "claim_1"
        }
        
        claim_from_amendment = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "payment_terms_days",
            "value": "45",
            "value_type": "number",
            "doc_id": "amendment_v1",
            "claim_id": "claim_2"
        }
        supersession_map = {
            "amendment_v1": "contract_v1"
        }
        
        conflicts = detect_conflicts([claim_from_original, claim_from_amendment], supersession_map)
        assert len(conflicts) == 0


class TestNumericVerification:

    def test_numeric_conflict_within_tolerance(self):
        claim_a = {"value": "1000", "value_type": "currency"}
        claim_b = {"value": "1020", "value_type": "currency"}
        
        result = numeric_conflict_analysis(claim_a, claim_b, tolerance_percent=5.0)
        
        assert result["is_significant"] is False
    
    def test_numeric_conflict_exceeds_tolerance(self):
        claim_a = {"value": "$1000", "value_type": "currency"}
        claim_b = {"value": "$2000", "value_type": "currency"}
        
        result = numeric_conflict_analysis(claim_a, claim_b, tolerance_percent=5.0)
        
        assert result["is_significant"] is True
        assert result["percent_difference"] > 5.0
    
    def test_invoice_vs_contract_verification(self):
        result = verify_invoice_vs_contract(
            invoice_amount=1000.0,
            invoice_currency="USD",
            contract_amount=1000.0,
            contract_currency="USD",
            tolerance_percent=2.0
        )
        
        assert result["matches"] is True
        assert result["variance_percent"] == 0.0
    
    def test_invoice_vs_contract_mismatch(self):
        result = verify_invoice_vs_contract(
            invoice_amount=1000.0,
            invoice_currency="USD",
            contract_amount=1200.0,
            contract_currency="USD",
            tolerance_percent=2.0
        )
        
        assert result["matches"] is False
        assert result["variance_percent"] > 10.0


class TestScopeAwareness:

    def test_different_time_periods(self):
        claim_a = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "revenue",
            "value": "1000000",
            "value_type": "currency",
            "doc_id": "report_2024",
            "effective_date": "2024-12-31"
        }
        
        claim_b = {
            "entity": "Vendor_A",
            "subject": "Vendor_A",
            "predicate": "revenue",
            "value": "500000",
            "value_type": "currency",
            "doc_id": "report_2025_q1",
            "effective_date": "2025-03-31"
        }
        conflicts = detect_conflicts([claim_a, claim_b])
        assert len(conflicts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

