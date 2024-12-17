import json
import requests
from datetime import timedelta

def load_airport_codes(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def convert_utc_to_local(utc_time, offset):
    return utc_time + timedelta(hours=offset)

def convert_local_to_utc(local_time, offset):
    return local_time - timedelta(hours=offset)

def get_taf(airport_code):
    url = f"https://aviationweather.gov/api/data/taf?ids={airport_code}&time=valid"
    response = requests.get(url)
    return response.text if response.text else f"No TAF found for {airport_code}"