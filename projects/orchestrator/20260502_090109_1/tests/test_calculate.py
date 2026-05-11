# tests/test_calculate.py
import pytest
from calculate import calculate

def test_add_integers():
    """Test adding two integers"""
    result = calculate(2, 3)
    assert result == 5, "Should return sum of two integers"

def test_add_floats():
    """Test adding two floats"""
    result = calculate(2.5, 3.5)
    assert result == 6.0, "Should return sum of two floats"

def test_add_integer_and_float():
    """Test adding an integer and a float"""
    result = calculate(2, 3.5)
    assert result == 5.5, "Should return sum of integer and float"

def test_non_numeric_input():
    """Test non-numeric input raises TypeError"""
    with pytest.raises(TypeError):
        calculate("2", 3)
    with pytest.raises(TypeError):
        calculate(None, 5)
    with pytest.raises(TypeError):
        calculate([1, 2], 3)
    with pytest.raises(TypeError):
        calculate({1: 2}, 3)
    with pytest.raises(TypeError):
        calculate((1, 2), 3)
    with pytest.raises(TypeError):
        calculate(set([1, 2]), 3)

def test_negative_numbers():
    """Test adding negative numbers"""
    result = calculate(-2, -3)
    assert result == -5, "Should handle negative integers"
    result = calculate(-2.5, -3.5)
    assert result == -6.0, "Should handle negative floats"

def test_zero_values():
    """Test adding zero values"""
    result = calculate(0, 5)
    assert result == 5, "Zero plus number should return number"
    result = calculate(0.0, 5.0)
    assert result == 5.0, "Zero float plus number should return number"