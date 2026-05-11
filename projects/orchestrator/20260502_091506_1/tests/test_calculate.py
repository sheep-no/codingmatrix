# tests/test_calculate.py
import pytest
from calculate import calculate

def test_add_integers():
    """Test adding two integers"""
    result = calculate(3, 5)
    assert result == 8, "Should return sum of two integers"

def test_add_floats():
    """Test adding two floating point numbers"""
    result = calculate(2.5, 3.5)
    assert result == 6.0, "Should return sum of two floats"

def test_add_integer_and_float():
    """Test adding an integer and a float"""
    result = calculate(4, 2.0)
    assert result == 6.0, "Should handle integer and float addition"

def test_add_strings():
    """Test adding two strings (should raise TypeError)"""
    with pytest.raises(TypeError):
        calculate("hello", "world")

def test_add_string_and_integer():
    """Test adding a string and an integer (should raise TypeError)"""
    with pytest.raises(TypeError):
        calculate("hello", 5)

def test_add_list_and_integer():
    """Test adding a list and an integer (should raise TypeError)"""
    with pytest.raises(TypeError):
        calculate([1, 2, 3], 5)

def test_add_none_values():
    """Test adding None values (should raise TypeError)"""
    with pytest.raises(TypeError):
        calculate(None, 5)
    with pytest.raises(TypeError):
        calculate(5, None)

def test_add_negative_numbers():
    """Test adding two negative integers"""
    result = calculate(-3, -5)
    assert result == -8, "Should handle negative number addition"

def test_add_zero():
    """Test adding zero to a number"""
    result = calculate(0, 5)
    assert result == 5, "Should handle zero addition"
    result = calculate(5, 0)
    assert result == 5, "Should handle zero addition"