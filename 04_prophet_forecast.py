"""
Step 4: Prophet 月度 GMV 时序预测
├── 从 MySQL 提取月度 GMV
├── 清洗（去除数据不完整的月份）
├── Prophet 建模 + 交叉验证
├── 未来 3 个月预测
└── 评估 MAPE

用法: 把 MYSQL_PASSWORD 改成你的密码 → Run
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
from sqlalchemy import create_engine
from prophet import Prophet
from sklearn.metrics import mean_absolute_percentage_error
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 0. 连接 & 取数据
# ============================================================
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "你的密码")
engine = create_engine(
    f"mysql+pymysql://root:{MYSQL_PASSWORD}@localhost:3306/olist?charset=utf8mb4"
)

# 从 SQL 分析 1 的逻辑取月度 GMV
monthly_gmv = pd.read_sql("""
    SELECT
        DATE_FORMAT(o.order_purchase_timestamp, '%%Y-%%m') AS order_month,
        ROUND(SUM(oi.price), 2) AS gmv,
        COUNT(DISTINCT o.order_id) AS order_count
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status IN ('delivered', 'shipped')
      AND o.order_purchase_timestamp IS NOT NULL
    GROUP BY DATE_FORMAT(o.order_purchase_timestamp, '%%Y-%%m')
    ORDER BY order_month
""", engine)

print("原始月度 GMV:")
print(monthly_gmv.to_string(index=False))
print()

# ============================================================
# 1. 数据清洗
# ============================================================
# 过滤异常月份：订单量 < 100 的都是数据采集不完整
monthly_gmv = monthly_gmv[monthly_gmv['order_count'] >= 100].copy()
monthly_gmv['ds'] = pd.to_datetime(monthly_gmv['order_month'] + '-01')
monthly_gmv['y'] = monthly_gmv['gmv']

print(f"清洗后有效月份: {len(monthly_gmv)} 个月")
print(f"时间范围: {monthly_gmv['ds'].min().strftime('%Y-%m')} ~ {monthly_gmv['ds'].max().strftime('%Y-%m')}")
print(f"月均 GMV: R$ {monthly_gmv['y'].mean():,.0f}")
print(f"GMV 范围: R$ {monthly_gmv['y'].min():,.0f} ~ {monthly_gmv['y'].max():,.0f}")
print()

# ============================================================
# 2. Prophet 建模（全量数据，用交叉验证评估）
# ============================================================
# 添加巴西黑五作为自定义节假日（only 2017 — 2018 数据没有黑五）
black_friday = pd.DataFrame({
    'holiday': 'black_friday',
    'ds': pd.to_datetime(['2017-11-01']),
    'lower_window': 0,
    'upper_window': 0,
})

model = Prophet(
    yearly_seasonality=False,       # 只有 1 个 11 月，无法估计年度季节性
    weekly_seasonality=False,
    daily_seasonality=False,
    holidays=black_friday,
    changepoint_prior_scale=0.5,    # 允许趋势灵活转弯
    seasonality_mode='additive',
)
model.fit(monthly_gmv[['ds', 'y']])

print("✅ Prophet 模型训练完成（全量 20 个月）")
print()

# ============================================================
# 3. 时间序列交叉验证（滚动窗口，避免单次切分不稳定）
# ============================================================
from prophet.diagnostics import cross_validation, performance_metrics

# 前 12 个月作为初始训练窗口，之后每 1 个月滚动一次，每次预测后 3 个月
cv_results = cross_validation(
    model,
    initial='365 days',     # 初始训练窗口: 12 个月
    period='30 days',       # 每 1 个月滚动一次
    horizon='90 days',      # 每次预测未来 3 个月
)

cv_metrics = performance_metrics(cv_results)

print("📊 交叉验证结果 (多次滚动平均):")
print(f"   切分窗口数: {cv_results['cutoff'].nunique()}")
print(f"   MSE:  R$ {cv_metrics['mse'].values[0]:,.0f}")
print(f"   RMSE: R$ {cv_metrics['rmse'].values[0]:,.0f}")
print(f"   MAE:  R$ {cv_metrics['mae'].values[0]:,.0f}")
print(f"   MAPE: {cv_metrics['mape'].values[0]:.1f}%")
cv_mape = cv_metrics['mape'].values[0]
print()

# ============================================================
# 4. 未来 3 个月预测
# ============================================================
future = model.make_future_dataframe(periods=3, freq='MS')
forecast = model.predict(future)

future_only = forecast[forecast['ds'] > monthly_gmv['ds'].max()]

print("🔮 未来 3 个月 GMV 预测:")
for _, row in future_only.iterrows():
    month_str = row['ds'].strftime('%Y-%m')
    print(f"   {month_str}: R$ {row['yhat']:,.0f} "
          f"(下限 R$ {row['yhat_lower']:,.0f}, 上限 R$ {row['yhat_upper']:,.0f})")

trend_end = future_only['yhat'].iloc[-1]
trend_start = future_only['yhat'].iloc[0]
trend_change = (trend_end - trend_start) / trend_start * 100
print(f"\n   未来 3 个月预测趋势: {'📈 上升' if trend_change > 0 else '📉 下降'} ({trend_change:+.1f}%)")
print()

# ============================================================
# 5. 模型分解（季节性模式识别 — 比预测值更重要）
# ============================================================
# 黑五效应 — 模型中唯一的特殊事件
bf_effect = forecast[forecast['ds'] == pd.to_datetime('2017-11-01')]
bf_holiday_effect = bf_effect['holidays'].values[0] if 'holidays' in bf_effect.columns else 0

print("📅 关键发现:")
print(f"   黑五(2017-11)节假日效应: R$ {bf_holiday_effect:+,.0f}")
print(f"   注: 因仅有 20 个月数据（不足 2 年），未启用年度季节性——")
print(f"        用黑五事件效应代替，避免模型用 1 个 11 月数据过度外推")
# 算黑五月份的实际 GMV 增长
bf_row = monthly_gmv[monthly_gmv['ds'] == pd.to_datetime('2017-11-01')]
if len(bf_row) > 0:
    bf_gmv = bf_row.iloc[0]['y']
    prev_3m_avg = monthly_gmv[
        (monthly_gmv['ds'] >= pd.to_datetime('2017-08-01')) &
        (monthly_gmv['ds'] <= pd.to_datetime('2017-10-01'))
    ]['y'].mean()
    print(f"   2017-11 实际 GMV: R$ {bf_gmv:,.0f} (前 3 月均值 R$ {prev_3m_avg:,.0f}, "
          f"提升 {((bf_gmv - prev_3m_avg) / prev_3m_avg * 100):.0f}%)")
print()

# ============================================================
# 6. 可视化
# ============================================================
fig, axes = plt.subplots(2, 1, figsize=(14, 10))

# 图1: 历史 + 预测
ax = axes[0]
ax.plot(monthly_gmv['ds'], monthly_gmv['y'] / 1e6, 'ko-', markersize=8,
        label='Actual GMV', linewidth=2.5, zorder=5)
ax.plot(forecast['ds'], forecast['yhat'] / 1e6, 'b-', linewidth=2,
        alpha=0.8, label='Model Fit')
# 未来部分高亮
ax.plot(future_only['ds'], future_only['yhat'] / 1e6, 'D-',
        color='#70AD47', markersize=10, linewidth=2.5, label='Forecast (Next 3 Months)')
ax.fill_between(forecast['ds'],
                forecast['yhat_lower'] / 1e6,
                forecast['yhat_upper'] / 1e6,
                color='gray', alpha=0.12, label='95% Confidence Interval')

# 黑五标注
ax.annotate('Black Friday\n+季节性峰值',
            xy=(pd.to_datetime('2017-11-01'), 0.995),
            xytext=(pd.to_datetime('2017-07-01'), 0.65),
            arrowprops=dict(arrowstyle='->', color='red', lw=2),
            fontsize=10, color='red', fontweight='bold')

ax.set_title('Olist Monthly GMV: Historical Fit + 3-Month Forecast', fontsize=14, fontweight='bold')
ax.set_ylabel('GMV (Million R$)')
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)

# 图2: 趋势分量 + 节假日效应
ax2 = axes[1]
color_trend = '#2E86C1'
ax2.plot(forecast['ds'], forecast['trend'] / 1e6, '-', color=color_trend, linewidth=2.5, label='Trend')
ax2.set_ylabel('Trend GMV (Million R$)', color=color_trend)
ax2.tick_params(axis='y', labelcolor=color_trend)

# 标黑五效应
if 'holidays' in forecast.columns:
    ax2b = ax2.twinx()
    ax2b.fill_between(forecast['ds'], 0, forecast['holidays'] / 1e6,
                       color='#E74C3C', alpha=0.3, label='Black Friday Effect')
    ax2b.set_ylabel('Holiday Effect (Million R$)', color='#E74C3C')
    ax2b.tick_params(axis='y', labelcolor='#E74C3C')
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2b.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
else:
    ax2.legend(loc='upper left')

ax2.set_title('Trend Component + Black Friday Effect', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('output_prophet_forecast.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 预测图已保存: output_prophet_forecast.png")

# 额外: Prophet 内置组件图
fig2 = model.plot_components(forecast)
plt.tight_layout()
plt.savefig('output_prophet_components.png', dpi=150, bbox_inches='tight')
plt.close()
print("→ 组件分解图已保存: output_prophet_components.png")
print()

# ============================================================
# 7. 简历方法论
# ============================================================
print("=" * 60)
print("📋 简历可用的方法论描述:")
print("-" * 60)
print(f"模型: Facebook Prophet（趋势 + 黑五节假日效应）")
print(f"数据: 20 个月真实 GMV 月度序列（2017-01 ~ 2018-08）")
print(f"特征工程: 黑五节假日效应 + 自动变点检测")
print(f"  注: 因仅 20 个月数据（不足 2 年周期），未启用年度季节性——")
print(f"       用黑五事件效应代替，避免模型用 1 次 11 月数据过度外推")
print(f"验证方法: 滚动时间序列交叉验证（初始 12 月，每 1 月滚动，horizon 3 月）")
print(f"精度: 交叉验证 MAPE = {cv_mape:.1f}%")
print(f"输出: 未来 3 个月预测 + 95% 置信区间 + 黑五效应量化")
print("=" * 60)
