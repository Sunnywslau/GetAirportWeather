import requests
from datetime import datetime

def get_weather_data(airport_code, airport_lookup):
    for entry in airport_lookup:
        if entry['airport'] == airport_code:
            location_code = entry['code']
            url = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_code}"
            response = requests.get(url)
            return response.json(), entry['UTC_to_LTC'], location_code  # Return location_code
    return None, None, None  # Update to return None for location_code

def get_taf(airport_code):
    url = f"https://aviationweather.gov/api/data/taf?ids={airport_code}&time=valid"
    response = requests.get(url)
    return response.text if response.text else f"No TAF found for {airport_code}"

def find_surrounding_weather_reports(weather_data, target_time):
    previous_reports = []
    nearest_report = None
    next_reports = []

    for report in weather_data['forecasts']:
        for detailed_report in report['detailed']['reports']:
            report_time = datetime.fromisoformat(detailed_report['localDate'] + 'T' + detailed_report['timeslot'])
            
            # Collect reports based on time
            if report_time < target_time:
                previous_reports.append(detailed_report)
            elif report_time >= target_time:
                if nearest_report is None:
                    nearest_report = detailed_report
                next_reports.append(detailed_report)

            # Limit to 5 reports total
            if len(next_reports) >= 5:
                break

        if len(next_reports) >= 5:
            break

    previous_reports = previous_reports[-5:]  # Last 5 previous reports
    next_reports = next_reports[:5]  # First 5 next reports

    return previous_reports, nearest_report, next_reports
