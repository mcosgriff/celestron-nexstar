# Space Weather Integration - NOAA SWPC

## Overview

NOAA's Space Weather Prediction Center (SWPC) provides comprehensive space weather data through their `services.swpc.noaa.gov` API. This document outlines available data sources and potential integration options.

## Current Integration

The codebase already uses NOAA SWPC for:

- **Kp Index (Geomagnetic Activity)**: Used for aurora visibility predictions
  - Endpoint: `https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json`
  - Location: `src/celestron_nexstar/api/events/aurora.py`

## Available NOAA SWPC Data Sources

Based on the [Space Weather Enthusiasts Dashboard](https://www.swpc.noaa.gov/communities/space-weather-enthusiasts-dashboard) and [Space Weather Advisory Outlook](https://www.spaceweather.gov/products/space-weather-advisory-outlook), the following data is available:

### 1. Space Weather Scales (NOAA Scales)

- **R-Scale (Radio Blackouts)**: R1-R5 scale for solar flare impacts
- **S-Scale (Solar Radiation Storms)**: S1-S5 scale for radiation events
- **G-Scale (Geomagnetic Storms)**: G1-G5 scale for geomagnetic activity
- **Endpoint**: Likely available via JSON API (needs verification)

### 2. Solar Activity

- **GOES Solar Ultraviolet Imager (SUVI)**: Solar images
- **Solar Visible Light**: Sunspot images
- **LASCO C3**: Coronagraph images
- **Solar Wind Speed**: Real-time solar wind data
- **Solar Wind Magnetic Fields**: Bt and Bz values
- **10.7cm Radio Flux**: Solar activity indicator
- **Endpoints**:
  - `https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json`
  - `https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json`
  - `https://services.swpc.noaa.gov/json/goes/goes-xrs-report.json` (X-ray flux)

### 3. Geospace/Aurora

- **Aurora Forecast (Ovation)**: 30-minute aurora predictions
- **3-Day Satellite Environment**: Space weather impacts on satellites
- **Endpoints**:
  - `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json`
  - `https://services.swpc.noaa.gov/products/geospace/geospace-1-day.json`

### 4. Ionosphere

- **Total Electron Content (TEC)**: Ionospheric conditions
- **D Region Absorption**: Radio wave absorption
- **Endpoints**:
  - `https://services.swpc.noaa.gov/json/glotec/glotec_latest.json`

### 5. Space Weather Advisory Outlook

- **Weekly Reports**: Issued every Monday
- **7-Day Forecast**: Space weather conditions and impacts
- **Format**: Text/HTML (may need parsing)
- **URL**: `https://www.spaceweather.gov/products/space-weather-advisory-outlook`

## Potential Integration Ideas

### Option 1: Space Weather Status Command

Create a new command: `nexstar space-weather` or `nexstar swx`

**Display:**

- Current NOAA scales (R, S, G)
- Solar wind speed and magnetic field
- 10.7cm radio flux
- Current Kp index (already available)
- Aurora forecast summary
- Active alerts/warnings

**Use Cases:**

- Quick check before observing
- Understand why aurora might be visible
- Monitor solar activity that could affect observations

### Option 2: Enhanced Aurora Integration

Add more context to existing aurora commands:

- Show current G-scale (geomagnetic storm level)
- Display solar wind conditions
- Link to space weather alerts

### Option 3: Space Weather Alerts

- Monitor for G3+ geomagnetic storms (enhanced aurora)
- Alert on R3+ radio blackouts (may affect GPS/communications)
- Track solar flares that could impact observations

### Option 4: Observation Conditions Integration

Add space weather factors to `nexstar telescope tonight`:

- Solar activity affecting sky conditions
- Geomagnetic activity warnings
- Radio interference warnings

## Implementation Approach

### Step 1: Explore Available Endpoints

Test available JSON endpoints to understand data structure:

```python
# Example endpoints to test:
endpoints = [
    "https://services.swpc.noaa.gov/json/goes/goes-xrs-report.json",
    "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
    "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
    "https://services.swpc.noaa.gov/products/geospace/geospace-1-day.json",
]
```

### Step 2: Create Data Models

Define dataclasses for space weather data:

```python
@dataclass
class SpaceWeatherConditions:
    """Current space weather conditions."""
    r_scale: int | None  # Radio blackout scale (R1-R5)
    s_scale: int | None  # Solar radiation scale (S1-S5)
    g_scale: int | None  # Geomagnetic scale (G1-G5)
    kp_index: float | None
    solar_wind_speed: float | None  # km/s
    solar_wind_bt: float | None  # nT
    solar_wind_bz: float | None  # nT
    radio_flux_107: float | None  # sfu
    alerts: list[str]
```

### Step 3: Create API Module

Similar to `aurora.py`, create `space_weather.py`:

- Fetch data from multiple endpoints
- Cache responses (30 min - 1 hour)
- Parse and normalize data
- Handle errors gracefully

### Step 4: CLI Command

Create `nexstar space-weather` command:

- Display current conditions in a table
- Show NOAA scales with color coding
- Link to detailed forecasts
- Integrate with existing aurora commands

## Example Display

```text
Space Weather Conditions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━_endpoints.json`
- `https://services.swpc.noaa.gov/products/geospace/geospace-1-day.json`

## References

- [NOAA SWPC Space Weather Enthusiasts Dashboard](https://www.swpc.noaa.gov/communities/space-weather-enthusiasts-dashboard)
- [Space Weather Advisory Outlook](https://www.spaceweather.gov/products/space-weather-advisory-outlook)
- [NOAA SWPC Services API](https://services.swpc.noaa.gov)
- [NOAA Space Weather Scales](https://www.swpc.noaa.gov/noaa-scales-explanation)
