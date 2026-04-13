# TCDD YHT Python Monitor

This project is a Python script that checks TCDD YHT ticket availability and sends notifications through `ntfy`.

## Requirements

- Python 3
- Internet access
- A valid TCDD bearer token

## Files

- `tcdd_yht_monitor.py`: main script
- `application.properties`: optional config file for the bearer token
- `tcdd_yht_monitor_esp8266.ino`: ESP8266 sketch version

## Bearer Token

The script reads the token from one of these places:

1. `TCDD_BEARER_TOKEN` environment variable
2. `application_properties`


Example:

```properties
app.bearer-token=YOUR_TOKEN_HERE
```

## Usage

List stations:

```bash
python3 tcdd_yht_monitor.py --list-stations
```

Run one check:

```bash
python3 tcdd_yht_monitor.py --departure Ankara --arrival Gebze --date 25-12-2026 --once
```

Run in a loop:

```bash
python3 tcdd_yht_monitor.py --departure Ankara --arrival Gebze --date 25-12-2026
```

Use a custom ntfy topic:

```bash
python3 tcdd_yht_monitor.py --departure Ankara --arrival Gebze --date 25-12-2026 --ntfy-topic https://ntfy.sh/mytopic
```

## Default Behavior

- Checks every 5 seconds
- Looks for trains after `12:16`
- Sends a startup notification to `https://ntfy.sh/mytopic`
- Sends a notification when seats are found

## Notes

- Station names must match the values from `--list-stations`
- The script filters for `YHT` trains
- Wheelchair-only seat classes are ignored
