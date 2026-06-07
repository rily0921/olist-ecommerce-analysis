"""
Step 3: Python 深度分析
├── 3.1 漏斗分析（订单状态各阶段转化率）
├── 3.2 同期群留存（Cohort Retention Heatmap）
├── 3.3 RFM 用户分层（命名 + 画像 + 运营策略）
└── 3.4 差评根因分析（评分 vs 延迟/运费/价格）

用法: 把下面 MYSQL_PASSWORD 改成你的数据库密码，然后 PyCharm 右键 → Run
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
import numpy as np
import os
from sqlalchemy import create_engine
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings
warnings.filterwarnings('ignore')

# 中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 0. 连接数据库（改成你的 MySQL 密码）
# ============================================================
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "你的密码")
engine = create_engine(
    f"mysql+pymysql://root:{MYSQL_PASSWORD}@localhost:3306/olist?charset=utf8mb4"
)

# ============================================================
# 3.1 漏斗分析
# ============================================================
print("=" * 60)
print("📊 3.1 漏斗分析：订单状态转化率")
print("=" * 60)

funnel = pd.read_sql("""
    SELECT
        order_status,
        COUNT(*) AS order_count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) AS pct
    FROM orders
    GROUP BY order_status
    ORDER BY FIELD(order_status, 'approved','invoiced','processing','shipped','delivered',
                                   'canceled','unavailable')
""", engine)

print(funnel.to_string(index=False))

# 漏斗图
statuses = ['approved', 'shipped', 'delivered']
counts = []
for s in statuses:
    c = funnel[funnel['order_status'] == s]['order_count'].values
    counts.append(c[0] if len(c) > 0 else 0)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 左: 柱状图
bars = axes[0].bar(statuses, counts, color=['#5B9BD5', '#ED7D31', '#70AD47'])
axes[0].set_title('Orders by Status', fontsize=13, fontweight='bold')
axes[0].set_ylabel('Order Count')
for bar, val in zip(bars, counts):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 500,
                 f'{val:,}', ha='center', fontsize=11, fontweight='bold')

# 右: 转化率
conversion_labels = ['approved → shipped', 'shipped → delivered']
conversion_rates = []
for i in range(len(counts)-1):
    rate = counts[i+1] / counts[i] * 100 if counts[i] > 0 else 0
    conversion_rates.append(rate)

bars2 = axes[1].bar(conversion_labels, conversion_rates, color=['#ED7D31', '#70AD47'])
axes[1].set_title('Stage Conversion Rate', fontsize=13, fontweight='bold')
axes[1].set_ylabel('Conversion Rate (%)')
axes[1].set_ylim(0, 105)
for bar, val in zip(bars2, conversion_rates):
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f'{val:.1f}%', ha='center', fontsize=12, fontweight='bold')

plt.tight_layout()
plt.savefig('output_funnel.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 漏斗图已保存: output_funnel.png")
print()

# ============================================================
# 3.2 同期群留存分析
# ============================================================
print("=" * 60)
print("📊 3.2 同期群留存分析：Cohort Retention")
print("=" * 60)

# 取用户-月份明细数据
user_months = pd.read_sql("""
    SELECT DISTINCT
        c.customer_unique_id,
        DATE_FORMAT(o.order_purchase_timestamp, '%%Y-%%m') AS purchase_month
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.order_purchase_timestamp IS NOT NULL
      AND o.order_status IN ('delivered', 'shipped')
""", engine)

# 每个用户的首购月份
user_months['purchase_month'] = pd.to_datetime(user_months['purchase_month'] + '-01')
first_purchase = user_months.groupby('customer_unique_id')['purchase_month'].min().reset_index()
first_purchase.columns = ['customer_unique_id', 'cohort_month']

# 关联首购月份
df = user_months.merge(first_purchase, on='customer_unique_id')

# 计算月份偏移 (首购月 = 0, 次月 = 1, ...)
df['month_offset'] = (
    (df['purchase_month'].dt.year - df['cohort_month'].dt.year) * 12
    + (df['purchase_month'].dt.month - df['cohort_month'].dt.month)
)

# 透视成矩阵: 行=cohort, 列=month_offset
cohort_pivot = df.pivot_table(
    index=df['cohort_month'].dt.strftime('%Y-%m'),
    columns='month_offset',
    values='customer_unique_id',
    aggfunc='nunique'
).fillna(0)

# 筛选有效 cohort
valid_cohorts = [c for c in cohort_pivot.index if c >= '2017-01']
cohort_pivot = cohort_pivot.loc[valid_cohorts]

# 只保留前 12 个月
max_cols = [c for c in cohort_pivot.columns if c <= 12]
cohort_pivot = cohort_pivot[max_cols]

# 转为留存率
cohort_sizes = cohort_pivot[0]  # 第 0 月 = 首购人数
retention = cohort_pivot.divide(cohort_sizes, axis=0) * 100

# 画热力图
fig, ax = plt.subplots(figsize=(16, 6))
sns.heatmap(retention, annot=True, fmt='.1f', cmap='YlOrRd',
            vmin=0, vmax=retention.values.max(),
            linewidths=0.5, ax=ax,
            cbar_kws={'label': 'Retention Rate (%)'})
ax.set_title('Cohort Retention Heatmap (Month 0 = First Purchase)', fontsize=14, fontweight='bold')
ax.set_xlabel('Months Since First Purchase')
ax.set_ylabel('First Purchase Month (Cohort)')
plt.tight_layout()
plt.savefig('output_cohort_retention.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 留存热力图已保存: output_cohort_retention.png")

# 关键数字
total_first_buyers = int(cohort_sizes.sum())
month1_retention = retention[1].mean()
repeat_rate = (1 - total_first_buyers / int(cohort_pivot.values.sum())) * 100
print(f"   首购用户总数: {total_first_buyers:,}")
print(f"   新用户次月(Month 1)平均留存率: {month1_retention:.1f}%")
print(f"   有任何复购行为的用户占比: {repeat_rate:.1f}%")
print(f"   注: Olist 97%+ 为一次性购买用户，留存率极低是正常现象")
print()

# ============================================================
# 3.3 RFM 用户分层
# ============================================================
print("=" * 60)
print("📊 3.3 RFM 用户分层")
print("=" * 60)

rfm = pd.read_sql("""
    SELECT
        c.customer_unique_id AS customer_id,
        DATEDIFF((SELECT MAX(order_purchase_timestamp) FROM orders),
                  MAX(o.order_purchase_timestamp)) AS recency,
        COUNT(DISTINCT o.order_id) AS frequency,
        ROUND(SUM(oi.price), 2) AS monetary
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status IN ('delivered', 'shipped')
    GROUP BY c.customer_unique_id
""", engine)

print(f"   用户总数: {len(rfm):,}")
print(f"   Recency 范围: {rfm['recency'].min()} ~ {rfm['recency'].max()} 天")
print(f"   Frequency 中位数: {rfm['frequency'].median():.0f}")
print(f"   Monetary 中位数: R$ {rfm['monetary'].median():.0f}")

# 肘部法则确定 K
scaler = StandardScaler()
rfm_scaled = scaler.fit_transform(rfm[['recency', 'frequency', 'monetary']])

inertias = []
K_range = range(2, 11)
for k in K_range:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(rfm_scaled)
    inertias.append(km.inertia_)

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(list(K_range), inertias, 'bo-', markersize=8)
ax.set_xlabel('Number of Clusters (K)', fontsize=12)
ax.set_ylabel('Inertia (Within-cluster SSE)', fontsize=12)
ax.set_title('Elbow Method for Optimal K', fontsize=13, fontweight='bold')
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('output_elbow.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 肘部法则图已保存: output_elbow.png")

# KMeans 分 4 群
kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
rfm['segment'] = kmeans.fit_predict(rfm_scaled)

# 每群 RFM 均值
seg_stats = rfm.groupby('segment').agg(
    人数=('customer_id', 'count'),
    平均Recency=('recency', 'mean'),
    平均Frequency=('frequency', 'mean'),
    平均Monetary=('monetary', 'mean'),
    总收入贡献=('monetary', 'sum')
).round(1)
seg_stats['收入占比%'] = (seg_stats['总收入贡献'] / rfm['monetary'].sum() * 100).round(1)
seg_stats['人数占比%'] = (seg_stats['人数'] / len(rfm) * 100).round(1)

# 按 Monetary 排序命名
seg_order = seg_stats.sort_values('平均Monetary', ascending=False)

# 给每群命名
segment_names = {
    seg_order.index[0]: '🏆 高价值核心用户',
    seg_order.index[1]: '📈 潜力成长用户',
    seg_order.index[2]: '⚠️ 流失预警用户',
    seg_order.index[3]: '💤 低价值一次性用户',
}
rfm['segment_name'] = rfm['segment'].map(segment_names)
seg_stats['命名'] = seg_stats.index.map(segment_names)

print()
print(seg_stats[['命名', '人数', '人数占比%', '平均Recency', '平均Frequency',
                  '平均Monetary', '收入占比%']].to_string())

# 每群人太少或太多的检查
print()
print("📋 运营策略建议:")
strategies = {
    '🏆 高价值核心用户': 'VIP 服务 + 新品优先体验 + 推荐返利（拉同类高价值用户）',
    '📈 潜力成长用户': '定向满减券提升频次 + 捆绑推荐提升单价 → 向高价值迁移',
    '⚠️ 流失预警用户': 'Push 召回 + 限时折扣 + 调查为什么不来了（贵？慢？差？）',
    '💤 低价值一次性用户': '降低获客成本优先级，不做高成本触达，观察是否自然升级',
}
for name, strategy in strategies.items():
    count = rfm[rfm['segment_name'] == name].shape[0]
    pct = count / len(rfm) * 100
    print(f"   {name} ({count} 人, {pct:.1f}%): {strategy}")
print()

# 保存分段结果
rfm.to_csv('output_rfm_segments.csv', index=False)
print("→ RFM 分段结果已保存: output_rfm_segments.csv")
print()

# ============================================================
# 3.4 差评根因分析
# ============================================================
print("=" * 60)
print("📊 3.4 差评根因分析")
print("=" * 60)

root_cause = pd.read_sql("""
    SELECT
        r.review_score,
        DATEDIFF(o.order_delivered_customer_date, o.order_estimated_delivery_date) AS delivery_delay,
        oi.price,
        oi.freight_value,
        ROUND(oi.freight_value / NULLIF(oi.price, 0) * 100, 1) AS freight_ratio
    FROM orders o
    JOIN order_reviews r ON o.order_id = r.order_id
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_estimated_delivery_date IS NOT NULL
      AND r.review_score IS NOT NULL
""", engine)

print(f"   有效评价订单: {len(root_cause):,}")

# 四分图: 评分 vs 延迟 + 运费占比
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# 图1: 评分 vs 延迟的箱线图
score_groups = [root_cause[root_cause['review_score'] == s]['delivery_delay'].values
                for s in range(1, 6)]
bp = axes[0].boxplot(score_groups, labels=range(1, 6), patch_artist=True,
                      showfliers=False)
colors = ['#E74C3C', '#E67E22', '#F1C40F', '#2ECC71', '#27AE60']
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
axes[0].axhline(y=0, color='red', linestyle='--', alpha=0.5)
axes[0].set_title('Review Score vs Delivery Delay', fontsize=12, fontweight='bold')
axes[0].set_xlabel('Review Score')
axes[0].set_ylabel('Delivery Delay (days, negative = early)')

# 图2: 评分 vs 运费占比
score_freight = root_cause.groupby('review_score')['freight_ratio'].mean()
axes[1].bar(score_freight.index, score_freight.values,
            color=colors, edgecolor='white', linewidth=1.5)
axes[1].set_title('Review Score vs Freight Ratio', fontsize=12, fontweight='bold')
axes[1].set_xlabel('Review Score')
axes[1].set_ylabel('Avg Freight / Price (%)')
for i, (x, y) in enumerate(zip(score_freight.index, score_freight.values)):
    axes[1].text(x, y + 0.2, f'{y:.1f}%', ha='center', fontweight='bold')

# 图3: 评分 vs 价格
score_price = root_cause.groupby('review_score')['price'].mean()
axes[2].bar(score_price.index, score_price.values,
            color=colors, edgecolor='white', linewidth=1.5)
axes[2].set_title('Review Score vs Average Price', fontsize=12, fontweight='bold')
axes[2].set_xlabel('Review Score')
axes[2].set_ylabel('Avg Price (R$)')
for x, y in zip(score_price.index, score_price.values):
    axes[2].text(x, y + 1, f'{y:.0f}', ha='center', fontweight='bold')

plt.tight_layout()
plt.savefig('output_review_root_cause.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 差评根因图已保存: output_review_root_cause.png")

# 关键统计输出
print()
print("📋 关键统计:")
for s in [1, 5]:
    subset = root_cause[root_cause['review_score'] == s]
    print(f"   评分 {s}: 订单 {len(subset):,}, "
          f"中位延迟 {subset['delivery_delay'].median():.1f} 天, "
          f"平均运费占比 {subset['freight_ratio'].mean():.1f}%, "
          f"平均价格 R$ {subset['price'].mean():.0f}")

# 延迟和运费双高的组合（最差体验）
root_cause['bad_delay'] = root_cause['delivery_delay'] > 0
bad_both = root_cause[(root_cause['bad_delay']) & (root_cause['freight_ratio'] > 30)]
print(f"\n   延迟 + 高运费（>30%）同时出现的订单: {len(bad_both):,} 单")
print(f"   其中差评(≤3)率: {len(bad_both[bad_both['review_score'] <= 3]) / len(bad_both) * 100:.1f}%")

print()
print("=" * 60)
print("✅ Step 3 全部完成！")
print("   产出: 4 张图 + 1 个 CSV")
print("   - output_funnel.png")
print("   - output_cohort_retention.png")
print("   - output_elbow.png")
print("   - output_review_root_cause.png")
print("   - output_rfm_segments.csv")
print("=" * 60)
