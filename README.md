# 订单详情、物流查询与运费估算

Python / FastAPI + Vue 3 / TypeScript / Vite。按订单匹配商品、计算 GST，展示收货信息和多个配送批次。

## 已实现

- 两笔题目订单、9 个 SKU 的真实商品查询结果；按订单独立计算。
- 订单切换、按订单/客户/SKU 搜索、商品名称与描述、含税 RRP、未税单价和行小计。
- 商品中性占位图、收货地址、联系人、物流批次、金额汇总。
- Australia Post / StarTrack 服务端测试接口查询，超时、认证失败、无记录、格式异常等回退。
- 可选运费估算，默认关闭；TNT 未实现，相关运费为 A$0.00。
- JSON 文件导入预览、字段及关联校验、缺失商品提示。预览不保存文件、不查询外部物流。
- 后端自动化测试覆盖金额、数据关联、缺失数据及外部接口失败。

## 数据来源与真实性

所有运行时商品名称、描述、价格及重量/尺寸均来自材料 `SQL.download` 指定的查询入口。
查询页面说明真实表名为 `product_list`，示例中的 `sku` 不是本题表名。

```sql
SELECT * FROM product_list
WHERE SKU IN ('TBAMET10','TBAMET28','TBOPAL28','AURPUR10','HARNIG','LELCBD100','HALGEO15','MCMW10','MCBO30');
```

实际查询返回 9 条匹配记录，完整 JSON 原样保存在 `backend/data/products.json`。
`backend/data/source.json` 记录入口、查询语句、获取时间和记录数。长版题目明确允许将查询结果作为本地 JSON 使用；它是实际查询结果的快照，不是假造商品数据，也不是实时数据库连接。
要更新目录，请在指定网站执行上述查询，将完整结果保存到 `products.json`，同步更新来源记录。未筛选的 `SELECT *` 默认只返回 10 行，不适合直接拿来当完整商品目录。

订单和物流映射来自题目，保存在 `backend/data/orders.json`。没有用示意截图中的虚构商品或轨迹替代题目数据。

允许的替代项：商品占位图、明确标识的运费估算公式、未实现/不可用时的零运费。
模拟商品和物流响应仅用于 `backend/tests/` 验证异常处理，不由应用返回为真实查询结果。

## 本地运行

环境：Python 3.11+、Node.js 22.12+（22.x）或兼容的更新 LTS、npm、Git。
当前工程位于 `C:\Users\geyux\PycharmProjects\ExamProject2`。
在 PyCharm 中选择 `backend/.venv/Scripts/python.exe` 为解释器；目标目录原有的根级 `.venv` 与 `.idea` 已保留。

两个终端分别从仓库根目录执行以下命令。

### 后端（Windows PowerShell）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 第一次配置时复制模板，再在本地填写材料中的测试凭证：
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

已有 `.env` 时跳过复制，避免覆盖本地配置。无凭证也能查看订单、计算金额和导入预览，物流区域会显示“未配置”。
macOS / Linux 使用 `.venv/bin/python`，复制命令改为 `cp .env.example .env`。

- 健康检查：<http://127.0.0.1:8000/api/health>
- 接口文档：<http://127.0.0.1:8000/docs>

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 将 `/api` 代理到本地 8000 端口。
初始化时 npm 官方源下载超时，因此锁文件使用 npm 镜像 `https://registry.npmmirror.com` 的地址和完整性校验；没有修改全局 npm 配置。

### 校验

```powershell
# 仓库根目录
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm run build
```

构建先执行 TypeScript 类型检查，再生成 `frontend/dist/`。
本轮验证：38 项后端测试通过；浏览器验证了订单切换、搜索、JSON 导入、缺失 SKU、非法数量、运费切换、接口失败后重试以及移动端布局。
当前测试依赖会产生两条第三方弃用警告，不影响测试通过；未将其静默隐藏。
生产部署需单独配置静态文件服务和 `/api` 反向代理，不能直接使用 Vite 开发代理作为生产配置。
当前定位是本地评估项目，未实现登录或生产环境访问控制。

## 输入结构

`backend/data/orders.json` 同时也是可在页面“导入 JSON”中使用的完整示例。

| 集合 | 必要字段 |
|---|---|
| `orders` | `order_no`, `order_date`（YYYY-MM-DD）, `status`, `company`, `customer`, `phone`, `email`, `address`, `postcode` |
| `shipments` | `id`, `order_no`, `carrier`（startrack/auspost/tnt）, `tracking_no` |
| `line_items` | `order_no`, `sku`, `quantity`, `shipment_id` |

订单编号及物流 ID 各自唯一，数量必须是 1–100000 的整数，邮编为四位数字。
每个订单和物流批次至少有一行商品；商品行引用的物流必须属于同一订单。
支持最多 100 个订单、500 个配送批次及 2000 行商品；前端文件限制 1 MB。
未知字段、无效数量、重复 ID、跨订单物流关联会被拒绝并显示错误位置。

SKU 未匹配或价格无效时，保留可展示的订单与商品信息，将受影响订单的 Subtotal、GST 和 Total 标记为不可计算，而不是把缺失价格当作零。其他订单正常计算。
业务逻辑没有硬编码样例订单号、SKU 或计算结果。

## 金额口径与舍入

采用长版的明确规则，纠正 PDF 中“价格已含税却再加税”的歧义：

```text
未税单价 = RRP / 1.10
未税行金额 = 未税单价 × 数量
订单未税小计 = 本订单未税行金额之和
GST = 订单未税小计 × 10%
总额 = 未税小计 + GST + 运费
```

后端使用 Decimal，内部保留精度；展示单价、行小计、订单未税小计和 GST 时分别按 ROUND_HALF_UP 舍入到分。
总额使用已舍入的订单未税小计、GST 和运费相加，避免显示汇总不平。
各行展示值相加与整体舍入结果可能有一分钱尾差，接口用 `rounding_adjustment` 返回差额，页面明确提示，不额外收费。
不对已含税 RRP 重复加税，不先舍入单价再计算整行。

当前查询快照、不计运费的核对结果（只用于文档与测试，非业务常量）：

| 订单 | 未税小计 | GST | 总额 |
|---|---:|---:|---:|
| PO-20251130-00072 | A$1,937.27 | A$193.73 | A$2,131.00 |
| PO-20251203-00046 | A$1,504.55 | A$150.45 | A$1,655.00 |

## 运费估算（题目允许的加分项）

默认不估算，显示 A$0.00。勾选开关后，按物流批次估算，再汇总至订单。
公式属于明确声明的设计假设，不是承运商合同价或实时运费报价：

1. `weight` 中的 g/kg 转为 kg，乘数量后求和；`volume` 中的 mm³/cm³/m³ 转为 cm³，乘数量后求和。没有 volume 时使用长宽高，支持 mm/cm/m。
2. 每批增加 0.2 kg 包材重量，体积增加 20% 包装余量。
3. 计费重量取 `max(商品重量 + 0.2 kg, 商品体积 × 1.2 / 5000)`，向上取整到 kg。
4. 每批费用 = A$8 基础费 + A$2.50 × 取整计费重量 + 邮区附加费。
5. 从 2111 出发，目的邮编首位不是 2 时附加 A$3；这是简化邮区规则，不等同于真实州界或承运商分区。
6. 不使用语义不清的 `Volumetric_GrossWeight` 字段，保留源值不擅自修正。商品包装尺寸也仅作为估算输入，不声称已解决真实装箱问题。
7. 缺失重量/尺寸时该批回退 A$0.00 并说明原因；TNT 始终回退 A$0.00。

运费作为最终待加金额参与题目总额公式，不再额外加一次 GST；GST 汇总仅按题目规定的商品未税小计计算。

## 物流接口与实际测试

使用 `材料/courier_testing_account.pdf` 提供的测试资料，与长版中的凭证逐项核对一致。

```text
GET https://digitalapi.auspost.com.au/test/shipping/v1/track?tracking_ids=...
Authorization: Basic <API key 与 password 的编码>
Account-Number: <对应产品账户>
```

凭证从后端环境变量读取；`.env` 通过 python-dotenv 加载，操作系统环境变量优先。
StarTrack 使用 `STARTRACK_ACCOUNT_NUMBER`，Australia Post 使用 `AUSPOST_ACCOUNT_NUMBER`，账号保持字符串以保留前导零。
单个请求只查询同一承运商的单号，10 秒超时；同一进程每分钟最多 10 次外部查询、相同单号缓存 60 秒。多进程生产部署应换成共享限流/缓存。
默认仅连接题目指定的 testbed，不会自动切换到生产环境。

2026-09-22 实际调用了以下 6 个题目提供的 StarTrack 测试单号：
`2FWZ50008569`、`2FWZ50008645`、`RBXZ50016112`、`2FWZ50020500`、`2FWZ50020498`、`2FWZ50020475`。
均返回 HTTP 401。可确认认证/授权失败，不能据此断言单号本身无效或凭证已过期。
应用显示不可用状态，不用模拟成功结果替代。完整的请求头或凭证不会输出到页面或日志。

正常响应按 `tracking_results` 中的 `tracking_id` 严格匹配，读取状态、包裹事件和最近有效更新时间；不把其他单号或订单状态冒充为物流结果。
测试环境的正常响应也明确标注为测试结果，不代表真实包裹轨迹。事件时间保留服务返回的原始格式。
TNT 材料包含 RTT / Weblinking / UAT 说明与凭证，但本轮未实现 TNT 集成；依据长版的可选范围，页面显示“未实现”及零运费。

## 材料差异与假设

- Python + Vue 同时符合 PDF 和长版的技术栈范围。
- PDF 第二笔订单头写 `PO-20251202-00046`，明细与长版写 `PO-20251203-00046`。输入数据按后者统一，业务逻辑不做特定订单号替换。
- 税额采用长版已澄清的含税/未税规则。
- 真实商品图片不是必需项，页面使用自绘中性瓶子 SVG 作为占位图。
- 源数据名称与 SKU 中的规格数字可能不同，例如 AURPUR10 返回的是 15g 商品；严格采用返回名称，不根据 SKU 字符串猜规格。
- SQL 查询入口不是另行评估的数据库 API；按题目许可保存查询快照，后续真实订单可以使用相同输入结构。

## 目录与接口

```text
backend/app/models.py       输入校验与关系约束
backend/app/orders.py       商品匹配、Decimal 计算、运费估算
backend/app/tracking.py     承运商适配、缓存、限流和回退
backend/app/main.py         HTTP 路由及环境配置
backend/data/              题目订单、商品查询快照和来源记录
backend/tests/             计算和异常处理测试
frontend/src/App.vue        订单工作台、导入预览、查询交互
frontend/src/types.ts       前端接口类型
frontend/src/style.css      响应式布局
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 本地服务健康检查 |
| GET | `/api/orders?estimate=false` | 读取题目订单并计算 |
| POST | `/api/orders/preview?estimate=false` | 校验并计算传入订单，不持久化 |
| GET | `/api/shipments/{shipment_id}/tracking` | 查询题目订单的物流，未知 ID 返回 404 |

## Git 与凭证安全

`.env`、虚拟环境、node_modules、构建目录、临时文件及 `材料/` 均被忽略。
仓库仅提交无值的 `.env.example`，不会提交材料中的真实密码。当前只进行本地提交，尚未配置 GitHub 远程仓库。
迁移时保留目标目录已有内容，原工程目录通过 Windows junction 指向新目录，避免当前会话引用断开。

## 官方参考

- [Australia Post Track Items](https://developers.auspost.com.au/content/apis/shipping-and-tracking/reference-track-items.html)
- [Australia Post 测试环境和认证 FAQ](https://developers.auspost.com.au/content/apis/shipping-and-tracking/info/api-resources/faq.html)
- [FastAPI](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Vite](https://vite.dev/guide/)
