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

## 5. v2.1.0 改进内容

### 5.1 稳健性

1. **HTTP 超时**：所有 API 请求增加 30 秒超时（`REQUEST_TIMEOUT`）。此前 `requests.post` 无超时，南网服务器无响应时会永久占用执行器线程。
2. **启动容错**：`async_setup_entry` 中验证登录态时，网络异常（`RequestException`/`CSGAPIError`）现抛出 `ConfigEntryNotReady`，HA 启动早于网络就绪时会自动退避重试，而不是永久失败。
3. **会话中途过期**：coordinator 轮询中一旦捕获 `NotLoggedIn`，本轮结束立即抛出 `ConfigEntryAuthFailed` 触发重新认证流程，不再等到下一轮询。
4. **移除集成时登出**：`async_remove_entry` 中登出请求增加异常捕获，网络不可用时不阻塞集成删除。

### 5.2 数据正确性（传感器 state_class 修复）

| 传感器 | 原状态类 | 现状态类 | 原因 |
|---|---|---|---|
| 余额、欠费 | total | **measurement** | 余额是瞬时水平量，非累计量，原写法导致长期统计失真 |
| 阶梯剩余电量 | total | **measurement** | 随月份递减的水平量 |
| 阶梯电价 | total | **measurement** | 价格是瞬时量 |

另为数值传感器增加 `suggested_display_precision`（常规 2 位小数，阶梯电价 4 位）。

### 5.3 实体与刷新语义

1. **先刷新后建实体**：`async_setup_entry` 改为 `await async_config_entry_first_refresh()` 后再 `async_add_entities`。实体创建即有数据；首次刷新时登录过期会正确触发 reauth，而非遗留不可用实体。
2. **配置实时生效**：coordinator 每轮从 `config_entry.data` 重新读取配置（此前为启动时快照），修改刷新间隔等选项后下一轮即生效。
3. **API 层空值保护**：新增 `safe_float()` 工具，`totalPower`/`totalActualAmount`/`balance` 等字段为 `None` 时不再抛 `TypeError`；绑定缴费号列表缺关键字段时跳过并告警而非崩溃。

### 5.4 配置流修复

1. **浅拷贝 mutation 修复**：选项流中 `dict(entry.data)` 是浅拷贝，直接修改 `new_data[CONF_ELE_ACCOUNTS]`/`new_data[CONF_SETTINGS]` 实际上原地改写了 entry.data 内层对象。现均改为显式拷贝内层字典。
2. **设置修改立即生效**：`async_step_settings` 修改刷新间隔后 reload 集成（原实现需重启 HA 或手动重载才生效——真实 bug）。
3. **添加缴费号网络异常**：`async_step_add_account` 中连接南网失败时以 `cannot_connect` 中止（已补翻译），而非裸异常。
4. **删除设备后重载**：`async_remove_config_entry_device` 移除账户后 reload 集成，coordinator 立即停止轮询已删除账户（原先会一直轮询直至重启）。

### 5.5 其它

- manifest.json：版本升至 2.1.0，新增 `integration_type: hub`；移除空的 `homekit`/`ssdp`/`zeroconf` 字段。
- 翻译：options 流新增 `cannot_connect` 中止原因（zh-Hans / en）。
- README 重写：新增实体表（含状态类说明）、Energy 面板使用说明、FAQ、调试方法、更新节流策略说明。
- 文档与代码中单位常量改用 `UnitOfCurrency.CNY`。

