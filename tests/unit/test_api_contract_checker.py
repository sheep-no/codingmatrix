import pytest
import tempfile
from pathlib import Path

class TestAPIContractChecker:
    @pytest.fixture
    def checker(self):
        from app.agent.api_contract_checker import APIContractChecker
        yield APIContractChecker()
    
    def test_check_consistency(self, checker):
        frontend_files = {"main.js": "fetch('/api/users')"}
        backend_files = {"api.py": "@app.get('/api/users')"}
        
        issues = checker.check_consistency(frontend_files, backend_files)
        
        assert isinstance(issues, list)
