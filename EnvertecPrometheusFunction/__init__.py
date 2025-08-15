import logging
import re
import requests
import azure.functions as func
import os

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Prometheus Envertec Function triggered.')

    # Username und Passwort aus Umgebungsvariablen holen
    username = os.environ.get("ENVERTEC_USERNAME")
    password = os.environ.get("ENVERTEC_PASSWORD")
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=500)

    # Step 1: Login to Envertec
    login_url = "https://www.envertecportal.com/apiaccount/login"
    login_payload = {
        "username": username,
        "pwd": password
    }
    session = requests.Session()

    login_resp = session.post(login_url, json=login_payload)
    if login_resp.status_code != 200:
        print("Login failed")
        return func.HttpResponse("Login failed", status_code=500)
    
    cookies = session.cookies.get_dict()
    if "ASP.NET_SessionId" not in cookies:
        print("Login failed: SessionId cookie missing")
        return func.HttpResponse("Login failed: SessionId cookie missing", status_code=500)
    print("Login successful")

    # Step 2: Get StationId
    overview_url = "https://www.envertecportal.com/terminal/systemoverview"
    overview_resp = session.post(overview_url)
    match = re.search(r"var\s+stationId\s+=\s+'(?P<stationId>\w+)';", overview_resp.text)
    if not match:
        print("StationId not found")
        return func.HttpResponse("StationId not found", status_code=500)
    station_id = match.group("stationId")
    print("StationId gefunden:", station_id)

    # Step 3: Get inverter data
    inverter_url = "https://www.envertecportal.com/ApiInverters/QueryTerminalReal"
    inverter_payload = {
        "page": 1,
        "perPage": 20,
        "orderBy": "GATEWAYSN",
        "whereCondition": f'{{"STATIONID":"{station_id}"}}'
    }
    inverter_resp = session.post(inverter_url, json=inverter_payload)
    if inverter_resp.status_code != 200:
        print("Inverter query failed")
        return func.HttpResponse("Inverter query failed", status_code=500)
    inverter_data = inverter_resp.json()

    # Step 4: Format as Prometheus metrics
    metrics = []
    # Typ-Kommentare für Prometheus
    metrics.append('# TYPE envertec_power_watt gauge')
    metrics.append('# TYPE envertec_dayenergy_kwh counter')
    metrics.append('# TYPE envertec_temperature_c gauge')

    query_results = inverter_data.get("Data", {}).get("QueryResults", [])
    for item in query_results:
        snalias = item.get("SNALIAS", "unknown")
        gatewayalias = item.get("GATEWAYALIAS", "unknown")
        power = item.get("POWER", 0)
        dayenergy = item.get("DAYENERGY", 0)
        temperature = item.get("TEMPERATURE", 0)

        metrics.append(f'envertec_power_watt{{snalias="{snalias}", gatewayalias="{gatewayalias}"}} {power}')
        metrics.append(f'envertec_dayenergy_kwh{{snalias="{snalias}", gatewayalias="{gatewayalias}"}} {dayenergy}')
        metrics.append(f'envertec_temperature_c{{snalias="{snalias}", gatewayalias="{gatewayalias}"}} {temperature}')


    metrics_text = "\n".join(metrics)
    print("Prometheus metrics generated:")
    print(metrics_text)
    return func.HttpResponse(metrics_text, mimetype="text/plain")
