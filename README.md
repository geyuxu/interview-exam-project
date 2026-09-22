# 订单详情、物流查询与运费估算

Python / FastAPI + Vue 3 / TypeScript / Vite。支持订单切换、商品匹配、GST 计算、多批次配送、物流查询及 JSON 导入。

## 功能

- 按订单、客户或 SKU 搜索，展示商品、联系人、收货地址与金额汇总。
- 使用真实商品查询结果的本地快照，包含 9 个 SKU 的名称、描述、价格及包装规格。
- Australia Post / StarTrack 服务端测试接口查询，展示状态和事件，处理超时、认证失败及无记录。
- 下载订单模板、导入 JSON、校验字段和跨订单关联；导入订单同样可以查询物流。
- 可选运费估算，默认关闭。商品图片使用中性占位图；TNT 暂未集成，相关运费为 A$0.00。
- 桌面与移动端布局，接口异常后可重试，导入数据仅保留在当前页面。

## 本地运行

环境：Python 3.11+、Node.js 22.12+（22.x）或 24+、npm、Git。

```powershell
git clone https://github.com/geyuxu/interview-exam-project.git
cd interview-exam-project
```

两个终端分别从仓库根目录启动服务。

### 后端（Windows PowerShell）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

在本地 `backend/.env` 中填写承运商测试凭证。无凭证仍可浏览订单、导入及计算金额，物流显示未配置。PyCharm 解释器选择 `backend/.venv/Scripts/python.exe`。macOS / Linux 使用 `.venv/bin/python`，首次复制配置可用 `cp -n .env.example .env`。

健康检查：<http://127.0.0.1:8000/api/health>；交互接口文档：<http://127.0.0.1:8000/docs>。

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>。开发服务器将 `/api` 代理到 8000 端口，可通过服务端环境变量 `API_PROXY_TARGET` 调整。锁文件使用 npm 镜像地址及完整性校验，不修改全局 npm 配置。

生产部署需要静态文件服务和 `/api` 反向代理；当前应用用于本地运行，未实现登录和生产环境访问控制。

## 数据

商品目录来自 SQL 查询服务的 `product_list` 表：

```sql
SELECT * FROM product_list
WHERE SKU IN ('TBAMET10','TBAMET28','TBOPAL28','AURPUR10','HARNIG','LELCBD100','HALGEO15','MCMW10','MCBO30');
```

`backend/data/products.json` 保存实际查询返回的完整 9 条记录；`backend/data/source.json` 记录查询入口、SQL、获取时间和记录数。这是数据库查询结果快照，运行时不会实时连接数据库。更新时重新执行查询，替换完整结果并同步来源记录。

`backend/data/orders.json` 保存初始订单及配送关联，也是页面下载模板的内容。商品名称和规格按查询结果显示，不根据 SKU 猜测。模拟物流响应仅用于自动化测试；应用始终调用真实承运商接口。

### 导入结构

| 集合 | 必要字段 |
|---|---|
| `orders` | `order_no`, `order_date`（YYYY-MM-DD）, `status`, `company`, `customer`, `phone`, `email`, `address`, `postcode` |
| `shipments` | `id`, `order_no`, `carrier`（startrack/auspost/tnt）, `tracking_no` |
| `line_items` | `order_no`, `sku`, `quantity`, `shipment_id` |

订单编号和物流 ID 各自唯一；数量必须是 1–100000 的整数，邮编为四位数字。每个订单和配送批次至少包含一行商品，商品引用的配送批次必须属于同一订单。

最多支持 100 个订单、500 个配送批次、2000 行商品；前后端均限制请求为 1 MiB，支持 UTF-8 BOM。未知字段、无效数量、重复 ID 和错误关联会被拒绝。导入内容不持久化。

SKU 未匹配或价格无效时，保留其他可展示信息，将受影响订单的 Subtotal、GST 和 Total 标记为不可计算；其他订单照常计算。

## 金额与运费

所有金额为 AUD，RRP 已含 10% GST：

```text
未税单价 = RRP / 1.10
未税行金额 = 未税单价 × 数量
订单未税小计 = 本订单未税行金额之和
GST = 订单未税小计 × 10%
总额 = 未税小计 + GST + 运费
```

后端使用 Decimal 保留计算精度，展示金额按 ROUND_HALF_UP 舍入到分。总额使用已舍入的小计、GST 和运费相加。各行展示值之和可能与整体舍入相差一分钱，接口返回 `rounding_adjustment`，页面显示说明，不额外收费。输入价格必须非负、有限且精确到分。

当前商品快照的核对结果（不计运费）：

| 订单 | 未税小计 | GST | 总额 |
|---|---:|---:|---:|
| PO-20251130-00072 | A$1,937.27 | A$193.73 | A$2,131.00 |
| PO-20251203-00046 | A$1,504.55 | A$150.45 | A$1,655.00 |

运费估算默认关闭，开启后按配送批次计算。以下是估算规则，不是承运商报价：

1. 商品重量换算为 kg，体积换算为 cm³，分别乘数量后求和；无体积时由长宽高计算。
2. 每批增加 0.2 kg 包材重量，体积增加 20% 包装余量。
3. 计费重量为 `max(商品重量 + 0.2, 商品体积 × 1.2 / 5000)`，向上取整到 kg。
4. 每批运费为 A$8 + A$2.50 × 计费重量 + 邮区附加费。从邮编 2111 出发，目的邮编首位不是 2 时附加 A$3。
5. 缺少有效规格或承运商为 TNT 时，该批运费为 A$0.00 并显示原因。

不使用含义不明确的 `Volumetric_GrossWeight` 字段。运费作为最终金额加入总额，商品 GST 单独计算。初始两笔订单开启估算后，各增加 A$16.00。

## 物流接口

```text
GET https://digitalapi.auspost.com.au/test/shipping/v1/track?tracking_ids=...
Authorization: Basic <API key 与 password 的编码>
Account-Number: <对应产品账户>
Content-Type: application/json
Accept: application/json
```

凭证只在后端读取，操作系统环境变量优先于 `.env`：

| 环境变量 | 用途 |
|---|---|
| `AUSPOST_API_KEY` | API key |
| `AUSPOST_API_PASSWORD` | API password |
| `STARTRACK_ACCOUNT_NUMBER` | StarTrack 产品账户 |
| `AUSPOST_ACCOUNT_NUMBER` | Australia Post 产品账户 |

账户按字符串处理以保留前导零。只连接 testbed；单次查询超时 10 秒，同进程每分钟最多 10 次外部查询，同一单号缓存 60 秒。凭证变更会使旧缓存失效，同一单号的重复并发请求会合并阻止重复调用，其他单号无需等待其网络请求。多进程部署需共享缓存和限流器。

返回结果严格匹配 `tracking_id`，读取包裹状态和事件，时间保留服务端原始格式。测试环境结果会明确标记。错误只返回安全的状态说明、HTTP 状态和错误代码，不输出凭证或上游完整响应。

**当前集成限制：** 2026-09-22 实际查询仍返回 HTTP 401 / `API_001`（认证失败）。测试环境 `/shipments` 也返回同样错误，需有效测试凭证或承运商恢复授权后才能验证成功轨迹。界面保留不可用状态和重试入口。TNT 澳洲国内接口尚未实现，运费为零。

## 接口与目录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务健康检查 |
| GET | `/api/orders?estimate=false` | 获取初始订单及计算结果 |
| GET | `/api/orders/template` | 下载 JSON 导入模板 |
| POST | `/api/orders/preview?estimate=false` | 校验并计算传入订单 |
| GET | `/api/shipments/{shipment_id}/tracking` | 查询初始订单的配送批次 |
| POST | `/api/tracking` | 根据 `carrier` 和 `tracking_no` 查询物流，支持导入订单 |

输入校验失败返回 422，超过请求大小上限返回 413，本地数据不可读返回 503。承运商不可用时返回 HTTP 200 及明确的业务状态 `unavailable`；`http_status` 表示承运商的响应状态。前端在更新页面前通过 Zod 验证响应结构。

```text
backend/app/models.py        输入与关系校验
backend/app/orders.py        商品匹配、金额与运费
backend/app/tracking.py      承运商适配、缓存与限流
backend/app/middleware.py    请求大小限制
backend/app/main.py          路由与配置
backend/data/               订单、商品快照和来源记录
backend/tests/              后端回归测试
frontend/src/App.vue         页面和交互
frontend/src/contracts.ts    接口响应校验与类型
frontend/tests/              桌面和移动端浏览器测试
.github/workflows/ci.yml     自动化检查
```

## 测试

在仓库根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m ruff check backend
.\backend\.venv\Scripts\python.exe -m ruff format --check backend
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm ci
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
```

也可使用已安装的 Edge：在运行浏览器测试前设置 `$env:PLAYWRIGHT_CHANNEL = 'msedge'`。测试独立启动后端 8011 和前端 5181，请保持这两个端口空闲。

测试覆盖金额及舍入、输入关联、上传大小、损坏数据、认证请求和失败响应、缓存及并发，以及桌面和移动端的切换、搜索、模板下载、导入、运费、物流和异常恢复。测试进程禁用本地承运商凭证，物流响应替身仅存在于测试中。当前共 51 项后端测试、10 项浏览器测试；后端测试依赖存在两条第三方弃用警告。

GitHub Actions 在推送和 PR 时执行后端检查、前端格式和构建检查，以及 Chromium 浏览器测试。

## 仓库与配置

仓库：[geyuxu/interview-exam-project](https://github.com/geyuxu/interview-exam-project)。`.env`、虚拟环境、依赖、构建产物及测试报告均被 Git 忽略；只提交无凭证的 `.env.example`。

接口参考：[Australia Post Track Items](https://developers.auspost.com.au/content/apis/shipping-and-tracking/reference-track-items.html)、[测试环境与认证 FAQ](https://developers.auspost.com.au/content/apis/shipping-and-tracking/info/api-resources/faq.html)。
