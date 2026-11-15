#!/usr/bin/env python3
"""
Create an interactive HTML visualization of fire weather data.

This script creates a standalone HTML file with:
- Interactive map showing the fire location
- Time series charts of weather parameters
- Highlighted fire day
- Summary statistics

Usage:
    python visualize_fire_weather.py --input data/single_fire_with_weather.parquet --output fire_weather_visualization.html
"""

import argparse
from pathlib import Path

import polars as pl

# Try to import visualization libraries
try:
    import folium
    from folium.plugins import FastMarkerCluster
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    print("Warning: folium not available, map will be static")

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("Warning: plotly not available, charts will be static")


def create_map_html(lat: float, lon: float, title: str = "Fire Location") -> str:
    """Create HTML for a map with the fire location."""
    if not FOLIUM_AVAILABLE:
        return f"""
        <div style="text-align: center; padding: 20px; border: 1px solid #ccc; margin: 20px 0;">
            <h3>{title}</h3>
            <p>Latitude: {lat:.4f}°, Longitude: {lon:.4f}°</p>
            <p>Map visualization requires folium library.</p>
        </div>
        """
    
    # Create folium map centered on Austria
    m = folium.Map(location=[47.5, 13.5], zoom_start=7)
    
    # Add fire location marker
    folium.Marker(
        location=[lat, lon],
        popup=f"Fire: {lat:.4f}, {lon:.4f}",
        icon=folium.Icon(color='red', icon='fire', prefix='fa')
    ).add_to(m)
    
    # Add Austria border (approximate polygon)
    austria_polygon = folium.GeoJson(
        {
            "type": "Polygon",
            "coordinates": [[
                [9.5, 49.0], [17.2, 49.0], [17.2, 46.4], [9.5, 46.4], [9.5, 49.0]
            ]]
        },
        style_function=lambda x: {'fillColor': '#00ff00', 'color': '#000000', 'fillOpacity': 0.1}
    )
    austria_polygon.add_to(m)
    
    # Save to temporary HTML file
    temp_map_file = Path("temp_map.html")
    m.save(temp_map_file)
    
    # Read the HTML content
    with open(temp_map_file, 'r') as f:
        map_html = f.read()
    
    # Clean up
    temp_map_file.unlink()
    
    # Extract just the map div (folium generates full HTML)
    # We'll wrap it in our own HTML
    return map_html


def create_charts_html(df: pl.DataFrame) -> str:
    """Create HTML for weather parameter charts."""
    if not PLOTLY_AVAILABLE:
        return """
        <div style="padding: 20px; border: 1px solid #ccc; margin: 20px 0;">
            <p>Interactive charts require plotly library.</p>
        </div>
        """
    
    # Convert polars to dicts then to pandas
    import pandas as pd
    data_dicts = df.to_dicts()
    pdf = pd.DataFrame(data_dicts)
    
    # Get fire day
    fire_day = pdf[pdf['fire_detection'] == True].iloc[0]['date']
    
    # Create subplots with secondary y-axis for first row
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=('Temperature & Humidity', 'Precipitation', 'Wind Speed & Direction'),
        vertical_spacing=0.1,
        specs=[[{"secondary_y": True}], [{}], [{}]]
    )
    
    # Temperature and Humidity
    fig.add_trace(
        go.Scatter(
            x=pdf['date'], y=pdf['t_2m_C'],
            name='Temperature (°C)',
            line=dict(color='red'),
            marker=dict(size=8)
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=pdf['date'], y=pdf['rh_2m_p'],
            name='Humidity (%)',
            line=dict(color='blue'),
            yaxis='y2'
        ),
        row=1, col=1,
        secondary_y=True
    )
    
    # Precipitation
    fig.add_trace(
        go.Bar(
            x=pdf['date'], y=pdf['precip_24h_mm'],
            name='Precipitation (mm)',
            marker=dict(color='cyan')
        ),
        row=2, col=1
    )
    
    # Wind Speed and Direction
    fig.add_trace(
        go.Scatter(
            x=pdf['date'], y=pdf['wind_speed_10m_ms'],
            name='Wind Speed (m/s)',
            line=dict(color='green'),
            marker=dict(size=8)
        ),
        row=3, col=1
    )
    
    # Update layout
    fig.update_xaxes(title_text="Date", row=3, col=1)
    fig.update_yaxes(title_text="°C", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="%", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="mm", row=2, col=1)
    fig.update_yaxes(title_text="m/s", row=3, col=1)
    
    # Add fire day marker
    for i, trace in enumerate(fig.data):
        if 'date' in pdf.columns:
            fire_idx = pdf[pdf['date'] == fire_day].index
            if len(fire_idx) > 0:
                fig.add_vline(
                    x=fire_day,
                    line_dash="dash", line_color="red",
                    annotation_text="Fire Day",
                    annotation_position="top"
                )
    
    # Save to temporary HTML
    temp_chart_file = Path("temp_chart.html")
    fig.write_html(temp_chart_file, include_plotlyjs='cdn')
    
    with open(temp_chart_file, 'r') as f:
        chart_html = f.read()
    
    temp_chart_file.unlink()
    
    return chart_html


def create_summary_html(df: pl.DataFrame) -> str:
    """Create HTML summary statistics table."""
    fire_df = df.filter(pl.col('fire_detection') == True)
    if len(fire_df) > 0:
        fire_row = fire_df.to_dicts()[0]
    else:
        fire_row = None
    
    summary = f"""
    <div style="padding: 20px; margin: 20px 0; background-color: #f5f5f5; border-radius: 5px;">
        <h2>Fire Event Summary</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background-color: #e0e0e0;">
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Parameter</th>
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Value</th>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><b>Fire Date</b></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{fire_row['date']}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><b>Location</b></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{fire_row['lat']:.4f}°N, {fire_row['lon']:.4f}°E</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><b>Max FRP</b></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{fire_row['fire_max_frp']:.1f} MW</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><b>Duration</b></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{fire_row['fire_duration_days']} day(s)</td>
            </tr>
        </table>
        
        <h3 style="margin-top: 20px;">Weather Statistics</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background-color: #e0e0e0;">
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Parameter</th>
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Min</th>
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Max</th>
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Avg</th>
                <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Fire Day</th>
            </tr>
    """
    
    # Add weather statistics
    weather_params = ['t_2m_C', 'rh_2m_p', 'precip_24h_mm', 'wind_speed_10m_ms', 'evapotranspiration_24h_mm']
    param_names = ['Temperature (°C)', 'Humidity (%)', 'Precipitation (mm)', 'Wind Speed (m/s)', 'Evapotranspiration (mm)']
    
    for param, name in zip(weather_params, param_names):
        if param in df.columns:
            min_val = df[param].min()
            max_val = df[param].max()
            avg_val = df[param].mean()
            fire_val = fire_row[param]
            
            def format_val(val):
                if val is None:
                    return 'N/A'
                try:
                    return f"{float(val):.1f}"
                except:
                    return 'N/A'
            
            min_str = format_val(min_val)
            max_str = format_val(max_val)
            avg_str = format_val(avg_val)
            fire_str = format_val(fire_val)
            
            summary += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;">{name}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{min_str}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{max_str}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{avg_str}</td>
                <td style="padding: 10px; border: 1px solid #ddd; background-color: #ffcccc;">{fire_str}</td>
            </tr>
            """
    
    summary += "</table></div>"
    
    return summary


def create_html_file(df: pl.DataFrame, output_path: Path) -> None:
    """Create a complete HTML file with all visualizations."""
    # Get fire location
    fire_df = df.filter(pl.col('fire_detection') == True)
    if len(fire_df) > 0:
        fire_row = fire_df.to_dicts()[0]
        fire_lat = float(fire_row['lat'])
        fire_lon = float(fire_row['lon'])
        fire_date = fire_row['date']
    else:
        # Use first row if no fire detection
        fire_row = df.to_dicts()[0]
        fire_lat = float(fire_row['lat'])
        fire_lon = float(fire_row['lon'])
        fire_date = fire_row['date']
    
    # Create components
    map_html = create_map_html(fire_lat, fire_lon, f"Fire Location: {fire_lat:.4f}, {fire_lon:.4f}")
    summary_html = create_summary_html(df)
    
    # Extract just the chart div from plotly HTML
    charts_html = create_charts_html(df)
    
    # Create complete HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fire Weather Data Visualization - {fire_date}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f0f0f0;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #d32f2f;
            text-align: center;
            border-bottom: 2px solid #d32f2f;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
        }}
        .section {{
            margin-bottom: 30px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background-color: white;
        }}
        .fire-day {{
            background-color: #ffebee;
            padding: 10px;
            border-left: 4px solid #d32f2f;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 Fire Weather Data Visualization</h1>
        <p style="text-align: center; color: #666;">
            Interactive analysis of weather conditions before, during, and after a wildfire event
        </p>
        
        {summary_html}
        
        <div class="section">
            <h2>🗺️ Fire Location Map</h2>
            <div style="height: 500px; width: 100%;">{map_html}</div>
        </div>
        
        <div class="section">
            <h2>📈 Weather Parameters Over Time</h2>
            {charts_html}
        </div>
        
        <div class="section fire-day">
            <h3>🔥 Fire Day Analysis</h3>
            <p><strong>Date:</strong> {fire_date}</p>
            <p><strong>Location:</strong> {fire_lat:.4f}°N, {fire_lon:.4f}°E</p>
            <p><strong>Max FRP:</strong> {fire_row['fire_max_frp']:.1f} MW</p>
            <p style="color: #d32f2f;">
                The red vertical line in the charts above marks the fire day.
            </p>
        </div>
        
        <div style="text-align: center; margin-top: 30px; padding: 20px; color: #666; font-size: 0.9em;">
            Data sources: NASA FIRMS (Fire Information for Resource Management System) & Meteomatics API
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"✅ HTML visualization saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Create interactive HTML visualization of fire weather data'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='data/single_fire_with_weather.parquet',
        help='Input parquet file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='fire_weather_visualization.html',
        help='Output HTML file'
    )
    
    args = parser.parse_args()
    
    # Load data
    df = pl.read_parquet(args.input)
    
    # Create HTML
    output_path = Path(args.output)
    create_html_file(df, output_path)
    
    # Check file size
    file_size = output_path.stat().st_size
    print(f"File size: {file_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
