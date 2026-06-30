# ecobee-proxy

A lightweight OAuth proxy that lets you add a live Ecobee thermostat widget to [Luna](https://github.com/luna-page/luna) or [Glance](https://github.com/glanceapp/glance).

Luna and Glance's `custom-api` widget can call any HTTP endpoint, but Ecobee uses OAuth 2.0 — access tokens expire every hour and can't be refreshed inside a dashboard config. This proxy sits between your dashboard and the Ecobee API, handles token refresh transparently, and exposes a single simple endpoint your widget calls.

![Widget preview showing indoor temp, humidity, HVAC state, setpoints, and outdoor temp]()

## What it shows

- Indoor temperature and humidity
- Thermostat name
- HVAC state (Heating / Cooling / Fan only / Idle)
- HVAC mode (Heat / Cool / Auto / Off)
- Heat and cool setpoints
- Outdoor temperature (from Ecobee's built-in weather)

Supports **Fahrenheit** and **Celsius** via an env var.

---

## Setup

### 1. Get an Ecobee API key

1. Sign in at [developer.ecobee.com](https://developer.ecobee.com)
2. Click **Create New Application**
3. Give it any name, set Authorization Method to **ecobee PIN**
4. Copy the **API Key**

### 2. Start the proxy

```bash
cp .env.example .env
# Edit .env and paste your API key
docker compose up -d
```

### 3. Authorize (one-time)

```bash
# Get a PIN
curl http://localhost:5050/pin
```

Go to **ecobee.com → My Apps → Add Application** and enter the PIN shown. Then:

```bash
# Exchange the PIN for tokens
curl http://localhost:5050/authorize
```

That's it. Tokens are saved to `./data/tokens.json` and refresh automatically — you never need to do this again.

---

## Add the widget

Copy the contents of [`widget.yml`](widget.yml) into your Luna or Glance config.

**Luna** — paste into any page's `widgets:` list:
```yaml
- $include: /path/to/widget.yml
```

Or inline the widget directly into your page config.

**Glance** — same `custom-api` widget type, same syntax.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ECOBEE_API_KEY` | *(required)* | API key from developer.ecobee.com |
| `UNIT` | `F` | Temperature unit: `F` or `C` |

---

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Container status, auth state, token expiry |
| `GET /pin` | Start OAuth — returns a PIN to enter on ecobee.com |
| `GET /authorize` | Complete OAuth after entering the PIN |
| `GET /thermostat` | Live thermostat data (used by the widget) |

---

## Why a proxy?

Ecobee's API requires OAuth 2.0. Access tokens expire every hour, and the only way to get a new one is to POST a refresh token to Ecobee's auth server — something a dashboard widget can't do on its own. The proxy handles that loop silently on every request, so the widget just sees a plain JSON endpoint.

The same pattern works for any OAuth-gated smart home API (Nest, Honeywell, etc.).
