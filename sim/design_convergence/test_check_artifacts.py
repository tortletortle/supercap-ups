import unittest
from check_artifacts import validate_acceptance_rows

IDS = ["SYS-001", "CHG-002", "CELL-UV-001", "MUX-002", "SAFE-001",
       "MUX-005", "MUX-006", "MUX-007", "MUX-008", "MUX-009"]

def valid_rows():
    return [{"test_id": i, "subsystem": "x", "scenario": "x",
             "stimulus_or_corner": "x", "measurements": "x",
             "pass_criteria": "x", "status": "MODEL_ONLY"} for i in IDS]

class AcceptanceMatrixTests(unittest.TestCase):
    def test_valid_matrix(self):
        validate_acceptance_rows(valid_rows())

    def test_blank_field_rejected(self):
        rows = valid_rows()
        rows[0]["pass_criteria"] = ""
        with self.assertRaises(SystemExit):
            validate_acceptance_rows(rows)

    def test_duplicate_id_rejected(self):
        rows = valid_rows()
        rows[-1]["test_id"] = rows[0]["test_id"]
        with self.assertRaises(SystemExit):
            validate_acceptance_rows(rows)

    def test_unknown_status_rejected(self):
        rows = valid_rows()
        rows[0]["status"] = "PASSED"
        with self.assertRaises(SystemExit):
            validate_acceptance_rows(rows)

    def test_missing_fault_case_rejected(self):
        rows = [r for r in valid_rows() if r["test_id"] != "MUX-008"]
        with self.assertRaises(SystemExit):
            validate_acceptance_rows(rows)

if __name__ == "__main__":
    unittest.main()
