from flask import Flask, jsonify
import requests
import os
import json
import time

app = Flask(__name__)

API_KEY = os.environ.get('ECOBEE_API_KEY', '')
UNIT = os.environ.get('UNIT', 'F').upper()
TOKEN_FILE = '/data/tokens.json'

tokens = {}


def load_tokens():
    global tokens
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tokens = json.load(f)


def save_tokens():
    os.makedirs('/data', exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)


def fmt(f10):
    """Convert Ecobee's tenths-of-Fahrenheit to the configured unit."""
    f = f10 / 10
    val = (f - 32) * 5 / 9 if UNIT == 'C' else f
    return f"{val:.1f}"


def refresh_access_token():
    global tokens
    r = requests.post('https://api.ecobee.com/token', params={
        'grant_type': 'refresh_token',
        'refresh_token': tokens.get('refresh_token', ''),
        'client_id': API_KEY,
    })
    if r.ok:
        data = r.json()
        tokens['access_token'] = data['access_token']
        tokens['refresh_token'] = data['refresh_token']
        tokens['expires_at'] = time.time() + data.get('expires_in', 3600) - 60
        save_tokens()
        return True
    return False


def get_access_token():
    if not tokens.get('access_token'):
        return None
    if time.time() > tokens.get('expires_at', 0):
        if not refresh_access_token():
            return None
    return tokens['access_token']


@app.route('/health')
def health():
    authorized = bool(tokens.get('access_token'))
    expires_in = max(0, int(tokens.get('expires_at', 0) - time.time()))
    return jsonify({
        'status': 'ok',
        'authorized': authorized,
        'unit': UNIT,
        'token_expires_in_seconds': expires_in if authorized else None,
    })


@app.route('/pin')
def get_pin():
    if not API_KEY:
        return jsonify({'error': 'ECOBEE_API_KEY is not set'}), 500
    r = requests.get('https://api.ecobee.com/authorize', params={
        'response_type': 'ecobeePin',
        'client_id': API_KEY,
        'scope': 'smartRead',
    })
    if not r.ok:
        return jsonify({'error': r.text}), 400
    data = r.json()
    tokens['auth_code'] = data['code']
    save_tokens()
    return jsonify({
        'pin': data['ecobeePin'],
        'expires_in_minutes': data.get('expires_in', 9),
        'next_step': 'Go to ecobee.com > My Apps > Add Application, enter the PIN above, then GET /authorize',
    })


@app.route('/authorize')
def authorize():
    code = tokens.get('auth_code', '')
    if not code:
        return jsonify({'error': 'No auth code — call /pin first'}), 400
    r = requests.post('https://api.ecobee.com/token', params={
        'grant_type': 'ecobeePin',
        'code': code,
        'client_id': API_KEY,
    })
    if not r.ok:
        return jsonify({'error': r.text}), 400
    data = r.json()
    tokens['access_token'] = data['access_token']
    tokens['refresh_token'] = data['refresh_token']
    tokens['expires_at'] = time.time() + data.get('expires_in', 3600) - 60
    tokens.pop('auth_code', None)
    save_tokens()
    return jsonify({'status': 'authorized'})


@app.route('/thermostat')
def thermostat():
    token = get_access_token()
    if not token:
        return jsonify({'error': 'Not authorized — visit /pin to set up'}), 401

    selection = json.dumps({
        "selection": {
            "selectionType": "registered",
            "selectionMatch": "",
            "includeSensors": True,
            "includeRuntime": True,
            "includeSettings": True,
            "includeWeather": True,
            "includeEquipmentStatus": True,
        }
    })

    def fetch(t):
        return requests.get(
            'https://api.ecobee.com/1/thermostat',
            params={'json': selection},
            headers={'Authorization': f'Bearer {t}'},
        )

    r = fetch(token)
    if r.status_code == 401:
        if refresh_access_token():
            r = fetch(tokens['access_token'])
        else:
            return jsonify({'error': 'Token refresh failed — re-run /pin + /authorize'}), 401

    if not r.ok:
        return jsonify({'error': r.text}), r.status_code

    thermostats = r.json().get('thermostatList', [])
    if not thermostats:
        return jsonify({'error': 'No thermostats found on this account'}), 404

    t = thermostats[0]
    runtime = t['runtime']
    settings = t['settings']
    equip = runtime.get('equipmentStatus', '')

    if any(x in equip for x in ['heatPump', 'auxHeat', 'heatStage']):
        state = 'Heating'
    elif any(x in equip for x in ['compCool', 'coolStage']):
        state = 'Cooling'
    elif 'fan' in equip.lower():
        state = 'Fan only'
    else:
        state = 'Idle'

    outdoor_temp = ''
    forecasts = t.get('weather', {}).get('forecasts', [])
    if forecasts:
        outdoor_temp = fmt(forecasts[0].get('temperature', 0))

    return jsonify({
        'name': t['name'],
        'temperature': fmt(runtime['actualTemperature']),
        'humidity': str(runtime.get('actualHumidity', 0)),
        'heat_setpoint': fmt(runtime['desiredHeat']),
        'cool_setpoint': fmt(runtime['desiredCool']),
        'hvac_mode': settings.get('hvacMode', 'off').capitalize(),
        'hvac_state': state,
        'outdoor_temp': outdoor_temp,
        'unit': UNIT,
    })


if __name__ == '__main__':
    load_tokens()
    app.run(host='0.0.0.0', port=5050)
