"""Example usage of the Meteomatics API client."""

from datetime import datetime, timezone
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "meteo-api.env")

# Import from the moonpies package
from moonpies import get_weather


def main():
    """Fetch and display weather data for a location."""
    # Example: Graz, Austria
    latitude = 47.0707
    longitude = 15.4395
    
    # Get current weather
    current_time = datetime.now(timezone.utc)
    
    print(f"Fetching weather for Graz, Austria ({latitude}, {longitude})...")
    print(f"Current UTC time: {current_time.isoformat()}")
    
    try:
        weather_data = get_weather(latitude, longitude, current_time)
        
        print("\nWeather data received:")
        print(f"  Version: {weather_data.get('version')}")
        print(f"  User: {weather_data.get('user')}")
        print(f"  Generated: {weather_data.get('dateGenerated')}")
        print(f"  Status: {weather_data.get('status')}")
        
        # Extract the actual weather data
        if 'data' in weather_data:
            data = weather_data['data']
            print(f"\n  Data points: {len(data)}")
            for point in data:
                print(f"    - {point}")
        
    except Exception as e:
        print(f"\nError fetching weather data: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
