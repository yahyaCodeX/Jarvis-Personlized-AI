"""Time, date and weather — things the voice model can't know on its own."""

from __future__ import annotations

import datetime

import requests

from config import load_profile
from .registry import tool

WEATHER_CITY = load_profile().get("weather_city") or "Jamshoro, Sindh"


def get_time() -> str:
    now = datetime.datetime.now()
    h = now.hour % 12 or 12
    period = "AM" if now.hour < 12 else "PM"
    return f"It's {h}:{now.minute:02d} {period}, sir."


def get_date() -> str:
    now = datetime.datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."


@tool("Returns the current local time and date on the user's PC.")
def get_time_and_date() -> str:
    return f"{get_time()} {get_date()}"


@tool("Gets the current weather for the user's home city (or another city if they name one).",
      params={"city": "Optional city name, e.g. 'Karachi'. Leave empty for the user's home city."})
def get_weather(city: str = "") -> str:
    city_name = (city or "").strip() or WEATHER_CITY
    try:
        query = city_name.replace(" ", "+").replace(",", "")
        url = f"https://wttr.in/{query}?format=%C,+%t,+feels+like+%f,+humidity+%h"
        r = requests.get(url, timeout=6, headers={"User-Agent": "curl/7.68.0"})
        if r.status_code == 200 and r.text.strip():
            text = (r.text.strip()
                    .replace("°C", " degrees Celsius")
                    .replace("°F", " degrees Fahrenheit")
                    .replace("°", " degrees"))
            place = city_name.split(",")[0].strip()
            return f"{place} right now: {text}, sir."
        return "Couldn't get the weather right now, sir."
    except requests.Timeout:
        return "Weather request timed out. Try again in a moment, sir."
    except Exception:
        return "Weather service is unreachable right now, sir."
