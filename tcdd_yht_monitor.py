#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


BASE_URL = "https://web-api-prod-ytp.tcddtasimacilik.gov.tr"
SEARCH_TRIP_URL = f"{BASE_URL}/tms/train/train-availability?environment=dev&userId=1"
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_TIMEZONE_OFFSET_HOURS = 3
DEFAULT_MIN_TIME = "12:16"
DEFAULT_NTFY_TOPIC_URL = "https://ntfy.sh/tcdddeneme"
DEFAULT_API_TIMEOUT_SECONDS = 30
DEFAULT_NTFY_TIMEOUT_SECONDS = 15
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 5


@dataclass(frozen=True)
class Station:
    id: int
    name: str
    city_name: str


DEFAULT_STATIONS = [
    Station(48, "ISTANBUL(PENDIK)", "Istanbul-Pendik"),
    Station(98, "ANKARA GAR", "Ankara"),
    Station(1306, "ERYAMAN YHT", "Ankara-Eryaman"),
    Station(93, "ESKISEHIR", "Eskisehir"),
    Station(20, "GEBZE","Gebze")
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check TCDD YHT availability and parse available seats."
    )
    parser.add_argument("--list-stations", action="store_true", help="List known stations and exit.")
    parser.add_argument("--departure", help="Departure city name, for example Ankara.")
    parser.add_argument("--arrival", help="Arrival city name, for example Istanbul-Pendik.")
    parser.add_argument(
        "--date",
        required=False,
        help="Travel date in DD-MM or DD-MM-YYYY format.",
    )
    parser.add_argument(
        "--min-time",
        default=DEFAULT_MIN_TIME,
        help=f"Earliest departure time, default {DEFAULT_MIN_TIME}.",
    )
    parser.add_argument("--max-time", default="23:59", help="Latest departure time, default 23:59.")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Polling interval in seconds, default {DEFAULT_INTERVAL_SECONDS}.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check instead of polling continuously.",
    )
    parser.add_argument(
        "--timezone-offset",
        type=int,
        default=DEFAULT_TIMEZONE_OFFSET_HOURS,
        help="Hour offset to apply when converting departure epochs, default +3.",
    )
    parser.add_argument(
        "--ntfy-topic",
        default=DEFAULT_NTFY_TOPIC_URL,
        help=f"ntfy topic URL for notifications, default {DEFAULT_NTFY_TOPIC_URL}.",
    )
    return parser.parse_args()


def load_properties() -> dict[str, str]:
    properties: dict[str, str] = {}
    candidate_paths = [
        Path("application_properties"),
        Path("application.properties"),
    ]
    for path in candidate_paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            properties[key.strip()] = value.strip()
    return properties


def get_bearer_token(properties: dict[str, str]) -> str:
    token = os.getenv("TCDD_BEARER_TOKEN") or properties.get("app.bearer-token", "")
    if not token:
        raise RuntimeError(
            "Bearer token not found. Set TCDD_BEARER_TOKEN or add app.bearer-token to application.properties."
        )
    return token


def find_station(query: str) -> Station:
    normalized = query.strip().casefold()
    for station in DEFAULT_STATIONS:
        if station.city_name.casefold() == normalized or station.name.casefold() == normalized:
            return station
    available = ", ".join(station.city_name for station in DEFAULT_STATIONS)
    raise ValueError(f"Unknown station '{query}'. Available stations: {available}")


def format_api_departure_date(raw_date: str) -> str:
    parts = raw_date.split("-")
    if len(parts) == 2:
        day, month = (int(part) for part in parts)
        year = datetime.now().year
    elif len(parts) == 3:
        day, month, year = (int(part) for part in parts)
    else:
        raise ValueError("Date must be in DD-MM or DD-MM-YYYY format.")

    travel_date = datetime(year, month, day)
    request_date = travel_date - timedelta(days=1)
    return f"{request_date.day}-{request_date.month}-{request_date.year} 21:00:00"


def build_headers(bearer_token: str) -> dict[str, str]:
    return {
        "Host": "web-api-prod-ytp.tcddtasimacilik.gov.tr",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr",
        "Authorization": f"Bearer {bearer_token}",
        "unit-id": "3895",
        "Content-Type": "application/json",
        "Origin": "https://ebilet.tcddtasimacilik.gov.tr",
        "DNT": "1",
        "Connection": "close",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


def build_payload(date_value: str, departure: Station, arrival: Station) -> dict[str, Any]:
    return {
        "searchRoutes": [
            {
                "departureStationId": departure.id,
                "departureStationName": departure.name,
                "arrivalStationId": arrival.id,
                "arrivalStationName": arrival.name,
                "departureDate": format_api_departure_date(date_value),
            }
        ],
        "passengerTypeCounts": [{"id": 0, "count": 1}],
        "searchReservation": False,
    }


def fetch_availability(
    bearer_token: str,
    date_value: str,
    departure: Station,
    arrival: Station,
) -> dict[str, Any]:
    payload = build_payload(date_value, departure, arrival)
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, DEFAULT_RETRY_ATTEMPTS + 1):
        req = request.Request(
            SEARCH_TRIP_URL,
            data=body,
            headers=build_headers(bearer_token),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=DEFAULT_API_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError:
            raise
        except (error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            last_error = exc
            if attempt == DEFAULT_RETRY_ATTEMPTS or not is_transient_network_error(exc):
                raise
            time.sleep(DEFAULT_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error


def send_ntfy_notification(topic_url: str, message: str) -> None:
    body = message.encode("utf-8")
    req = request.Request(topic_url, data=body, method="POST")
    with request.urlopen(req, timeout=DEFAULT_NTFY_TIMEOUT_SECONDS):
        return


def is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, ssl.SSLError)):
        return True
    if isinstance(exc, error.URLError):
        return is_transient_network_error(exc.reason)
    return "timed out" in str(exc).casefold()


def format_network_error(exc: BaseException) -> str:
    if isinstance(exc, error.URLError) and exc.reason:
        return format_network_error(exc.reason)
    return str(exc)


def epoch_to_time(epoch_millis: int, timezone_offset: int) -> str:
    tz = timezone(timedelta(hours=timezone_offset))
    local_time = datetime.fromtimestamp(epoch_millis / 1000, tz=tz)
    return local_time.strftime("%H:%M")


def parse_time_value(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def time_in_range(value: str, min_time: str, max_time: str) -> bool:
    current = parse_time_value(value)
    minimum = parse_time_value(min_time)
    maximum = parse_time_value(max_time)
    return minimum <= current <= maximum


def parse_availability(data: dict[str, Any], min_time: str, max_time: str, timezone_offset: int) -> list[str]:
    results: list[str] = []
    train_legs = data.get("trainLegs") or []
    if not train_legs:
        return results

    train_availabilities = train_legs[0].get("trainAvailabilities") or []
    for availability_group in train_availabilities:
        trains = availability_group.get("trains") or []
        if not trains:
            continue

        train = trains[0]
        if train.get("type") != "YHT":
            continue

        available_seats = 0
        for car in train.get("cars") or []:
            availabilities = car.get("availabilities") or []
            if not availabilities:
                continue
            cabin_class = availabilities[0].get("cabinClass")
            if not cabin_class:
                continue
            cabin_name = str(cabin_class.get("name", "")).casefold()
            if "tekerlekli" in cabin_name:
                continue
            available_seats += int(availabilities[0].get("availability", 0))

        segments = train.get("segments") or []
        if not segments:
            continue

        departure_time = epoch_to_time(int(segments[0]["departureTime"]), timezone_offset)
        if available_seats < 1:
            continue

        if time_in_range(departure_time, min_time, max_time):
            results.append(f"ALERT: {departure_time} Av. Seats: {available_seats}")
        else:
            results.append(f"INFO: {departure_time} Av. Seats: {available_seats}")

    return results


def print_station_list() -> None:
    for station in DEFAULT_STATIONS:
        print(f"{station.city_name:18} id={station.id} api_name={station.name}")


def run_check(args: argparse.Namespace, token: str) -> list[str]:
    if not args.departure or not args.arrival or not args.date:
        raise ValueError("--departure, --arrival and --date are required unless --list-stations is used.")

    departure = find_station(args.departure)
    arrival = find_station(args.arrival)

    response = fetch_availability(token, args.date, departure, arrival)
    logs = parse_availability(response, args.min_time, args.max_time, args.timezone_offset)

    timestamp = datetime.now().strftime("%H:%M:%S")
    if not logs:
        print(f"[{timestamp}] No available seats found.")
        return []

    for line in logs:
        print(f"[{timestamp}] {line}")
    return logs


def main() -> int:
    args = parse_args()
    if args.list_stations:
        print_station_list()
        return 0

    properties = load_properties()
    token = get_bearer_token(properties)
    notified_alerts: set[str] = set()

    startup_message = (
        f"TCDD monitor started. Route: {args.departure} -> {args.arrival}, "
        f"date: {args.date}, time window: {args.min_time}-{args.max_time}."
    )
    try:
        send_ntfy_notification(args.ntfy_topic, startup_message)
    except Exception as exc:  # noqa: BLE001
        print(f"Startup notification failed: {exc}", file=sys.stderr)

    while True:
        try:
            logs = run_check(args, token)
            for line in logs:
                if not line.startswith("ALERT:"):
                    continue
                if line in notified_alerts:
                    continue
                found_message = (
                    f"Seat found for {args.departure} -> {args.arrival} on {args.date}. {line}"
                )
                try:
                    send_ntfy_notification(args.ntfy_topic, found_message)
                except Exception as exc:  # noqa: BLE001
                    print(f"Notification failed: {exc}", file=sys.stderr)
                    continue
                notified_alerts.add(line)
        except ValueError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP error {exc.code}: {body}", file=sys.stderr)
            return 1
        except (error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            print(
                f"Network error: {format_network_error(exc)}. Retrying in {args.interval} seconds...",
                file=sys.stderr,
            )
            if args.once:
                return 1
        except Exception as exc:  # noqa: BLE001
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
