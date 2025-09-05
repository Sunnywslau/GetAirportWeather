import re
import streamlit as st

def display_taf_info(taf_text):
    st.subheader("TAF Information:")
    
    # Replace newlines with HTML line breaks to preserve formatting
    taf_text = taf_text.replace('\n', '<br>')
    
    # Define regex patterns for visibility, cloud ceiling, unmeasured visibility, and freezing conditions
    visibility_pattern = r'(?<=\s)(\d{4})(?=\s|<br>|$)'  # 4-digit visibility, allows end of string
    cloud_ceiling_pattern = r'(?<!\S)\b(BKN|OVC)(\d{3})\b(?=\s|<br>|$)'  # BKN/OVC with 3-digit height
    unmeasured_visibility_pattern = r'(?<!\S)(VV///|VV\d{3}?)(?=\s|<br>|$)'  # Match VV/// or VV followed by 3 digits
    freezing_conditions_pattern = r'(?<!\S)([-+]?FZ(?:DZ|RA))(?=\s|<br>|$)'  # Freezing conditions
    snow_pattern = r'(?<!\S)(SN)(?=\s|<br>|$)'  # Match SN indicating snow

    # Function to highlight visibility
    def highlight_visibility(match):
        visibility = match.group(0)
        visibility_meters = int(visibility)
        return f"<span style='color: red; font-weight: bold;'>{visibility}</span>" if visibility_meters < 3000 else visibility

    # Function to highlight cloud ceiling
    def highlight_cloud_ceiling(match):
        cloud_type = match.group(1)  # BKN or OVC
        height = int(match.group(2)) * 100  # Convert 3-digit height to feet
        return f"<span style='color: pink; font-weight: bold;'>{cloud_type}{match.group(2)}</span>" if height < 1000 else match.group(0)

        
    def highlight_unmeasured_visibility(match):
        return f"<span style='color: purple; font-weight: bold;'>{match.group(0)}</span>"
        

    # Function to highlight freezing conditions
    def highlight_freezing_conditions(match):
        return f"<span style='color: blue; font-weight: bold;'>{match.group(0)}</span>"
        
    # Function to highlight snow conditions
    def highlight_snow(match):
        return f"<span style='color: green; background-color: blue; font-weight: bold;'>{match.group(0)}</span>"

    # Highlight relevant sections of the TAF
    highlighted_taf = re.sub(visibility_pattern, highlight_visibility, taf_text)
    highlighted_taf = re.sub(cloud_ceiling_pattern, highlight_cloud_ceiling, highlighted_taf)
    highlighted_taf = re.sub(unmeasured_visibility_pattern, highlight_unmeasured_visibility, highlighted_taf)
    highlighted_taf = re.sub(freezing_conditions_pattern, highlight_freezing_conditions, highlighted_taf)
    highlighted_taf = re.sub(snow_pattern, highlight_snow, highlighted_taf)  # Add snow highlighting

    # Display the highlighted TAF with larger font size for wide screen
    st.markdown(f"""
    <div style="font-size: 18px; line-height: 1.2; padding: 8px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #007acc; font-family: 'Courier New', monospace; margin: 5px 0;">
        {highlighted_taf}
    </div>
    """, unsafe_allow_html=True)

