"""Tests for the Meteomatics API client."""

from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

# Ensure we can import from the package
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moonpies.meteomatics import get_weather


# Load environment variables from meteo-api.env
# The meteomatics module should handle this, but let's ensure it's available
env_path = Path(__file__).resolve().parents[2] / "meteo-api.env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)


@pytest.fixture
def valid_credentials():
    """Ensure credentials are available for testing."""
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")
    
    if not username or not password:
        pytest.skip("Meteomatics credentials not available")
    
    return username, password


def test_get_weather_with_valid_data(valid_credentials):
    """Test that get_weather returns data for a valid location and time."""
    # Use Graz, Austria coordinates
    latitude = 47.0707
    longitude = 15.4395
    valid_time = datetime.now(timezone.utc)
    
    result = get_weather(latitude, longitude, valid_time)
    
    # Check that we got a response
    assert result is not None
    assert isinstance(result, dict)
    
    # Check that the response contains the expected data
    # The Meteomatics API returns data in a nested structure
    # The exact structure depends on the API version
    print(f"API response: {result}")
    
    # At minimum, we should have some data
    assert len(result) > 0


def test_get_weather_with_missing_credentials(monkeypatch):
    """Test that get_weather raises ValueError when credentials are missing."""
    # Remove credentials from environment
    monkeypatch.delenv("METEOMATICS_USERNAME", raising=False)
    monkeypatch.delenv("METEOMATICS_PASSWORD", raising=False)
    
    latitude = 47.0707
    longitude = 15.4395
    valid_time = datetime.now(timezone.utc)
    
    with pytest.raises(ValueError, match="METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set"):
        get_weather(latitude, longitude, valid_time)


def test_import_from_package(valid_credentials):
    """Test that get_weather can be imported from the moonpies package."""
    from moonpies import get_weather as get_weather_from_package
    
    assert get_weather_from_package is get_weather
    
    # Also test it works
    latitude = 47.0707
    longitude = 15.4395
    valid_time = datetime.now(timezone.utc)
    
    result = get_weather_from_package(latitude, longitude, valid_time)
    assert result is not None


if __name__ == "__main__":
    # Run a simple test without pytest
    print("Running simple Meteomatics API test...")
    
    # Load env file
    env_path = Path(__file__).resolve().parents[2] / "meteo-api.env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
    
    try:
        from moonpies.meteomatics import get_weather
        
        # Test with Graz coordinates
        result = get_weather(
            latitude=47.0707,
            longitude=15.4395,
            valid_time=datetime.now(timezone.utc)
        )
        
        print("✓ Successfully fetched weather data:")
        print(f"  Response type: {type(result)}")
        print(f"  Response keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        print("\n✓ All tests passed!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
