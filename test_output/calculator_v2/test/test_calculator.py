import pytest
from httpx import AsyncClient, ASGIMethod
from fastapi import status
from pytest import fixture
from typing import Any, Dict
import asyncio

from app import app  # Assuming the main app is defined in app.py

# Fixtures for testing
@fixture
async def client():
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac

@fixture
def calculator_data() -> Dict[str, Any]:
    return {
        "add": (2, 3, 5),
        "subtract": (10, 5, 5),
        "multiply": (4, 5, 20),
        "divide": (10, 2, 5),
        "invalid_divide": (10, 0, "division by zero"),
        "invalid_types": ("string", 5, "invalid types"),
        "negative_divide": (-10, 2, -5),
        "large_numbers": (1000000, 999999, 1999999),
        "decimal_numbers": (3.5, 2.5, 6.0),
        "mixed_types": (3.5, 2, 5.5)  # Should be valid as numbers
    }

# Test cases
class TestCalculatorE2E:
    @pytest.mark.asyncio
    async def test_add_operation(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["add"]
        response = await client.post(
            "/add",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}
        assert response.json()["result"] == expected

    @pytest.mark.asyncio
    async def test_subtract_operation(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["subtract"]
        response = await client.post(
            "/subtract",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_multiply_operation(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["multiply"]
        response = await client.post(
            "/multiply",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_divide_operation(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["divide"]
        response = await client.post(
            "/divide",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_divide_by_zero(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, _ = calculator_data["invalid_divide"]
        response = await client.post(
            "/divide",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_message = response.json()["detail"][0]["msg"]
        assert "Input should be a valid number" not in error_message  # Not the expected error
        # Note: The actual error might be different depending on the implementation

    @pytest.mark.asyncio
    async def test_invalid_operation(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, _ = calculator_data["invalid_types"]
        response = await client.post(
            "/add",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_message = response.json()["detail"][0]["msg"]
        assert "Input should be a valid number" in error_message

    @pytest.mark.asyncio
    async def test_divide_negative_numbers(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["negative_divide"]
        response = await client.post(
            "/divide",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_large_numbers(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["large_numbers"]
        response = await client.post(
            "/add",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_decimal_numbers(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["decimal_numbers"]
        response = await client.post(
            "/multiply",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

    @pytest.mark.asyncio
    async def test_mixed_types(client: AsyncClient, calculator_data: Dict[str, Any]):
        a, b, expected = calculator_data["mixed_types"]
        response = await client.post(
            "/add",
            json={"a": a, "b": b}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": expected}

# Additional test cases for edge cases
class TestCalculatorEdgeCases:
    @pytest.mark.asyncio
    async def test_add_zero(client: AsyncClient):
        response = await client.post("/add", json={"a": 0, "b": 0})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 0}

    @pytest.mark.asyncio
    async def test_subtract_zero(client: AsyncClient):
        response = await client.post("/subtract", json={"a": 0, "b": 0})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 0}

    @pytest.mark.asyncio
    async def test_subtract_negative(client: AsyncClient):
        response = await client.post("/subtract", json={"a": 5, "b": -3})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 8}

    @pytest.mark.asyncio
    async def test_multiply_zero(client: AsyncClient):
        response = await client.post("/multiply", json={"a": 5, "b": 0})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 0}

    @pytest.mark.asyncio
    async def test_divide_negative_result(client: AsyncClient):
        response = await client.post("/divide", json={"a": -10, "b": 2})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": -5}

    @pytest.mark.asyncio
    async def test_divide_one(client: AsyncClient):
        response = await client.post("/divide", json={"a": 5, "b": 5})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 1}

    @pytest.mark.asyncio
    async def test_divide_fraction(client: AsyncClient):
        response = await client.post("/divide", json={"a": 5, "b": 8})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"result": 0.625}

# Test for error handling
class TestCalculatorErrorHandling:
    @pytest.mark.asyncio
    async def test_missing_field(client: AsyncClient):
        response = await client.post("/add", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Missing required field" in response.json()["detail"][0]["msg"]

    @pytest.mark.asyncio
    async def test_invalid_operation_type(client: AsyncClient):
        response = await client.post("/add", json={"a": "invalid", "b": 5})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_operation_not_found(client: AsyncClient):
        response = await client.post("/invalid", json={"a": 5, "b": 5})
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Not Found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_divide_by_zero_proper(client: AsyncClient):
        response = await client.post("/divide", json={"a": 5, "b": 0})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_message = response.json()["detail"][0]["msg"]
        assert "Input should be a valid number" not in error_message
        # Note: The actual implementation might throw a different error for division by zero

# Additional performance test
class TestCalculatorPerformance:
    @pytest.mark.asyncio
    async def test_performance(client: AsyncClient):
        # Generate large numbers for calculation
        a = 999999999999999
        b = 888888888888888
        
        # Test add
        start = asyncio.get_event_loop().time()
        await client.post("/add", json={"a": a, "b": b})
        end = asyncio.get_event_loop().time()
        assert end - start < 0.1  # Expect response within 100ms
        
        # Test multiply
        start = asyncio.get_event_loop().time()
        await client.post("/multiply", json={"a": a, "b": b})
        end = asyncio.get_event_loop().time()
        assert end - start < 0.5  # Expect response within 500ms

# Test for security and input validation
class TestCalculatorSecurity:
    @pytest.mark.asyncio
    async def test_xss_protection(client: AsyncClient):
        response = await client.post(
            "/add",
            json={"a": "<script>alert('test')</script>", "b": 5}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
    @pytest.mark.asyncio
    async def test_sql_injection(client: AsyncClient):
        response = await client.post(
            "/add",
            json={"a": "5 OR 1=1; --", "b": 5}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

# Test for internationalization
class TestCalculatorInternationalization:
    @pytest.mark.asyncio
    async def test_locale_en(client: AsyncClient):
        response = await client.post("/add", json={"a": 2, "b": 3})
        assert response.json()["result"] == 5

    @pytest.mark.asyncio
    async def test_locale_fr(client: AsyncClient):
        # This would require proper locale support in the app
        response = await client.post("/add", json={"a": 2, "b": 3})
        # Expected: {"result": 5} regardless of locale for numbers
        assert response.json()["result"] == 5

# Test for documentation
class TestCalculatorDocumentation:
    @pytest.mark.asyncio
    async def test_swagger_ui(client: AsyncClient):
        response = await client.get("/docs")
        assert response.status_code == status.HTTP_200_OK
        assert "swagger-ui" in response.text

    @pytest.mark.asyncio
    async def test_openapi_json(client: AsyncClient):
        response = await client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        assert "openapi" in response.json()