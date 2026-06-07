-- ============================================================
-- 备选方案: 如果 LOAD DATA 报错 (secure_file_priv 限制)
-- ============================================================
-- 先查一下 MySQL 允许从哪个目录加载文件:
--   SHOW VARIABLES LIKE 'secure_file_priv';
--
-- 如果返回某个目录 (比如 C:\ProgramData\MySQL\...\):
--   把 9 个 CSV 复制到那个目录，然后把下面路径改成那个目录
--
-- 如果返回空: 恭喜，任何路径都能 LOAD DATA，直接用 01_create_tables.sql
-- 如果返回 NULL: 完全禁止 LOAD DATA，改用下面的 Python 脚本导入
-- ============================================================


-- ============================================================
-- Python 备选导入脚本 (存为 01_import_csv.py，在 PyCharm 运行)
-- 如果 MySQL LOAD DATA 被禁用，用这个脚本通过 pandas + sqlalchemy 导入
-- ============================================================
-- '''
-- import pandas as pd
-- from sqlalchemy import create_engine
-- import os
--
-- # 连接 MySQL (改成你的用户名密码)
-- engine = create_engine('mysql+pymysql://root:你的密码@localhost:3306/olist?charset=utf8mb4')
--
-- data_dir = r'E:\Desktop\实习\找项目\archive'
--
-- tables = {
--     'customers':    'olist_customers_dataset.csv',
--     'products':     'olist_products_dataset.csv',
--     'sellers':      'olist_sellers_dataset.csv',
--     'geolocation':  'olist_geolocation_dataset.csv',
--     'product_category_translation': 'product_category_name_translation.csv',
--     'orders':       'olist_orders_dataset.csv',
--     'order_items':  'olist_order_items_dataset.csv',
--     'order_payments': 'olist_order_payments_dataset.csv',
--     'order_reviews': 'olist_order_reviews_dataset.csv',
-- }
--
-- # 先导入无外键依赖的表，再导入有外键的表
-- for table, filename in tables.items():
--     filepath = os.path.join(data_dir, filename)
--     df = pd.read_csv(filepath)
--     df.to_sql(table, engine, if_exists='append', index=False, chunksize=10000)
--     print(f'✅ {table}: {len(df)} rows imported')
-- '''

-- ============================================================
-- Phase 1: 数据分析 SQL 查询 (6 个核心分析)
-- 在 MySQL Workbench 中逐个执行，每个查询的结果截图保存
-- ============================================================

USE olist;

-- ============================================================
-- 分析 1: 月度 GMV 及环比增长率
-- 业务问题: 收入趋势如何？是否有季节性？增长是否健康？
-- ============================================================
WITH monthly_gmv AS (
    SELECT
        DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS order_month,
        COUNT(DISTINCT o.order_id) AS order_count,
        ROUND(SUM(oi.price), 2) AS gmv,
        ROUND(AVG(oi.price), 2) AS avg_order_value
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status IN ('delivered', 'shipped')
      AND o.order_purchase_timestamp IS NOT NULL
    GROUP BY DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m')
)
SELECT
    order_month,
    order_count,
    gmv,
    avg_order_value,
    ROUND((gmv - LAG(gmv) OVER (ORDER BY order_month))
          / LAG(gmv) OVER (ORDER BY order_month) * 100, 2) AS mom_growth_pct
FROM monthly_gmv
ORDER BY order_month;

-- 解读要点:
-- 1. 2017-11 黑五是否有明显 GMV 峰值？
-- 2. 整体趋势是上升还是持平？
-- 3. 客单价和订单量哪个是 GMV 增长的主驱动？


-- ============================================================
-- 分析 2: 各州销售额排名及全国占比
-- 业务问题: 哪些区域是核心市场？哪些有增长潜力？
-- ============================================================
SELECT
    c.customer_state,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT c.customer_unique_id) AS customer_count,
    ROUND(SUM(oi.price), 2) AS total_revenue,
    ROUND(SUM(oi.price) / (SELECT SUM(price) FROM order_items oi2
        JOIN orders o2 ON oi2.order_id = o2.order_id
        WHERE o2.order_status IN ('delivered', 'shipped')) * 100, 2) AS pct_of_total,
    ROUND(AVG(oi.price), 2) AS avg_order_value,
    ROUND(SUM(oi.price) / COUNT(DISTINCT c.customer_unique_id), 2) AS revenue_per_customer
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status IN ('delivered', 'shipped')
GROUP BY c.customer_state
ORDER BY total_revenue DESC;

-- 解读要点:
-- 1. SP（圣保罗）是否占绝对主导？前5州贡献了多少%？
-- 2. 人均消费和客单价在州之间有差异吗？
-- 3. 哪些州是"订单多但人均低"（走量市场）vs "订单少但人均高"（高端市场）？


-- ============================================================
-- 分析 3: 品类销售额 TOP10 + 客单价
-- 业务问题: 哪些品类是收入引擎？各品类的客单价和销量特征？
-- ============================================================
SELECT
    pt.product_category_name_english AS category,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT oi.product_id) AS product_variety,
    ROUND(SUM(oi.price), 2) AS total_revenue,
    ROUND(SUM(oi.price) / (SELECT SUM(price) FROM order_items oi2
        JOIN orders o2 ON oi2.order_id = o2.order_id
        WHERE o2.order_status IN ('delivered', 'shipped')) * 100, 2) AS revenue_pct,
    ROUND(AVG(oi.price), 2) AS avg_unit_price,
    ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS revenue_per_order
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name
WHERE o.order_status IN ('delivered', 'shipped')
GROUP BY pt.product_category_name_english
ORDER BY total_revenue DESC
LIMIT 10;

-- 解读要点:
-- 1. 头部品类集中度：TOP3/Top5/Top10 各贡献了多少%收入？
-- 2. 高单价品类（如电子产品）vs 高频品类（如日用品）的策略差异
-- 3. product_variety 和 revenue 的关系：品类丰富度是否驱动收入？


-- ============================================================
-- 分析 4: 支付方式分布 + 分期偏好
-- 业务问题: 用户偏好什么支付方式？分期对客单价的拉升效果？
-- ============================================================
-- 4a: 支付方式概览
SELECT
    payment_type,
    COUNT(*) AS transaction_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM order_payments), 2) AS pct,
    ROUND(AVG(payment_value), 2) AS avg_payment_value,
    ROUND(SUM(payment_value), 2) AS total_payment_value,
    ROUND(AVG(payment_installments), 2) AS avg_installments
FROM order_payments
GROUP BY payment_type
ORDER BY total_payment_value DESC;

-- 4b: 分期行为分析 (只看信用卡)
SELECT
    CASE
        WHEN payment_installments = 1 THEN '1期(一次性)'
        WHEN payment_installments BETWEEN 2 AND 3 THEN '2-3期'
        WHEN payment_installments BETWEEN 4 AND 6 THEN '4-6期'
        WHEN payment_installments BETWEEN 7 AND 12 THEN '7-12期'
        ELSE '12期+'
    END AS installment_range,
    COUNT(*) AS order_count,
    ROUND(AVG(payment_value), 2) AS avg_order_value,
    ROUND(SUM(payment_value), 2) AS total_value
FROM order_payments
WHERE payment_type = 'credit_card'
GROUP BY installment_range
ORDER BY MIN(payment_installments);

-- 解读要点:
-- 1. 信用卡占比是否超 70%？Boleto（巴西本地支付）排第几？
-- 2. 分期数越多，客单价是否显著上升？（验证分期对消费的刺激效果）
-- 3. 借记卡和 voucher 的客单价是否明显偏低？


-- ============================================================
-- 分析 5: 发货时效 SLA 达标率
-- 业务问题: 物流是否按时送达？哪些州是物流重灾区？
-- ============================================================
SELECT
    c.customer_state,
    COUNT(*) AS delivered_orders,
    ROUND(AVG(DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp)), 1) AS avg_delivery_days,
    ROUND(AVG(DATEDIFF(o.order_estimated_delivery_date, o.order_purchase_timestamp)), 1) AS avg_estimated_days,
    ROUND(AVG(DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date)), 1) AS avg_delay_days,
    SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN 1 ELSE 0 END) AS delayed_orders,
    ROUND(SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS delay_rate_pct,
    ROUND(AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date)
        ELSE 0 END), 1) AS avg_positive_delay_days
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY c.customer_state
ORDER BY delay_rate_pct DESC;

-- 解读要点:
-- 1. 整体延迟率是多少？哪些州延迟率 > 50%？
-- 2. 延迟最严重的州平均晚多少天？
-- 3. 是否存在"承诺时间过短导致延迟"的情况（avg_estimated_days 很短的州延迟率高）？
-- 4. 物流改善的优先级排序：先解决延迟率最高的州


-- ============================================================
-- 分析 6: 差评率按品类排名 + 与发货延迟的相关性
-- 业务问题: 哪些品类差评最多？差评和延迟发货关系多大？
-- ============================================================
-- 6a: 品类差评率排名
SELECT
    pt.product_category_name_english AS category,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(CASE WHEN r.review_score <= 3 THEN 1 ELSE 0 END) AS low_rating_orders,
    ROUND(SUM(CASE WHEN r.review_score <= 3 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS low_rating_rate_pct,
    ROUND(AVG(r.review_score), 2) AS avg_review_score,
    ROUND(AVG(oi.price), 2) AS avg_price,
    ROUND(AVG(oi.freight_value), 2) AS avg_freight,
    ROUND(AVG(DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date)), 1) AS avg_delivery_delay
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name
JOIN order_reviews r ON o.order_id = r.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND r.review_score IS NOT NULL
GROUP BY pt.product_category_name_english
HAVING COUNT(*) >= 50  -- 过滤样本太小的品类
ORDER BY low_rating_rate_pct DESC
LIMIT 15;

-- 6b: 评分 vs 发货延迟的统计关系
SELECT
    r.review_score,
    COUNT(*) AS order_count,
    ROUND(AVG(DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date)), 1) AS avg_delivery_delay,
    ROUND(AVG(oi.price), 2) AS avg_price,
    ROUND(AVG(oi.freight_value), 2) AS avg_freight,
    ROUND(AVG(oi.freight_value / NULLIF(oi.price, 0)) * 100, 1) AS freight_ratio_pct
FROM orders o
JOIN order_reviews r ON o.order_id = r.order_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY r.review_score
ORDER BY r.review_score;

-- 解读要点:
-- 1. 哪 3 个品类差评率最高？它们的共同特征是什么（贵？运费高？延迟长？）
-- 2. 评分和延迟天数是否呈明显负相关？（1分的订单延迟最严重？5分的几乎不延迟？）
-- 3. 运费占比（freight_ratio）和评分的关系：高运费是否拉低评分？
-- 4. 核心洞察：到底是"商品不好"还是"物流不行"导致的差评？


-- ============================================================
-- 补充分析: 数据质量检查 (做分析前跑一遍，心里有数)
-- ============================================================

-- 检查 order_status 分布
SELECT order_status, COUNT(*) AS cnt,
       ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM orders),2) AS pct
FROM orders GROUP BY order_status ORDER BY cnt DESC;
-- 预期: delivered 占绝大多数 (97%+)

-- 检查时间范围
SELECT
    MIN(order_purchase_timestamp) AS earliest_order,
    MAX(order_purchase_timestamp) AS latest_order,
    DATEDIFF(MAX(order_purchase_timestamp), MIN(order_purchase_timestamp)) AS days_span
FROM orders
WHERE order_purchase_timestamp IS NOT NULL;
-- 预期: 2016-09 到 2018-10，约 25 个月

-- 检查订单重复支付 (1个订单多次支付)
SELECT
    payment_count_per_order,
    COUNT(*) AS order_count
FROM (
    SELECT order_id, COUNT(*) AS payment_count_per_order
    FROM order_payments GROUP BY order_id
) t
GROUP BY payment_count_per_order
ORDER BY payment_count_per_order;
-- 预期: 绝大多数是 1 次支付，少量分期拆成多笔
