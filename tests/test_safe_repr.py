import json
from pathlib import Path
from pprint import pformat

import pytest
from data_downloader.utils import safe_repr


def test_safe_repr_path():
    """Test if safe_repr function can correctly handle Path objects"""
    # Create a Path object
    path = Path("~/test/data.txt")

    # Test direct conversion
    result = safe_repr(path)
    assert isinstance(result, str)
    assert result == str(path)

    # Ensure the converted string can be serialized to JSON
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        pytest.fail("Converted Path object cannot be serialized to JSON")


def test_safe_repr_dict_with_path():
    """Test if safe_repr function can correctly handle dictionaries containing Path objects"""
    # Create a dictionary containing Path objects
    data = {
        "folder": Path("~/data"),
        "file": Path("~/data/test.txt"),
        "other": "string value",
        "number": 42,
    }

    # Test conversion
    result = safe_repr(data)
    assert isinstance(result, dict)
    assert isinstance(result["folder"], str)
    assert isinstance(result["file"], str)
    assert result["folder"] == str(data["folder"])
    assert result["file"] == str(data["file"])
    assert result["other"] == data["other"]
    assert result["number"] == data["number"]

    # Ensure the converted dictionary can be serialized to JSON
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        pytest.fail("Converted dictionary cannot be serialized to JSON")


def test_safe_repr_list_with_path():
    """Test if safe_repr function can correctly handle lists containing Path objects"""
    # Create a list containing Path objects
    data = [Path("~/file1.txt"), Path("~/file2.txt"), "string value", 42]

    # Test conversion
    result = safe_repr(data)
    assert isinstance(result, list)
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)
    assert result[0] == str(data[0])
    assert result[1] == str(data[1])
    assert result[2] == data[2]
    assert result[3] == data[3]

    # Ensure the converted list can be serialized to JSON
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        pytest.fail("Converted list cannot be serialized to JSON")


def test_safe_repr_nested_structure():
    """Test if safe_repr function can correctly handle nested structures"""
    # Create a nested structure
    data = {
        "paths": [Path("~/file1.txt"), Path("~/file2.txt")],
        "nested": {"path": Path("~/nested/file.txt"), "value": 100},
    }

    # Test conversion
    result = safe_repr(data)

    # Verify structure
    assert isinstance(result["paths"], list)
    assert isinstance(result["paths"][0], str)
    assert isinstance(result["paths"][1], str)
    assert isinstance(result["nested"], dict)
    assert isinstance(result["nested"]["path"], str)

    # Verify values
    assert result["paths"][0] == str(data["paths"][0])
    assert result["paths"][1] == str(data["paths"][1])
    assert result["nested"]["path"] == str(data["nested"]["path"])
    assert result["nested"]["value"] == data["nested"]["value"]

    # Ensure the converted structure can be serialized to JSON
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        pytest.fail("Converted nested structure cannot be serialized to JSON")


def test_pformat_with_path():
    """Test pformat with safe_repr combination"""
    # Create data containing Path objects
    data = {
        "folder": Path("~/data"),
        "files": [Path("~/data/file1.txt"), Path("~/data/file2.txt")],
    }

    # Use safe_repr and pformat for formatting
    formatted = pformat(safe_repr(data), indent=4)

    # Verify the formatted string doesn't contain Path objects
    assert "PosixPath" not in formatted
    assert "WindowsPath" not in formatted
    assert str(data["folder"]) in formatted
    assert str(data["files"][0]) in formatted
    assert str(data["files"][1]) in formatted


def test_safe_repr_custom_iterable():
    """Test if safe_repr function can correctly handle custom iterable objects"""

    # Create custom iterable object
    class CustomIterable:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

    # Custom iterable containing Path objects
    custom_iterable = CustomIterable([Path("~/custom1.txt"), Path("~/custom2.txt")])

    # Test conversion
    result = safe_repr(custom_iterable)

    # Verify results
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)
