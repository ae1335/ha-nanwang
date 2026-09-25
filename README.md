# China Southern Power Grid (csg_power)

A custom Home Assistant integration for China Southern Power Grid (南方电网, 广东/广西/云南/贵州/海南) electricity usage and billing data.

This integration fetches data from the official CSG mobile app APIs and exposes electricity usage, costs, balance/arrears, and tier ladder information as Home Assistant sensors.

一个用于查询**南方电网**用电量与电费数据的 Home Assistant 自定义集成，支持余额、欠费、日/月/年用电量与电费、阶梯电价等传感器。

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
- Startup resilience: temporary network failures retry automatically (`ConfigEntryNotReady`) instead of failing setup
- HTTP timeouts on all API requests so a slow CSG server can never hang Home Assistant
- Expired sessions trigger the re-authentication flow promptly
- Sensors:
  - Account balance *(measurement)*
  - Arrears *(measurement)*
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

## Entities

| Entity (suffix) | 中文 | Unit | State class |
|---|---|---|---|
| `balance` | 余额 | CNY | measurement |
| `arrears` | 欠费 | CNY | measurement |
| `yesterday_kwh` | 昨日用电量 | kWh | total |
| `latest_day_kwh` | 最近日用电量 | kWh | total |
| `latest_day_cost` | 最近日电费 | CNY | total |
| `this_month_total_usage` | 本月累计用电量 | kWh | total |
| `this_month_total_cost` | 本月累计电费 | CNY | total |
| `this_year_total_usage` | 本年总用电量 | kWh | total |
| `this_year_total_cost` | 本年总电费 | CNY | total |
| `current_ladder` | 当前阶梯档位 | — | — |
| `current_ladder_remaining_kwh` | 阶梯剩余电量 | kWh | measurement |
| `current_ladder_tariff` | 阶梯电价 | CNY | measurement |
| `last_month_total_usage` | 上月累计用电量 | kWh | total |
| `last_month_total_cost` | 上月累计电费 | CNY | total |
| `last_year_total_usage` | 上年总用电量 | kWh | total |
| `last_year_total_cost` | 上年总电费 | CNY | total |

Balance, arrears, remaining ladder quota and tariff are `measurement` sensors so that Home Assistant long-term statistics stay meaningful (they are levels, not cumulative totals).

## Installation

### HACS (recommended)

1. Add this repository URL to HACS as a custom repository of category **Integration**.
2. Install **China Southern Power Grid**.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/csg_power` folder into your Home Assistant `custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **China Southern Power Grid** and follow the setup wizard.

## Configuration

The integration is fully configured through the UI. During setup:

1. Select a login method.
2. Complete login (SMS code / password / QR scan).
3. Select the billing account(s) you want to monitor.
4. Adjust update interval in the integration options if needed.

### Options

Open the integration's **Configure** dialog to:

- **添加已绑定的缴费号 / Add billing account** — add more accounts linked to your CSG login. Takes effect immediately (the entry reloads).
- **参数设置 / Settings** — change the update interval (minimum 60 s). Takes effect immediately.

### Update throttling

To avoid pointless requests, some data is only refreshed near the beginning of a period:

- **Last month data**: refreshed while the current day-of-month ≤ 3 (then the month is closed and no longer changes).
- **Last year data**: refreshed in the first 7 days of January only.

## Energy Dashboard

The kWh sensors (`this_month_total_usage`, `yesterday_kwh`, `latest_day_kwh`, …) have device class *energy* and can be added to the Home Assistant **Energy dashboard**. Note that these values come from CSG's backend and are typically updated once per day — they are meter readings, not real-time measurements.

## FAQ

**Q: Why did all sensors become unavailable / a "重新认证" (re-authenticate) notice appeared?**
The CSG login session expired. Follow the repair prompt to log in again — the integration keeps all accounts and settings.

**Q: Why is "last month" data not updating?**
By design it is only refreshed in the first 3 days of each month, because CSG does not change closed-month data afterwards.

**Q: Can I use a shorter update interval than 4 hours?**
Yes (down to 60 s), but keep it reasonable — the integration is polling a real cloud service and very aggressive polling may get your account rate-limited or blocked.

**Q: Does it work outside 广东/广西/云南/贵州/海南?**
No. This integration only supports China Southern Power Grid. For State Grid (国网) regions, look for a State Grid integration instead.

## Debugging

Add this to `configuration.yaml` and restart to get detailed API logs:

```yaml
logger:
  logs:
    custom_components.csg_power: debug
```

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
