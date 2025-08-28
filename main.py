import streamlit as st
from weather import get_weather_data, find_surrounding_weather_reports
from taf import display_taf_info
from utils import load_airport_codes, convert_utc_to_local, convert_local_to_utc, get_taf
from datetime import datetime, timedelta, timezone
import re
import pandas as pd
import matplotlib.pyplot as plt
import json
import os
import math

def calculate_wind_components(wind_direction, wind_speed, runway_heading):
    """
    Calculate crosswind and headwind components.
    
    Args:
        wind_direction: True wind direction in degrees (0-359)
        wind_speed: Wind speed in knots
        runway_heading: Runway true heading in degrees
        
    Returns:
        tuple: (crosswind, headwind) both in knots
        - crosswind: positive = right crosswind, negative = left crosswind
        - headwind: positive = headwind, negative = tailwind
    """
    # Convert to radians
    wind_rad = math.radians(wind_direction)
    runway_rad = math.radians(runway_heading)
    
    # Calculate the angle between wind and runway
    angle_diff = wind_rad - runway_rad
    
    # Calculate components
    headwind = wind_speed * math.cos(angle_diff)
    crosswind = wind_speed * math.sin(angle_diff)
    
    return round(crosswind, 1), round(headwind, 1)

def format_wind_component(value, component_type):
    """Format wind component for display with red highlighting for dangerous values."""
    if component_type == 'crosswind':
        if abs(value) < 0.1:
            return "0.0C"
        else:
            formatted = f"{abs(value):.1f}C"
            # Highlight crosswind > 30kt in red
            if abs(value) > 30:
                return f'<span style="color: red; font-weight: bold;">{formatted}</span>'
            else:
                return formatted
    else:  # headwind/tailwind
        if abs(value) < 0.1:
            return "0.0H"
        elif value > 0:
            return f"{value:.1f}H"  # Headwind with 1 decimal
        else:
            formatted = f"{abs(value):.1f}T"
            # Highlight tailwind >= 10kt in red
            if abs(value) >= 10:
                return f'<span style="color: red; font-weight: bold;">{formatted}</span>'
            else:
                return formatted

def display_preferential_runway_section(airport_code, utc_input):
    """Display preferential runway information for the given airport code."""
    runway_file = os.path.join(os.path.dirname(__file__), 'runways.json')
    
    # Check if runways.json exists
    if not os.path.exists(runway_file):
        return  # Silently skip if file doesn't exist
    
    try:
        # Load runway data
        with open(runway_file, 'r', encoding='utf-8') as f:
            runway_data = json.load(f)
        
        # Check if airport code exists in runway data
        code = airport_code.upper()
        if code not in runway_data:
            return  # Silently skip if airport not found
        
        # Display the section
        st.markdown("---")
        st.markdown(f"## Preferential Runway for {code}")
        
        # Wind component input
        st.markdown("#### Wind Component Analysis (Optional)")
        col1, col2 = st.columns([2, 2])
        with col1:
            # Create a unique key based on current airport code and time to force reset
            wind_key = f"wind_component_input_{airport_code}_{utc_input}"
            wind_input = st.text_input(
                "Enter Wind (DDDSS format)",
                placeholder="e.g., 27015 (270° at 15kt)",
                help="Enter 5-digit format: first 3 digits = true wind direction (000-359), last 2 digits = wind speed in knots",
                key=wind_key
            )
        
        wind_direction = None
        wind_speed = None
        
        # Parse wind input
        if wind_input and len(wind_input) == 5 and wind_input.isdigit():
            try:
                wind_direction = int(wind_input[:3])
                wind_speed = int(wind_input[3:])  # Fixed: should be [3:] not [2:]
                if 0 <= wind_direction <= 359 and 0 <= wind_speed <= 99:
                    with col2:
                        st.success(f"Wind: {wind_direction:03d}°/{wind_speed:02d}kt")
                else:
                    st.warning("Invalid wind values. Direction: 000-359°, Speed: 00-99kt")
                    wind_direction = wind_speed = None
            except ValueError:
                st.warning("Invalid wind format. Use DDDSS format (e.g., 27015)")
                wind_direction = wind_speed = None
        elif wind_input and wind_input.strip():
            st.warning("Invalid format. Use 5-digit DDDSS format (e.g., 27015 for 270° at 15kt)")
        
        airport_runways = runway_data[code]
        
        # Get magnetic variation for true heading calculation
        magnetic_variation = airport_runways.get('magnetic_variation', 0)
        
        # Check if ANY runway (departure or arrival) has notes to ensure consistent rendering
        dep = airport_runways.get('departure', [])
        arr = airport_runways.get('arrival', [])
        all_runways = dep + arr
        force_html_rendering = any(runway.get('Note', '').strip() for runway in all_runways)
        
        # Display Departure and Arrival information side by side
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Departure")
            if dep:
                display_runway_table(dep, "departure", magnetic_variation, force_html_rendering, wind_direction, wind_speed)
            else:
                st.info("No departure runway information available.")
        
        with col2:
            st.markdown("### Arrival")
            if arr:
                display_runway_table(arr, "arrival", magnetic_variation, force_html_rendering, wind_direction, wind_speed)
            else:
                st.info("No arrival runway information available.")
            
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
        # Silently handle errors - don't show runway section if there's an issue
        pass

def display_runway_table(runway_list, operation_type, magnetic_variation=0, force_html_rendering=False, wind_direction=None, wind_speed=None):
    """Helper function to display runway table with hover notes functionality and wind components."""
    # Sort by preferential order (smallest to largest)
    sorted_runways = sorted(runway_list, key=lambda x: x.get('preferential', 999))
    
    # Check if any runways have notes OR if we're forcing HTML rendering for consistency
    has_notes = any(runway.get('Note', '').strip() for runway in sorted_runways)
    use_html_rendering = has_notes or force_html_rendering
    
    # Determine if we have wind data for additional columns
    has_wind_data = wind_direction is not None and wind_speed is not None
    
    if use_html_rendering:
        # For runways with notes, use HTML with tooltips
        st.markdown("""
        <style>
        .runway-table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-family: 'Source Sans Pro', sans-serif;
            font-size: 16px;
        }
        .runway-table th {
            background-color: #f0f2f6;
            color: #262730;
            font-weight: bold;
            padding: 12px 15px;
            text-align: left;
            border: 1px solid #e6e9ef;
            font-size: 16px;
        }
        .runway-table td {
            padding: 10px 15px;
            border: 1px solid #e6e9ef;
            background-color: #ffffff;
            font-size: 16px;
            vertical-align: middle;
        }
        .runway-table tr:hover {
            background-color: #f8f9fa;
        }
        .runway-note {
            position: relative;
            cursor: help;
            color: #1f77b4;
            font-weight: bold;
        }
        .runway-note:hover::after {
            content: attr(data-note);
            position: absolute;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            white-space: nowrap;
            z-index: 1000;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .runway-note:hover::before {
            content: '';
            position: absolute;
            bottom: 115%;
            left: 50%;
            transform: translateX(-50%);
            border: 5px solid transparent;
            border-top-color: #333;
            z-index: 1000;
        }
        /* Ensure Streamlit dataframes have consistent font size */
        .stDataFrame {
            font-size: 16px !important;
        }
        .stDataFrame table {
            font-size: 16px !important;
        }
        .stDataFrame tbody tr td {
            font-size: 16px !important;
            vertical-align: middle !important;
        }
        .stDataFrame thead tr th {
            font-size: 16px !important;
        }
        /* Additional targeting for dataframe cells */
        div[data-testid="stDataFrame"] table {
            font-size: 16px !important;
        }
        div[data-testid="stDataFrame"] table td {
            font-size: 16px !important;
            vertical-align: middle !important;
        }
        div[data-testid="stDataFrame"] table th {
            font-size: 16px !important;
        }
        /* Target the actual table content */
        .stDataFrame div div table {
            font-size: 16px !important;
        }
        .stDataFrame div div table td {
            font-size: 16px !important;
            vertical-align: middle !important;
        }
        .stDataFrame div div table th {
            font-size: 16px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Build HTML table with hover tooltips
        html_rows = ['<table class="runway-table">']
        if has_wind_data:
            html_rows.append('<thead><tr><th>Runway</th><th>Direction</th><th>Cross/Head Wind</th></tr></thead>')
        else:
            html_rows.append('<thead><tr><th>Runway</th><th>Direction</th></tr></thead>')
        html_rows.append('<tbody>')
        
        for runway in sorted_runways:
            runway_name = runway.get('runway', '')
            magnetic_direction = runway.get('magnetic_direction', '')
            note = runway.get('Note', '').strip()
            
            if magnetic_direction:
                true_direction = (magnetic_direction + magnetic_variation) % 360
                direction_display = f"{int(magnetic_direction):03d}°M / {int(true_direction):03d}°T"
            else:
                direction_display = ""
            
            if note:
                runway_cell = f'<span class="runway-note" data-note="{note}">{runway_name} ℹ️</span>'
            else:
                runway_cell = runway_name
            
            # Calculate wind components if wind data is available
            wind_cell = ""
            if has_wind_data and magnetic_direction:
                true_direction = (magnetic_direction + magnetic_variation) % 360
                crosswind, headwind = calculate_wind_components(wind_direction, wind_speed, true_direction)
                crosswind_str = format_wind_component(crosswind, 'crosswind')
                headwind_str = format_wind_component(headwind, 'headwind')
                wind_cell = f'<td style="font-family: monospace; text-align: center; font-size: 16px; vertical-align: middle;">{crosswind_str} / {headwind_str}</td>'
                html_rows.append(f'<tr><td style="vertical-align: middle;">{runway_cell}</td><td style="font-family: monospace; vertical-align: middle; font-size: 16px;">{direction_display}</td>{wind_cell}</tr>')
            else:
                if has_wind_data:
                    html_rows.append(f'<tr><td style="vertical-align: middle;">{runway_cell}</td><td style="font-family: monospace; vertical-align: middle; font-size: 16px;">{direction_display}</td><td style="font-size: 16px; text-align: center; vertical-align: middle;">-</td></tr>')
                else:
                    html_rows.append(f'<tr><td style="vertical-align: middle;">{runway_cell}</td><td style="font-family: monospace; vertical-align: middle; font-size: 16px;">{direction_display}</td></tr>')
        
        html_rows.append('</tbody></table>')
        st.markdown(''.join(html_rows), unsafe_allow_html=True)
        
    else:
        # For runways without notes, use clean st.dataframe
        display_data = []
        for runway in sorted_runways:
            runway_name = runway.get('runway', '')
            magnetic_direction = runway.get('magnetic_direction', '')
            
            if magnetic_direction:
                true_direction = (magnetic_direction + magnetic_variation) % 360
                direction_display = f"{int(magnetic_direction):03d}°M / {int(true_direction):03d}°T"
            else:
                direction_display = ""
            
            row_data = {
                'Runway': runway_name,
                'Direction': direction_display,
            }
            
            # Add wind components if wind data is available
            if has_wind_data and magnetic_direction:
                crosswind, headwind = calculate_wind_components(wind_direction, wind_speed, true_direction)
                crosswind_str = format_wind_component(crosswind, 'crosswind')
                headwind_str = format_wind_component(headwind, 'headwind')
                row_data['Cross/Head Wind'] = f"{crosswind_str} / {headwind_str}"
            elif has_wind_data:
                row_data['Cross/Head Wind'] = "-"
            
            display_data.append(row_data)
        
        df = pd.DataFrame(display_data)
        
        # Build column configuration dynamically
        column_config = {
            "Runway": st.column_config.TextColumn(
                "Runway",
                help="Runway designation",
                width="medium",
            ),
            "Direction": st.column_config.TextColumn(
                "Direction", 
                help="Magnetic direction (M) and True direction (T)",
                width="large",
            ),
        }
        
        # Add wind column configuration if wind data is present
        if has_wind_data:
            column_config["Cross/Head Wind"] = st.column_config.TextColumn(
                "Cross/Head Wind",
                help="Crosswind (L/R) and Headwind (H/T) components in knots",
                width="medium",
            )
        
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
            height=35 * len(display_data) + 35
        )

def main():
    # Configure page to use wide layout
    st.set_page_config(
        page_title="Weather Dashboard",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.markdown("# Weather Dashboard")
    
    # Disable browser autocomplete with custom CSS
    st.markdown("""
    <style>
    .stTextInput input {
        autocomplete: off;
    }
    /* Set maximum width to prevent excessive stretching on very wide screens */
    .main .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 1400px;
        margin: 0 auto;
    }
    /* Scale up text elements for wide screen layout */
    .main .block-container p {
        font-size: 16px !important;
    }
    .main .block-container .stMarkdown {
        font-size: 16px !important;
    }
    .main .block-container .stMarkdown p {
        font-size: 16px !important;
    }
    /* Scale up info boxes */
    .main .block-container .stAlert {
        font-size: 16px !important;
    }
    /* Scale up warning/error messages */
    .main .block-container .stWarning {
        font-size: 16px !important;
    }
    .main .block-container .stError {
        font-size: 16px !important;
    }
    /* Scale up success messages */
    .main .block-container .stSuccess {
        font-size: 16px !important;
    }
    /* Ensure links are also properly sized */
    .main .block-container a {
        font-size: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state for form persistence
    if 'show_weather_data' not in st.session_state:
        st.session_state.show_weather_data = False
    if 'current_airport_code' not in st.session_state:
        st.session_state.current_airport_code = ""
    if 'current_utc_input' not in st.session_state:
        st.session_state.current_utc_input = ""
    if 'clear_counter' not in st.session_state:
        st.session_state.clear_counter = 0
    
    # Sidebar for user input
    st.sidebar.header("Input Parameters")
    airport_lookup = load_airport_codes('./airport_codes.json')  # Update path as necessary
    
    # Input for airport code
    airport_code = st.sidebar.text_input(
        "Enter Airport Code", 
        key=f"airport_code_input_{st.session_state.clear_counter}",
        help="Enter ICAO airport code (e.g., VHHH, CYYZ)"
    ).upper()
    
    utc_input = st.sidebar.text_input(
        "Enter time in UTC (HHMM)", 
        key=f"utc_time_input_{st.session_state.clear_counter}",
        help="Enter time in HHMM format (e.g., 1530 for 3:30 PM)"
    )
    
    # Update tracking values when inputs change (for dynamic key generation)
    if (airport_code != st.session_state.current_airport_code or 
        utc_input != st.session_state.current_utc_input):
        # Update session state to track current values
        st.session_state.current_airport_code = airport_code
        st.session_state.current_utc_input = utc_input
    
    if st.sidebar.button("Get Weather Data"):
        # Validate inputs first
        if not airport_code.strip():
            st.sidebar.error("Please enter an airport code")
        elif not utc_input.strip():
            st.sidebar.error("Please enter a time in UTC")
        else:
            # Enable weather data display (values already stored above)
            st.session_state.show_weather_data = True
    
    # Add a clear button
    if st.sidebar.button("Clear"):
        # Increment clear counter before clearing (to get new widget keys)
        current_counter = st.session_state.get('clear_counter', 0) + 1
        
        # Clear all session state completely
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        
        # Reinitialize essential session state
        st.session_state.show_weather_data = False
        st.session_state.current_airport_code = ""
        st.session_state.current_utc_input = ""
        st.session_state.clear_counter = current_counter
        st.rerun()
    
    # Show weather data if button was clicked (using session state)
    if st.session_state.show_weather_data:
        airport_code = st.session_state.current_airport_code
        utc_input = st.session_state.current_utc_input
        
        if utc_input and airport_code:
            # Validate input format for HHMM
            if not re.match(r'^\d{4}$', utc_input):
                st.warning("Please enter the time in the format HHMM (e.g., 1530 for 3:30 PM).")
                return
            
            try:
                current_utc_time = datetime.utcnow()
                input_time = datetime.strptime(utc_input, "%H%M")
                
                # Create the full UTC datetime
                target_time = datetime(current_utc_time.year, current_utc_time.month, current_utc_time.day,
                                       input_time.hour, input_time.minute)

                if target_time < current_utc_time:
                    target_time += timedelta(days=1)  # Input time has already passed today

                weather_data, utc_offset, location_code = get_weather_data(airport_code, airport_lookup)  # Capture location_code

                if weather_data:
                    local_time = convert_utc_to_local(target_time, utc_offset)
                    location_name = weather_data['location']['name']
                    
                    # Handle different formats for last update time
                    last_update = weather_data['lastUpdated']
                    
                    try:
                        # Parse last_update and set UTC timezone if necessary
                        if last_update.endswith('Z'):
                            last_update_time_utc = datetime.fromisoformat(last_update[:-1])  # Remove 'Z' for parsing
                        else:
                            last_update_time_utc = datetime.fromisoformat(last_update)  # Directly parse with offset
                            last_update_time_utc = last_update_time_utc.astimezone(timezone.utc)
                        
                        # Display header information (enhanced for wide screen)
                        st.markdown(f"""
                        <div style="font-size: 18px; margin: 10px 0;">
                            <strong>Airport Code:</strong> {airport_code} | <strong>Location:</strong> {location_name}<br>
                            <strong>Time (UTC):</strong> {target_time.strftime('%Y-%m-%d %H:%M')}Z 
                            <strong>Local:</strong> {local_time.strftime('%Y-%m-%d %H:%M')}L
                        </div>
                        """, unsafe_allow_html=True)

                        # Prepare data for plotting
                        previous_reports, nearest_report, next_reports = find_surrounding_weather_reports(weather_data, local_time)
                        all_reports = previous_reports + [nearest_report] + next_reports
                        times, pressures, temperatures = [], [], []

                        for report in all_reports:
                            report_time = datetime.fromisoformat(report['localDate'] + 'T' + report['timeslot'])
                            times.append(report_time.strftime('%Y-%m-%d %H:%M'))
                            pressures.append(report['pressure'])
                            temperatures.append(report['temperatureC'])

                        # Create a DataFrame for filtering
                        df = pd.DataFrame({
                            'Time': times,
                            'Pressure (hPa)': pressures,
                            'Temperature (°C)': temperatures
                        })

                        # Conservative logic for both text and plot: if input time matches, use that value; else, use closest before/after and take min pressure, max temperature
                        input_time_str = local_time.strftime('%Y-%m-%d %H:%M')
                        if input_time_str in df['Time'].values:
                            idx = df[df['Time'] == input_time_str].index[0]
                            pressure_value = df.at[idx, 'Pressure (hPa)']
                            temperature_value = df.at[idx, 'Temperature (°C)']
                            
                            # Display temperature/pressure and BBC link in a compact table format
                            st.markdown(f"""
                            <table style="width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 16px;">
                                <tr>
                                    <td style="background-color: #f0f2f6; padding: 15px; border-radius: 5px 0 0 5px; border: 1px solid #e6e9ef; width: 70%;">
                                        <strong>Temperature:</strong> <span style='color: blue; font-weight: bold; font-size: 20px;'>{temperature_value} °C</span> | 
                                        <strong>Pressure:</strong> <span style='color: blue; font-weight: bold; font-size: 20px;'>{pressure_value} hPa</span>
                                        <br><span style="font-size: 14px; color: #666;">(Last update: {last_update_time_utc.strftime('%Y-%m-%d %H:%M')} UTC)</span>
                                    </td>
                                    <td style="background-color: #e8f4fd; padding: 15px; border-radius: 0 5px 5px 0; border: 1px solid #e6e9ef; text-align: center; width: 30%;">
                                        <a href="https://www.bbc.com/weather/{location_code}" target="_blank" 
                                           style="font-size: 14px; font-weight: bold; text-decoration: none; color: #1f77b4;">
                                           📊 BBC Weather
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            """, unsafe_allow_html=True)
                            crit_indices = [idx]
                        else:
                            # Find closest before/after indices
                            filtered_times = pd.to_datetime(df['Time'])
                            input_time_local = local_time.replace(second=0, microsecond=0)
                            prev_idx = filtered_times[filtered_times <= input_time_local].idxmax() if any(filtered_times <= input_time_local) else None
                            next_idx = filtered_times[filtered_times > input_time_local].idxmin() if any(filtered_times > input_time_local) else None
                            crit_indices = []
                            if prev_idx is not None:
                                crit_indices.append(prev_idx)
                            if next_idx is not None and next_idx != prev_idx:
                                crit_indices.append(next_idx)
                            if crit_indices:
                                # Conservative: min pressure, max temperature
                                pressure_value = df.loc[crit_indices]['Pressure (hPa)'].min()
                                temperature_value = df.loc[crit_indices]['Temperature (°C)'].max()
                                
                                # Display temperature/pressure and BBC link in a compact table format
                                st.markdown(f"""
                                <table style="width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 16px;">
                                    <tr>
                                        <td style="background-color: #f0f2f6; padding: 15px; border-radius: 5px 0 0 5px; border: 1px solid #e6e9ef; width: 70%;">
                                            <strong>Temperature:</strong> <span style='color: blue; font-weight: bold; font-size: 20px;'>{temperature_value} °C</span> | 
                                            <strong>Pressure:</strong> <span style='color: blue; font-weight: bold; font-size: 20px;'>{pressure_value} hPa</span>
                                            <br><span style="font-size: 14px; color: #666;">(Last update: {last_update_time_utc.strftime('%Y-%m-%d %H:%M')} UTC)</span>
                                        </td>
                                        <td style="background-color: #e8f4fd; padding: 15px; border-radius: 0 5px 5px 0; border: 1px solid #e6e9ef; text-align: center; width: 30%;">
                                            <a href="https://www.bbc.com/weather/{location_code}" target="_blank" 
                                               style="font-size: 14px; font-weight: bold; text-decoration: none; color: #1f77b4;">
                                               📊 BBC Weather
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                                """, unsafe_allow_html=True)
                            else:
                                earliest_time = df['Time'].min() if not df.empty else None
                                if earliest_time:
                                    earliest_time_utc = convert_local_to_utc(datetime.strptime(earliest_time, '%Y-%m-%d %H:%M'), utc_offset)
                                    st.warning(f"The selected time is outside the available data range. Data is available since {earliest_time_utc.strftime('%Y-%m-%d %H:%M')} UTC.")
                                else:
                                    st.write("Not enough data to determine nearest values.")
                                return

                        # Fetch and display TAF in a more compact way
                        taf_info = get_taf(airport_code)
                        
                        # Create a three-column layout for better screen utilization
                        # Give TAF more width by using 2:1:1 ratio instead of 1:1:1
                        info_col1, info_col2, info_col3 = st.columns([2, 1, 1])
                        
                        # TAF in first column (now wider)
                        with info_col1:
                            display_taf_info(taf_info)

                        # Create time range for ±3 hours
                        time_range_start = local_time - timedelta(hours=3)
                        time_range_end = local_time + timedelta(hours=3)

                        # Filter data for the ±3 hour range
                        filtered_df = df[(pd.to_datetime(df['Time']) >= time_range_start) & 
                                         (pd.to_datetime(df['Time']) <= time_range_end)]

                        # Enhanced: Dotted line for input time, critical points logic
                        filtered_times = pd.to_datetime(filtered_df['Time'])
                        input_time_local = local_time.replace(second=0, microsecond=0)
                        # Use the same crit_indices as above for plotting
                        crit_temp = crit_temp_idx = crit_press = crit_press_idx = None
                        if crit_indices:
                            temps = filtered_df.loc[crit_indices]['Temperature (°C)']
                            presses = filtered_df.loc[crit_indices]['Pressure (hPa)']
                            crit_temp = temps.max()
                            crit_temp_idx = temps.idxmax()
                            crit_press = presses.min()
                            crit_press_idx = presses.idxmin()

                        # Plotting
                        # Dotted line for input time: plot at local time corresponding to user's UTC input
                        input_time_local_str = local_time.strftime('%Y-%m-%d %H:%M')
                        # Always show the line if local_time is within the filtered data's time range
                        show_input_line = False
                        if not filtered_times.empty:
                            min_time = filtered_times.min()
                            max_time = filtered_times.max()
                            show_input_line = min_time <= local_time <= max_time

                        # Prepare datetime-based x-axis for plotting
                        filtered_df_dt = filtered_df.copy()
                        filtered_df_dt['Time_dt'] = pd.to_datetime(filtered_df_dt['Time'])

                        # Pressure Plot in second column
                        with info_col2:
                            st.markdown("### Pressure Over Time")
                            fig, ax1 = plt.subplots(figsize=(3.5, 2.2))
                            ax1.plot(filtered_df_dt['Time_dt'], filtered_df_dt['Pressure (hPa)'], marker='o', label='Pressure (hPa)', color='blue')
                            # Dotted line for input time (local time, only if in range)
                            if show_input_line:
                                ax1.axvline(x=local_time, color='red', linestyle=':', linewidth=2, label='Input Time')
                            # Highlight min pressure
                            if crit_press_idx is not None:
                                ax1.scatter(filtered_df_dt.loc[crit_press_idx]['Time_dt'], filtered_df_dt.loc[crit_press_idx]['Pressure (hPa)'], color='green', marker='v', s=120, label='Min Pressure')
                            ax1.set_xlabel('Time', fontsize=8)
                            ax1.set_ylabel('Pressure (hPa)', color='blue', fontsize=8)
                            ax1.tick_params(axis='y', labelcolor='blue', labelsize=7)
                            ax1.tick_params(axis='x', labelsize=7, rotation=45)
                            plt.xticks(rotation=45)
                            ax1.set_xticks(filtered_df_dt['Time_dt'])
                            ax1.set_xticklabels([t.strftime('%H:%M') for t in filtered_df_dt['Time_dt']], rotation=45, ha='right', fontsize=7)
                            # Disable scientific notation for y-axis
                            ax1.ticklabel_format(style='plain', axis='y')
                            # Dynamically set y-axis limits based on data range with margin
                            y_min = filtered_df_dt['Pressure (hPa)'].min()
                            y_max = filtered_df_dt['Pressure (hPa)'].max()
                            y_margin = max(1, int((y_max - y_min) * 0.1))  # 10% margin or at least 1 hPa
                            ax1.set_ylim(y_min - y_margin, y_max + y_margin)
                            # Format y-axis as integer using FixedLocator
                            import matplotlib.ticker as mticker
                            y_labels = ax1.get_yticks()
                            ax1.yaxis.set_major_locator(mticker.FixedLocator(y_labels))
                            ax1.set_yticklabels([f'{int(y):d}' for y in y_labels], fontsize=7)
                            handles, labels = ax1.get_legend_handles_labels()
                            by_label = dict(zip(labels, handles))
                            ax1.legend(by_label.values(), by_label.keys(), fontsize=7)
                            plt.tight_layout()
                            st.pyplot(fig, use_container_width=False)

                        # Temperature Plot in third column
                        with info_col3:
                            st.markdown("### Temperature Over Time")
                            fig, ax2 = plt.subplots(figsize=(3.5, 2.2))
                            ax2.plot(filtered_df_dt['Time_dt'], filtered_df_dt['Temperature (°C)'], marker='o', label='Temperature (°C)', color='orange')
                            # Dotted line for input time (local time, only if in range)
                            if show_input_line:
                                ax2.axvline(x=local_time, color='red', linestyle=':', linewidth=2, label='Input Time')
                            # Highlight max temperature
                            if crit_temp_idx is not None:
                                ax2.scatter(filtered_df_dt.loc[crit_temp_idx]['Time_dt'], filtered_df_dt.loc[crit_temp_idx]['Temperature (°C)'], color='purple', marker='^', s=120, label='Max Temperature')
                            ax2.set_xlabel('Time', fontsize=8)
                            ax2.set_ylabel('Temperature (°C)', color='orange', fontsize=8)
                            ax2.tick_params(axis='y', labelcolor='orange', labelsize=7)
                            ax2.tick_params(axis='x', labelsize=7, rotation=45)
                            plt.xticks(rotation=45)
                            ax2.set_xticks(filtered_df_dt['Time_dt'])
                            ax2.set_xticklabels([t.strftime('%H:%M') for t in filtered_df_dt['Time_dt']], rotation=45, ha='right', fontsize=7)
                            # Dynamically set y-axis limits based on data range with margin
                            t_min = filtered_df_dt['Temperature (°C)'].min()
                            t_max = filtered_df_dt['Temperature (°C)'].max()
                            t_margin = max(0.5, (t_max - t_min) * 0.1)  # 10% margin or at least 0.5°C
                            ax2.set_ylim(t_min - t_margin, t_max + t_margin)
                            ax2.tick_params(axis='y', labelsize=7)
                            handles, labels = ax2.get_legend_handles_labels()
                            by_label = dict(zip(labels, handles))
                            ax2.legend(by_label.values(), by_label.keys(), fontsize=7)
                            plt.tight_layout()
                            st.pyplot(fig, use_container_width=False)

                        # Display Preferential Runway section
                        display_preferential_runway_section(airport_code, utc_input)

                    except ValueError as e:
                        st.error(f"Error parsing last update time: {e}")
                else:
                    st.error("Invalid airport code or no weather data available.")
            except ValueError as e:
                st.error(f"Invalid time format. Please use HHMM. Error: {e}")
        else:
            st.warning("Please enter both airport code and UTC time, then click 'Get Weather Data'.")

if __name__ == "__main__":
    main()
