"""Guard the exact ontology bytes required by the deployed S-only artifact."""
import hashlib
from pathlib import Path
import unittest


class OperatingOntologyContractTests(unittest.TestCase):
    def test_csv_bytes_match_operating_model_metadata(self):
        # Metadata read from the actual easy-backend.service artifact on EC2:
        # artifacts/s_only_final_20261124/model.json, not artifacts/s_only/model.json.
        root = Path(__file__).resolve().parents[1]
        digest = hashlib.sha256()
        for file in sorted((root / 'ontology').glob('*.csv')):
            digest.update(file.name.encode())
            digest.update(file.read_bytes())
        self.assertEqual(digest.hexdigest(),
                         '297419463e0ddc58feee56df83599a5f5baddd592820d1637af89c4153e3af2d',
                         'Ontology differs from the deployed model: coordinate CSV and model releases.')


if __name__ == '__main__':
    unittest.main()
