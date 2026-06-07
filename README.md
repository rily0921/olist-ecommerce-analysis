# Olist 巴西电商经营分析

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-orange)](https://www.mysql.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red)](https://streamlit.io/)
[![Prophet](https://img.shields.io/badge/Prophet-Facebook-blue)](https://facebook.github.io/prophet/)

基于 **Olist 巴西电商 10 万条真实订单数据**的端到端经营分析项目。以数据分析师（而非算法工程师）的视角，回答一个核心商业问题：**"这个平台的增长应该往哪走？"**

## 项目概览

| 维度 | 内容 |
|------|------|
| 数据来源 | [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle) |
| 数据规模 | 9 张表、~10 万订单、~100 万条地理数据 |
| 分析框架 | MySQL 数据基建 -> SQL 业务分析 -> Python 深度分析 -> Prophet 时序预测 -> Streamlit 看板 |
| 核心发现 | 0.5% 次月留存、物流体验驱动差评、2.4% 大额客户贡献 19% 收入 |

## 快速开始

### 1. 环境要求

- Python 3.11+
- MySQL 8.0+
- 下载 [Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 并解压到 `archive/` 目录

### 2. 安装依赖

```bash
pip install streamlit pandas matplotlib sqlalchemy pymysql prophet scikit-learn
```

### 3. 导入数据

设置 MySQL 密码环境变量：

```bash
# Windows PowerShell
$env:MYSQL_PASSWORD = "你的MySQL密码"

# Linux/Mac
export MYSQL_PASSWORD="你的MySQL密码"
```

在 MySQL Workbench 中打开 `01_import_data.sql`，逐段执行建库、建表、导入 CSV、建索引。

### 4. 运行分析

```bash
# SQL 分析（MySQL Workbench 中执行）
02_analysis_queries.sql

# Python 深度分析
python 03_python_analysis.py

# 时序预测
python 04_prophet_forecast.py

# 启动交互看板
streamlit run 05_dashboard.py
```

## 项目结构

```
├── 01_import_data.sql          # MySQL 建表 + 导入 + 索引
├── 02_analysis_queries.sql     # 6 个 SQL 分析查询（含商业解读注释）
├── 03_python_analysis.py       # Python 深度分析（漏斗、留存、RFM、差评根因）
├── 04_prophet_forecast.py      # Prophet 月度 GMV 预测
├── 05_dashboard.py             # Streamlit 交互看板 + 智能助手
├── faq_data.json               # 智能助手 FAQ 知识库
├── STEP3_深度分析总结.md        # Step 3 分析结论
├── STEP4_时序预测总结.md        # Step 4 建模说明
└── README.md
```

## 分析架构

```
Step 1: 数据基建 (MySQL)
  └── 9 张表建库 + LOAD DATA 导入 + 索引优化

Step 2: SQL 业务分析 (6 个查询)
  ├── 月度 GMV 及环比增长率
  ├── 各州销售额排名 + 全国占比
  ├── 品类销售额 TOP10 + SKU 效率
  ├── 支付方式 + 分期偏好
  ├── 发货时效 SLA 达标率
  └── 差评率排名 + 评分 vs 延迟相关性

Step 3: Python 深度分析
  ├── 漏斗分析：订单状态转化率
  ├── 同期群留存：Cohort Retention 热力图
  ├── RFM 用户分层：4 群命名 + 运营策略
  └── 差评根因：评分 vs 延迟/运费/价格三因子分析

Step 4: Prophet 时序预测
  ├── 趋势 + 黑五节假日效应建模
  ├── 滚动时间序列交叉验证
  └── 未来 3 个月 GMV 预测 + 季节性模式识别

Step 5: Streamlit 看板 + 智能助手
  ├── Tab 1: 完整分析报告（叙事型，6 个 Section）
  ├── Tab 2: 自主数据探索（动态筛选 + 实时图表）
  └── 侧边栏: FAQ + Claude API 智能问答
```

## 核心洞察

| 发现 | 数据 | 业务含义 |
|------|:---:|------|
| 用户几乎不回来 | 次月留存 **0.5%** | 低频品类平台的增长应聚焦拉新效率 + 首单价值最大化 |
| 差评不是质量问题 | 价格与评分无关，运费+物流驱动差评 | "双杀"订单（延迟+高运费）差评率 **75.2%** |
| 大额客户被忽视 | 2.4% 用户贡献 **19%** 收入 | 2,229 人首单后 7 天定向触达，性价比远超群发 |
| 分期 = 客单价杠杆 | 分 12 期消费是一次付清的 **3.5 倍** | 商品页默认展示分期每期金额可拉升客单价 |

## 技术栈

MySQL + Python (Pandas, Matplotlib, Seaborn, Scikit-learn, Prophet) + Streamlit + Claude API

## License

MIT — 仅供学习与面试展示使用
