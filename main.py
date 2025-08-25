import streamlit as st
from weather import get_weather_data, find_surrounding_weather_reports
from taf import display_taf_info
from utils import load_airport_codes, convert_utc_to_local, convert_local_to_utc, get_taf
from datetime import datetime, timedelta, timezone
import re
import pandas as pd
import matplotlib.pyplot as plt

def main():
    st.title("Weather Dashboard")
    
    # Sidebar for user input
    st.sidebar.header("Input Parameters")
    airport_lookup = load_airport_codes('./airport_codes.json')  # Update path as necessary
    
    # Input for airport code
    airport_code = st.sidebar.text_input("Enter Airport Code", "").upper()  # Convert to uppercase
    utc_input = st.sidebar.text_input("Enter time in UTC (HHMM)", "")
    
    if st.sidebar.button("Get Weather Data"):
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
                        
                        # Display header information
                        st.write(f"**Airport Code:** {airport_code} | **Location:** {location_name} <br>"
                                 f"**Time (UTC):** {target_time.strftime('%Y-%m-%d %H:%M')}Z "
                                 f"**Local:** {local_time.strftime('%Y-%m-%d %H:%M')}L", unsafe_allow_html=True)

                        
                        
                        # Fetch and display TAF
                        taf_info = get_taf(airport_code)
                        display_taf_info(taf_info)

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

                        # Check if input time exists in the data
                        input_time_str = local_time.strftime('%Y-%m-%d %H:%M')
                        if input_time_str in df['Time'].values:
                            idx = df[df['Time'] == input_time_str].index[0]
                            pressure_value = df.at[idx, 'Pressure (hPa)']
                            temperature_value = df.at[idx, 'Temperature (°C)']
                            # Format pressure and temperature in bold blue and display last update
                            st.write(f"**Temperature:** <span style='color: blue; font-weight: bold;'>{temperature_value} °C</span> | "
                                     f"**Pressure:** <span style='color: blue; font-weight: bold;'>{pressure_value} hPa</span> "
                                     f"(Last update: {last_update_time_utc.strftime('%Y-%m-%d %H:%M')} UTC)", unsafe_allow_html=True)
                        else:
                            # If not found, check the available data range
                            if previous_reports and next_reports:
                                highest_pressure = max(previous_reports[-1]['pressure'], next_reports[0]['pressure'])
                                highest_temperature = max(previous_reports[-1]['temperatureC'], next_reports[0]['temperatureC'])
                                st.write(f"**Nearest Temperature:** <span style='color: blue; font-weight: bold;'>{highest_temperature} °C</span> | "
                                         f"**Nearest Pressure:** <span style='color: blue; font-weight: bold;'>{highest_pressure} hPa</span> "
                                         f"(Last update: {last_update_time_utc.strftime('%Y-%m-%d %H:%M')} UTC)", unsafe_allow_html=True)
                            else:
                                earliest_time = df['Time'].min() if not df.empty else None
                                if earliest_time:
                                    # Convert earliest_time from local to UTC
                                    earliest_time_utc = convert_local_to_utc(datetime.strptime(earliest_time, '%Y-%m-%d %H:%M'), utc_offset)
                                    st.warning(f"The selected time is outside the available data range. Data is available since {earliest_time_utc.strftime('%Y-%m-%d %H:%M')} UTC.")
                                else:
                                    st.write("Not enough data to determine nearest values.")
                                return
                        # Add WX Details link after temperature and pressure
                        st.markdown(f"[Details in BBC Weather](https://www.bbc.com/weather/{location_code})", unsafe_allow_html=True)

                        # Create time range for ±3 hours
                        time_range_start = local_time - timedelta(hours=3)
                        time_range_end = local_time + timedelta(hours=3)

                        # Filter data for the ±3 hour range
                        filtered_df = df[(pd.to_datetime(df['Time']) >= time_range_start) & 
                                         (pd.to_datetime(df['Time']) <= time_range_end)]


                        # --- Enhanced Plotting: Highlight input time and critical points ---
                        col1, col2 = st.columns([1, 1])

                        # --- Enhanced: Dotted line for input time, critical points logic ---
                        filtered_times = pd.to_datetime(filtered_df['Time'])
                        input_time_local = local_time.replace(second=0, microsecond=0)
                        # Find the closest available data point before and after the input time
                        prev_idx = filtered_times[filtered_times <= input_time_local].idxmax() if any(filtered_times <= input_time_local) else None
                        next_idx = filtered_times[filtered_times > input_time_local].idxmin() if any(filtered_times > input_time_local) else None
                        crit_indices = []
                        if prev_idx is not None:
                            crit_indices.append(prev_idx)
                        if next_idx is not None and next_idx != prev_idx:
                            crit_indices.append(next_idx)
                        # Find max temp and min pressure among crit_indices
                        crit_temp = None
                        crit_temp_idx = None
                        crit_press = None
                        crit_press_idx = None
                        if crit_indices:
                            temps = filtered_df.loc[crit_indices]['Temperature (°C)']
                            presses = filtered_df.loc[crit_indices]['Pressure (hPa)']
                            crit_temp = temps.max()
                            crit_temp_idx = temps.idxmax()
                            crit_press = presses.min()
                            crit_press_idx = presses.idxmin()

                        # --- Plotting ---
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


                        # --- Pressure Plot ---
                        with col1:
                            fig, ax1 = plt.subplots(figsize=(6, 3))
                            ax1.plot(filtered_df_dt['Time_dt'], filtered_df_dt['Pressure (hPa)'], marker='o', label='Pressure (hPa)', color='blue')
                            # Dotted line for input time (local time, only if in range)
                            if show_input_line:
                                ax1.axvline(x=local_time, color='red', linestyle=':', linewidth=2, label='Input Time')
                            # Highlight min pressure
                            if crit_press_idx is not None:
                                ax1.scatter(filtered_df_dt.loc[crit_press_idx]['Time_dt'], filtered_df_dt.loc[crit_press_idx]['Pressure (hPa)'], color='green', marker='v', s=120, label='Min Pressure')
                            ax1.set_xlabel('Time')
                            ax1.set_ylabel('Pressure (hPa)', color='blue')
                            ax1.tick_params(axis='y', labelcolor='blue')
                            plt.xticks(rotation=45)
                            ax1.set_xticks(filtered_df_dt['Time_dt'])
                            ax1.set_xticklabels(filtered_df_dt['Time'], rotation=45, ha='right')
                            plt.title('Pressure Over Time')
                            handles, labels = ax1.get_legend_handles_labels()
                            by_label = dict(zip(labels, handles))
                            ax1.legend(by_label.values(), by_label.keys())
                            st.pyplot(fig)

                        # --- Temperature Plot ---
                        with col2:
                            fig, ax2 = plt.subplots(figsize=(6, 3))
                            ax2.plot(filtered_df_dt['Time_dt'], filtered_df_dt['Temperature (°C)'], marker='o', label='Temperature (°C)', color='orange')
                            # Dotted line for input time (local time, only if in range)
                            if show_input_line:
                                ax2.axvline(x=local_time, color='red', linestyle=':', linewidth=2, label='Input Time')
                            # Highlight max temperature
                            if crit_temp_idx is not None:
                                ax2.scatter(filtered_df_dt.loc[crit_temp_idx]['Time_dt'], filtered_df_dt.loc[crit_temp_idx]['Temperature (°C)'], color='purple', marker='^', s=120, label='Max Temperature')
                            ax2.set_xlabel('Time')
                            ax2.set_ylabel('Temperature (°C)', color='orange')
                            ax2.tick_params(axis='y', labelcolor='orange')
                            plt.xticks(rotation=45)
                            ax2.set_xticks(filtered_df_dt['Time_dt'])
                            ax2.set_xticklabels(filtered_df_dt['Time'], rotation=45, ha='right')
                            plt.title('Temperature Over Time')
                            handles, labels = ax2.get_legend_handles_labels()
                            by_label = dict(zip(labels, handles))
                            ax2.legend(by_label.values(), by_label.keys())
                            st.pyplot(fig)

                    except ValueError as e:
                        st.error(f"Error parsing last update time: {e}")
                else:
                    st.error("Invalid airport code or no weather data available.")
            except ValueError as e:
                st.error(f"Invalid time format. Please use HHMM. Error: {e}")

if __name__ == "__main__":
    main()
