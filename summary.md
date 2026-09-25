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

## 6. v2.1.1 改进内容

### 6.1 关键 bug：reauth 流程被误中止（已修复）

经核对 HA 2024.4.3 源码验证：`ConfigFlow._abort_if_unique_id_configured()` 内部**没有**针对 reauth 的豁免逻辑（`_async_current_entries` 也不会排除正在被重新认证的 entry）。而本集成的 reauth 流程会经过 `check_and_set_unique_id()` → `_abort_if_unique_id_configured()`，由于被重新认证的 entry 本身就持有 `CSG-<手机号>` 这个 unique_id，**reauth 流程必然在输入手机号后即被 `already_configured` 中止——登录过期后用户根本无法完成重新认证**。

修复：`check_and_set_unique_id()` 现在检测 reauth 上下文（`self._reauth_entry`），当其 unique_id 与当前输入匹配时跳过 abort；仅在不同 entry 冲突时才中止。

### 6.2 安全与健壮性

1. **不再持久化明文密码**：`CONF_PASSWORD` 之前被写入 entry.data（即明文落在 `.storage`），但全工程无任何读取方（不存在自动重登）。现仅在 flow 内存上下文中传递，完成登录后即丢弃；reauth 更新 entry 时会顺带清掉旧数据中遗留的密码。
2. **logout 凭据类型归一化**：`str(LoginType.LOGIN_TYPE_SMS)` 会得到 `"LoginType.LOGIN_TYPE_SMS"` 而非 `"11"`（Python 枚举 `__str__` 行为）。现改用 `getattr(login_type, "value", login_type)`，兼容枚举与持久化后的纯字符串两种形态。
3. **非法 JSON 响应**：`_make_request` 解析响应体失败时抛出 `CSGAPIError("invalid_json", ...)`，替代原先的裸 `JSONDecodeError`，coordinator 与 config flow 中均能归类为 API 错误而非"未知异常"。

### 6.3 仓库与 CI

1. 移除过期的 `csg_power_v2.0.0.zip`（HACS 不依赖 zip，且其内容已过时；发布建议改用 GitHub Release 附件）。
2. 新增 `.github/workflows/validate.yml`：push/PR 时自动运行 pyflakes、verify_all.py、hassfest 校验与 HACS 校验。
3. manifest 版本升至 2.1.1。

## 7. v2.1.2 改进内容

### 7.1 配置流异常处理补全（扫码登录崩溃修复）

此前扫码登录流程中多处 API 调用没有任何异常捕获：

1. **二维码过期导致 flow 崩溃**：二维码有效期约 5 分钟，过期后 `getLoginInfo` 返回非成功状态，客户端抛 `CSGAPIError`，而 `async_step_validate_qr_login` 未捕获——整个配置流程直接以"未知错误"崩溃，用户只能从头再来。现在捕获后返回原表单并提示"二维码可能已失效，请刷新后重新扫码"，用户勾选刷新即可重试。
2. **生成二维码失败**（网络异常）：`async_step_qr_login` 现在返回带 `cannot_connect` 错误的表单而非崩溃。
3. **扫码成功后获取用户信息失败**：同样捕获并允许重试。
4. **选项流添加缴费号**：`initialize`/`get_all_electricity_accounts` 的网络异常现在以 `cannot_connect` 优雅中止。

### 7.2 校验工具增强

- `verify_all.py` 新增**翻译结构一致性检查**：strings.json / zh-Hans.json / en.json 三份文件键结构必须完全一致，防止未来某个语言悄悄缺翻译。
- manifest 版本升至 2.1.2。

## 8. v2.1.3 改进内容

### 8.1 新增单元测试套件（27 个用例）

项目此前完全依赖静态检查，本轮为无 Home Assistant 依赖的纯逻辑层建立了 `tests/`（pytest）：

- `safe_float`：None/空串/非法串/合法数值全边界
- `encrypt_params` / `decrypt_params`：AES-CBC 加解密往返（含中文、空对象、base64 合法性）
- `CSGElectricityAccount.dump()/load()`：序列化往返、缺必填键报错、计量点号可选
- `merge_by_day_data`：双方不可用、单方回退、长度优先、charge 补丁合并、kwh 取最大等全分支
- `CSGClient._make_request`：成功路径（并断言 timeout 传参）、非 200 → CSGHTTPError、非法 JSON → CSGAPIError、鉴权头注入
- `verify_login`：正常 / NotLoggedIn → False
- `logout`：LoginType 枚举 → "11"、纯字符串透传（回归锁定 v2.1.1 的修复）
- `tests/conftest.py` 在未安装 HA 的环境中注入 stub 模块，使 `csg_power` 包可初始化

`merge_by_day_data` 为此从 sensor.py（依赖 HA）迁至新的 `utils.py`（零 HA 依赖），coordinator 调用点同步更新。

### 8.2 测试直接抓出的真 bug：加密填充按字符计算

`encrypt_params` 的零填充按 **Unicode 字符数**计算（`len(content)`），而 AES-CBC 需要按 **UTF-8 字节数**对齐——中文每字 3 字节，任何含中文的加密请求体都会抛出 "Data must be padded to 16 byte boundary"。当前登录 payload 恰好全 ASCII 才未触发。已改为对编码后的字节序列填充；对 ASCII 输入行为完全不变（27 个用例含中文往返验证）。

### 8.3 其它

- 修复"最近日电费"为 0 时被 `or` 运算误判为不可用的边界（改为显式 None 判断）。
- CI 的 static-checks job 现在安装 pytest/pycryptodome/requests 并运行单元测试。
- manifest 版本升至 2.1.3。

## 9. v2.1.4 改进内容

### 9.1 Coordinator 业务逻辑测试（15 个新用例，共 42 个）

此前测试只覆盖 api 层，本轮把 coordinator 的核心业务逻辑纳入回归防护：

- `_update_latest_day`：本月亮最后一天、**0 电费回归锁定**（v2.1.3 修复）、上月回退、双方不可用、UNCHANGED 哨兵不误用。
- `_update_states`（日期节流策略）：首次更新全刷、月初 ≤3 日刷新上月、月末跳过上月、1 月前 7 日刷新去年、同日不重复刷新去年、年月变量计算（含 1 月→去年 12 月）。
- `_async_fetch`：成功、NotLoggedIn（置 `_login_expired` 标志）、CSGAPIError（不置标志）、任意异常兜底。

### 9.2 测试基建升级

- `tests/conftest.py` 从纯 MagicMock 兜底升级为**结构化 HA stub**：`DataUpdateCoordinator`/`CoordinatorEntity`/`SensorEntity` 是具有真实 `__init__` 签名的类（MagicMock 实例不能作类基类），`STATE_UNAVAILABLE`/`CONF_USERNAME`/单位枚举等是真值常量。`sensor.py` 因此可在无 HA 环境导入，业务逻辑测试成为可能；未结构化的符号仍由 MagicMock 兜底。
- coordinator 实例用 `__new__` 构造（跳过父类初始化），仅提供方法实际触碰的属性，测试不依赖 HA 运行时。
- manifest 版本升至 2.1.4。

## 10. v2.1.5 改进内容

### 10.1 加回 brotli 依赖（条件性回归修复）

初版 v2.0.0 的 requirements 为 `["pycryptodome", "brotli", "async_timeout"]`，后续 "remove unused deps" 提交把 brotli 一并删除——删除者只看到代码里没有 `import brotli`，但 `_common_headers` 手动宣告了 `Accept-Encoding: gzip, deflate, br`：服务器返回 Brotli 压缩响应时，环境中若无 brotli 包则响应体无法解压（requests/urllib3 依赖 brotli 解码 br）。多数 HA 环境因 aiohttp speedups 附带 Brotli 而侥幸正常，但依赖未声明即不受保证。已加回 `"brotli>=1.1"`，与 header 宣告能力和上游实测行为对齐；`async_timeout` 的删除经核实是正确的（代码已改用 `asyncio.timeout`）。

### 10.2 CI 与校验工具

- workflow 增加最小权限声明（`permissions: contents: read`），Actions 安全基线。
- verify_all.py 新增 **manifest 完整性检查**：必填键齐全、version 语义化格式（x.y.z）、domain 与目录名一致、iot_class 合法值、requirements 条目格式规范。
- manifest 版本升至 2.1.5。

## 11. v2.1.6 改进内容（终审）

### 11.1 终审重读

全部改动完成后首次完整重读六个核心文件（api 客户端、sensor、config_flow、__init__、utils、tests），确认多轮补丁叠加后逻辑自洽：reauth 修复、密码不落盘、QR 异常处理、`_login_expired` 标志与首次刷新语义相互兼容。修正一处类型注解失实：`api_get_metering_point` 实际返回列表而非字典。

### 11.2 跨文件一致性检查

verify_all.py 新增 **AST 交叉检查**：sensor.py 中引用的所有 `SUFFIX_*`/`ATTR_KEY_*` 键必须出现在 coordinator 的 `_gathered_data[...][KEY] = ...` 赋值目标中——防止"添加了传感器实体却没有任何数据源"这类错误（当前 22 个键全部有来源）。该检查独立于单元测试，对未写测试的新代码同样有效。

### 11.3 CI 实证

下载 v2.1.5 的 HACS 校验日志确认：license 检查错误已消失（2/9 → 1/9 checks failed），仅剩 brands 注册项（已知一次性待办，CI 中非阻塞）。

- manifest 版本升至 2.1.6。

