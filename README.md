# China Southern Power Grid (csg_power)

A custom Home Assistant integration for China Southern Power Grid (广东/广西/云南/贵州/海南） electricity usage and billing data.

This integration fetches data from the official CSG mobile app APIs and exposes electricity usage, costs, balance/arrears, and tier ladder information as Home Assistant sensors.

## Features

- Query electricity usage and billing data for China Southern Power Grid accounts
- Support login methods:
  - SMS verification code
  - SMS code + password
  - CSG App QR code
  - WeChat QR code
  - Alipay QR code
- Multiple billing accounts per user account
- Configurable update interval (default: 4 hours, minimum: 60 seconds)
- Automatic update throttling for last month / last year data based on date
- Sensors:
  - Account balance
  - Arrears
  - Yesterday electricity usage
  - Latest day electricity usage & cost
  - This month electricity usage & cost
  - This year electricity usage & cost
  - Current tier ladder / remaining kWh / tariff
  - Last month electricity usage & cost
  - Last year electricity usage & cost
- Extra state attributes:
  - Daily breakdown for current / last month
  - Monthly breakdown for current / last year
  - Latest day date
  - Tier ladder start date

## Installation

### Manual

1. Copy the `custom_components/csg_power` folder into your Home Assistant `custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **China Southern Power Grid** and follow the setup wizard.

### HACS

This integration can be installed via HACS once published as a custom repository. Add this repository URL to HACS as an integration category and install.

## Configuration

The integration is fully configured through the UI. During setup:

1. Select a login method.
2. Complete login (SMS code / password / QR scan).
3. Select the billing account(s) you want to monitor.
4. Adjust update interval in the integration options if needed.

## Requirements

- Home Assistant 2024.4 or newer (uses `asyncio.timeout`)
- Python packages installed automatically by Home Assistant:
  - `pycryptodome`
  - `brotli`

## Notes

- This integration only reads and converts data from CSG servers. It does not calculate tiered or time-of-use electricity tariffs itself.
- CSG login sessions may expire; if this happens, Home Assistant will prompt you to re-authenticate.
- Keep update interval reasonable (default 4 hours) to avoid overloading CSG servers.

## License

GPLv3
