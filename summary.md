# 南方电网集成 v2 架构分析与重构说明

## 1. 原仓库架构分析

仓库: https://github.com/CubicPill/china_southern_power_grid_stat

### 1.1 模块组成

| 文件 | 职责 |
|------|------|
| `manifest.json` | Home Assistant 集成元数据：domain、依赖（pycryptodome/brotli）、版本等 |
| `const.py` | 配置项、传感器后缀、属性键、默认更新策略等常量 |
| `__init__.py` | 配置入口 setup/unload、登出、删除缴费号 |
| `config_flow.py` | GUI 配置流程：选择登录方式 → 短信/密码/扫码登录 → 添加缴费号 → 参数设置 |
| `sensor.py` | Coordinator + SensorEntity：余额、欠费、昨日/当月/当年/上月/去年用电量与电费、阶梯信息 |
| `csg_client/__init__.py` | 同步 HTTP 客户端，封装南网 App API、AES/RSA 加密、登录、查询 |
| `csg_client/const.py` | API 路径、密钥、状态码、枚举、常量 |

### 1.2 登录与鉴权

- 登录入口：短信验证码、短信+密码、南网 APP / 微信 / 支付宝扫码
- 加密：请求体使用 AES-CBC（硬编码 KEY/IV），密码字段使用 RSA 公钥加密
- 鉴权：登录后通过 response header 获取 `x-auth-token`，后续请求放在 header 中
- 问题：README 明确说明登录态失效后**不再自动重新登录**，需要用户手动重载集成

### 1.3 数据抓取的 API（App 端 `ucs/ma/zt/`）

| API | 数据 |
|-----|------|
| `center/sendMsg` | 发送登录短信 |
| `center/login` / `loginByPwdAndMsg` | 登录 |
| `center/createLoginQrcode` / `getLoginInfo` | 扫码登录 |
| `user/queryAuthenticationResult` | 验证登录态 |
| `user/getUserInfo` | 获取 custNumber |
| `eleCustNumber/queryBindEleUsers` | 列出绑定缴费号 |
| `charge/queryMeteringPoint` | 计量点 ID |
| `charge/queryDayElectricByMPoint` | 指定月每日用电量 |
| `charge/queryDayElectricChargeByMPoint` | 指定月每日电费 + 阶梯 |
| `charge/queryUserAccountNumberSurplus` | 余额/欠费 |
| `charge/getAnalyzeFeeDetails` | 年度用电量/电费 + 月明细 |
| `charge/queryDayElectricByMPointYesterday` | 昨日用电量 |

### 1.4 传感器清单

余额、欠费、昨日用电量、最近一日用电量/电费、当月/当年/上月/去年总用电量/电费、当前阶梯档位/剩余电量/电价，以及每日/每月明细作为 extra_state_attributes。

### 1.5 主要问题

- 代码全部堆在一个大文件（`csg_client/__init__.py`），缺少清晰分层
- 异常与常量混合
- `asyncio.gather` 使用 `return_exceptions=True` 但仍用 `(success, result)` 模式，略显冗余
- 对 `async_timeout.timeout` 的写法较老（新版 HA 推荐 `asyncio.timeout`）
- 没有类型提示、文档和健壮的错误兜底

## 2. 重构后的集成 `csg_power`

### 2.1 目录结构

```
custom_components/csg_power/
├── __init__.py
├── config_flow.py
├── const.py
├── manifest.json
├── sensor.py
├── api/
│   ├── __init__.py      # CSGClient 与 CSGElectricityAccount
│   ├── const.py         # API 常量、密钥、枚举
│   └── exceptions.py    # CSGAPIError / InvalidCredentials / NotLoggedIn 等
└── translations/
    └── zh-Hans.json
```

### 2.2 架构改进

1. **职责分离**：HTTP 客户端、异常、常量分文件；API 层只关心请求/响应，HA 层只关心配置和实体。
2. **类型提示**：所有公共函数补齐类型标注，减少运行时错误。
3. **Modern HA**：`asyncio.timeout` 替代 `async_timeout.timeout`。
4. **错误处理**：fetch 包装统一返回 `(success, result)`；sensor 层对 `STATE_UNAVAILABLE` 和 `STATE_UPDATE_UNCHANGED` 做完整分支处理。
5. **配置流程**：保留原登录方式，修复原代码中 import 与 schema key 的潜在 bug。
6. **向后兼容**：数据结构与原版基本一致，方便从旧版迁移。

### 2.3 关键实现点

- `CSGClient` 仍为同步实现，通过 `hass.async_add_executor_job` 在 HA 中运行。
- `CSGElectricityAccount.dump()` / `load()` 负责序列化到 config entry。
- `CSGCoordinator` 在每次轮询时：
  1. 验证并初始化 client
  2. 补充缺失的 `metering_point_number`
  3. 并发抓取余额/欠费、昨日、当年/去年、当月/上月数据
  4. 合并日用电与日电费数据，推导“最近一日”传感器
  5. 按日期策略降低上月/去年更新频率

## 3. 使用方式

1. 将 `custom_components/csg_power` 复制到 Home Assistant 的 `custom_components/` 目录。
2. 重启 Home Assistant。
3. 在「设置 → 设备与服务 → 添加集成」中搜索「China Southern Power Grid」。
4. 按提示登录并选择缴费号。
5. 集成会自动创建对应的传感器。

## 4. 注意事项

- 与原仓库一样，仍需手动处理登录态过期问题：登录过期后 Home Assistant 会提示重新配置。
- 阶梯电价、峰谷电价等计算不在本集成范围内，仅做数据抓取。
- 建议更新间隔不低于 60 秒，默认 4 小时。
