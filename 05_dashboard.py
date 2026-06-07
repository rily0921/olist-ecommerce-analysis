"""
Olist 巴西电商经营分析看板
- Tab 1: 完整分析报告（只读，叙事型）
- Tab 2: 自主数据探索（筛选 + 动态图表）
- 侧边栏: 智能分析助手
运行: streamlit run 05_dashboard.py
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from sqlalchemy import create_engine, text
from prophet import Prophet
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import json, os, warnings
warnings.filterwarnings('ignore')

# ============================================================
# Fonts & Config
# ============================================================
FONT_PATH = 'C:/Windows/Fonts/simhei.ttf'
FONT_CN = fm.FontProperties(fname=FONT_PATH, size=11)
FONT_CN_TITLE = fm.FontProperties(fname=FONT_PATH, size=15)
FONT_CN_SM = fm.FontProperties(fname=FONT_PATH, size=9)
FONT_CN_BIG = fm.FontProperties(fname=FONT_PATH, size=13)
FONT_CN_XL = fm.FontProperties(fname=FONT_PATH, size=18)

plt.rcParams.update({
    'font.size': 11, 'axes.titlesize': 14, 'axes.labelsize': 11,
    'xtick.labelsize': 9, 'ytick.labelsize': 9, 'legend.fontsize': 9,
    'figure.facecolor': 'white', 'axes.facecolor': '#FAFAFA',
    'axes.edgecolor': '#E0E0E0', 'axes.grid': True,
    'grid.alpha': 0.4, 'grid.color': '#E0E0E0',
})

C_BLUE = '#1a5276'; C_RED = '#C0392B'; C_GREEN = '#1E8449'
C_ORANGE = '#D68910'; C_GRAY = '#7F8C8D'; C_LIGHT_BLUE = '#AED6F1'

st.set_page_config(page_title="Olist 电商经营分析", layout="wide")

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
.report-title{font-size:2.6rem;font-weight:800;margin-bottom:0.2rem;letter-spacing:-0.5px;color:#1a1a1a}
.report-subtitle{color:#888;font-size:0.95rem;margin-bottom:2rem}
.section-title{font-size:1.5rem;font-weight:700;margin:1.2rem 0 0.8rem 0;color:#1a1a1a;border-bottom:3px solid #2471A3;padding-bottom:0.4rem}
.insight-box{background:#F4F6F6;border-left:4px solid #2471A3;padding:1rem 1.2rem;margin:0.8rem 0;border-radius:4px;font-size:0.95rem;line-height:1.8;color:#2C3E50}
.highlight-box{background:#FEF9E7;border-left:4px solid #D68910;padding:1rem 1.2rem;margin:0.8rem 0;border-radius:4px;font-size:0.95rem;line-height:1.8;color:#2C3E50}
.metric-card{background:white;border:1px solid #E8E8E8;border-radius:10px;padding:1.4rem 1rem;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.chat-msg-user{background:#EBF5FB;padding:0.7rem 1rem;border-radius:12px;margin:0.4rem 0;font-size:0.9rem}
.chat-msg-bot{background:#F4F6F6;padding:0.7rem 1rem;border-radius:12px;margin:0.4rem 0;font-size:0.9rem;line-height:1.6}
div[data-testid="stTabs"] button {font-size:1.05rem;font-weight:600;}
</style>
""", unsafe_allow_html=True)

# ============================================================
# Database
# ============================================================
@st.cache_resource
def get_engine():
    return create_engine(f"mysql+pymysql://root:{os.environ.get('MYSQL_PASSWORD', '')}@localhost:3306/olist?charset=utf8mb4")
engine = get_engine()

# ---- 全量缓存数据（报告 Tab 用） ----
@st.cache_data(ttl=3600)
def load_report_data():
    gmv = pd.read_sql("""
        SELECT DATE_FORMAT(o.order_purchase_timestamp,'%%Y-%%m') AS month,
               ROUND(SUM(oi.price),2) AS gmv, COUNT(DISTINCT o.order_id) AS orders
        FROM orders o JOIN order_items oi ON o.order_id=oi.order_id
        WHERE o.order_status IN('delivered','shipped') AND o.order_purchase_timestamp IS NOT NULL
        GROUP BY month HAVING COUNT(DISTINCT o.order_id)>=100 ORDER BY month
    """, engine)

    state = pd.read_sql("""
        SELECT c.customer_state, COUNT(DISTINCT o.order_id) AS orders,
               ROUND(SUM(oi.price),2) AS revenue,
               ROUND(SUM(oi.price)*100.0/(SELECT SUM(price) FROM order_items oi2
                JOIN orders o2 ON oi2.order_id=o2.order_id
                WHERE o2.order_status IN('delivered','shipped')),2) AS pct
        FROM orders o JOIN customers c ON o.customer_id=c.customer_id
        JOIN order_items oi ON o.order_id=oi.order_id
        WHERE o.order_status IN('delivered','shipped')
        GROUP BY c.customer_state ORDER BY revenue DESC
    """, engine)

    cat = pd.read_sql("""
        SELECT pt.product_category_name_english AS cat,
               COUNT(DISTINCT o.order_id) AS orders, COUNT(DISTINCT oi.product_id) AS skus,
               ROUND(SUM(oi.price),2) AS revenue, ROUND(AVG(oi.price),2) AS avg_price
        FROM orders o JOIN order_items oi ON o.order_id=oi.order_id
        JOIN products p ON oi.product_id=p.product_id
        JOIN product_category_translation pt ON p.product_category_name=pt.product_category_name
        WHERE o.order_status IN('delivered','shipped')
        GROUP BY pt.product_category_name_english ORDER BY revenue DESC
    """, engine)

    delivery = pd.read_sql("""
        SELECT c.customer_state, COUNT(*) AS orders,
               ROUND(SUM(CASE WHEN order_delivered_customer_date>order_estimated_delivery_date
                THEN 1 ELSE 0 END)*100.0/COUNT(*),2) AS delay_rate
        FROM orders o JOIN customers c ON o.customer_id=c.customer_id
        WHERE o.order_status='delivered' AND o.order_delivered_customer_date IS NOT NULL
          AND o.order_estimated_delivery_date IS NOT NULL
        GROUP BY c.customer_state HAVING COUNT(*)>=30 ORDER BY delay_rate DESC
    """, engine)

    rfm = pd.read_sql("""
        SELECT c.customer_unique_id,
               DATEDIFF('2018-10-17',MAX(o.order_purchase_timestamp)) AS recency,
               COUNT(DISTINCT o.order_id) AS frequency,
               ROUND(SUM(oi.price),2) AS monetary
        FROM orders o JOIN customers c ON o.customer_id=c.customer_id
        JOIN order_items oi ON o.order_id=oi.order_id
        WHERE o.order_status IN('delivered','shipped')
        GROUP BY c.customer_unique_id
    """, engine)

    inst = pd.read_sql("""
        SELECT CASE WHEN payment_installments=1 THEN '一次性付清'
                     WHEN payment_installments BETWEEN 2 AND 3 THEN '分 2-3 期'
                     WHEN payment_installments BETWEEN 4 AND 6 THEN '分 4-6 期'
                     WHEN payment_installments BETWEEN 7 AND 12 THEN '分 7-12 期'
                     ELSE '分 12 期以上' END AS r,
               COUNT(*) AS n, ROUND(AVG(payment_value),2) AS v
        FROM order_payments WHERE payment_type='credit_card'
        GROUP BY r ORDER BY MIN(payment_installments)
    """, engine)

    return gmv, state, cat, delivery, rfm, inst

gmv, state, cat, delivery, rfm, inst = load_report_data()
all_states = state['customer_state'].tolist()
all_cats = cat['cat'].tolist()
all_months = gmv['month'].tolist()

# Load FAQ
SRC = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SRC, 'faq_data.json'), 'r', encoding='utf-8') as f:
    FAQ = json.load(f)

def save_and_show(fig):
    fig.tight_layout(pad=2.5, rect=(0, 0, 1, 0.94))
    st.pyplot(fig)
    plt.close(fig)

def faq_answer(q):
    for kw, ans in FAQ.items():
        if kw in q: return ans
    return None

# ============================================================
# Sidebar: 智能助手（全局）
# ============================================================
with st.sidebar:
    st.markdown("## 分析助手")
    st.caption("问我任何数据相关的问题")

    cols = st.columns(2)
    faq_labels = ["黑五是什么？", "GMV 怎么算？", "RFM 是什么？", "复购为什么低？"]
    for i, q in enumerate(faq_labels):
        if cols[i % 2].button(q, key=f"faq_{i}", use_container_width=True):
            st.session_state['chat_q'] = q

    user_q = st.text_input("输入问题", key="ci", placeholder="比如：圣保罗为什么延迟率低？")
    if user_q: st.session_state['chat_q'] = user_q

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = st.text_input("Anthropic API Key（可选）", type="password", key="ak")
    use_claude = bool(api_key)
    if not use_claude:
        st.caption("输入 API Key 解锁 Claude 智能分析")
    st.markdown("---")
    st.caption("两个 Tab：报告阅读 | 自主探索")

# ---- 处理聊天 ----
if 'chat_q' in st.session_state and st.session_state['chat_q']:
    q = st.session_state['chat_q']
    with st.sidebar:
        st.markdown(f'<div class="chat-msg-user"> {q}</div>', unsafe_allow_html=True)
        ans = faq_answer(q)
        src = "FAQ"
        if ans is None and use_claude:
            with st.spinner("分析中..."):
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key)
                    schema = ("Olist 巴西电商数据库9张表：orders, customers, order_items, "
                              "order_payments, order_reviews, products, sellers, geolocation, "
                              "product_category_translation。orders通过customer_id连customers，"
                              "通过order_id连order_items/payments/reviews。")
                    summary = ("总订单99,441，97%签收。97.6%用户只买一次，次月留存0.5%。"
                               "SP贡献38%收入。信用卡占74%。运费+延迟->差评率75.2%。"
                               "2.4%大额客户贡献19%收入。")
                    resp = client.messages.create(
                        model="claude-haiku-4-5-20251001", max_tokens=400,
                        system=f"{schema}\n\n{summary}",
                        messages=[{"role":"user","content":f"你是Olist数据分析助手。用中文回答，200字内，基于数据事实。问题：{q}"}])
                    ans = resp.content[0].text
                    src = "Claude"
                except Exception as e:
                    ans = f"API调用失败: {str(e)[:80]}。FAQ模式仍可用。"
        if ans is None:
            ans = ("抱歉，我暂时无法回答。\n\n试试问：黑五是什么？/ 为什么复购低？"
                   "/ 差评的原因？/ 圣保罗有什么特别？\n\n输入 API Key 可解锁 Claude 智能分析。")
        st.markdown(f'<div class="chat-msg-bot"> {ans}</div>', unsafe_allow_html=True)
        st.caption(f"来源：{src}")
    del st.session_state['chat_q']

# ============================================================
# 两个 Tab
# ============================================================
tab_report, tab_explore = st.tabs(["分析报告", "自主探索"])

# ====================================================================
# TAB 1: 完整分析报告（只读，叙事型）
# ====================================================================
with tab_report:
    st.markdown('<p class="report-title">Olist 巴西电商经营分析报告</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="report-subtitle">数据：Brazilian E-Commerce by Olist (Kaggle) '
        '~10万订单  2016-2018  MySQL + Python + Prophet + Streamlit + Claude</p>',
        unsafe_allow_html=True)

    with st.expander("名词解释（点击展开）", expanded=False):
        c1, c2 = st.columns(2)
        c1.markdown("**GMV**：商品交易总额（不含运费）。\n\n**环比**：比上月涨跌%。\n\n"
                    "**客单价**：平均每笔订单金额。\n\n**SKU**：商品品种数。\n\n"
                    "**BRL(R$)**：巴西雷亚尔，1 BRL ~ 1.3 RMB。")
        c2.markdown("**RFM**：Recency+Frequency+Monetary。\n\n"
                    "**同期群留存**：按首购月份分组追踪复购。\n\n"
                    "**黑五**：11月购物节，类似双11。\n\n"
                    "**SLA**：物流准时率。")

    # -- S1: Growth --
    st.markdown('<p class="section-title">一、平台在增长吗？</p>', unsafe_allow_html=True)
    col1, col2 = st.columns([2, 1])
    with col1:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        xs = range(len(gmv)); vals = gmv['gmv'] / 1e6
        ax.plot(xs, vals, 'o-', color=C_BLUE, markersize=7, linewidth=2.2, zorder=5)
        ax.fill_between(xs, 0, vals, alpha=0.06, color=C_BLUE)
        bf_i = gmv[gmv['month'] == '2017-11'].index[0]
        ax.annotate('2017-11 黑五\nR$0.99M', (bf_i, vals[bf_i]),
                    xytext=(bf_i - 3, vals[bf_i] + 0.15),
                    arrowprops=dict(arrowstyle='->', color=C_RED, lw=1.5),
                    fontsize=9, color=C_RED, fontweight='bold', ha='center',
                    fontproperties=FONT_CN_SM)
        ax.set_ylabel('GMV（百万 BRL）', fontproperties=FONT_CN)
        ax.set_ylim(0, vals.max() * 1.25); ax.set_xticks([])
        ax.set_title('月度 GMV 趋势', fontweight='bold', fontproperties=FONT_CN_TITLE, pad=14)
        save_and_show(fig)
    with col2:
        h1 = gmv.iloc[:len(gmv)//2]['gmv'].mean()
        h2 = gmv.iloc[len(gmv)//2:]['gmv'].mean()
        st.metric("前期月均 GMV", f"R$ {h1:,.0f}")
        st.metric("后期月均 GMV", f"R$ {h2:,.0f}",
                  delta=f"{'增长' if h2>h1 else '下降'} {abs((h2/h1-1)*100):.0f}%",
                  delta_color="off")
        pk = gmv.loc[gmv['gmv'].idxmax()]
        st.metric(f"峰值 ({pk['month']})", f"R$ {pk['gmv']:,.0f}")
    st.markdown(
        '<div class="insight-box"><b>分析</b>：2018上半年GMV同比翻倍，但5月后连续下滑'
        '（~99万->~85万 BRL）。季节性波动还是增长瓶颈？</div>', unsafe_allow_html=True)
    st.markdown("---")

    # -- S2: Retention --
    st.markdown('<p class="section-title">二、用户为什么不再回来？</p>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.2])
    with col1:
        fig, ax = plt.subplots(figsize=(3.8, 3.2))
        rp = (rfm['frequency'] > 1).sum(); once = len(rfm) - rp
        wedges, texts, autotexts = ax.pie(
            [once, rp], labels=[f'仅买一次\n{once:,} 人', f'买过2次+\n{rp:,} 人'],
            colors=['#E74C3C','#27AE60'], autopct='%1.1f%%',
            textprops={'fontsize':12}, startangle=90, explode=(0,0.06))
        for t in texts: t.set_fontproperties(FONT_CN_BIG)
        for a in autotexts: a.set_fontweight('bold'); a.set_fontsize(14)
        ax.set_title('97.6% 的用户只买过一次', fontweight='bold',
                     fontproperties=FONT_CN_TITLE, pad=18)
        save_and_show(fig)
    with col2:
        st.markdown("""
        ### 同期群留存：次月仅 0.5%
        - Month 0：100%
        - Month 1：**0.5%**（200人剩1个）
        - Month 2+：趋近于0

        <div class="insight-box">
        <b>不是运营问题，是商业模式决定的。</b><br>
        Olist品类（家具、床品、手表）天然低频。用户买一张桌子，五年不换。
        </div>

        **结论**：策略聚焦拉新效率+首单价值最大化。
        """, unsafe_allow_html=True)
    st.markdown("---")

    # -- S3: User Value --
    st.markdown('<p class="section-title">三、哪些用户在贡献价值？</p>', unsafe_allow_html=True)
    rfm_c = rfm.dropna().copy()
    sc = StandardScaler(); rfm_s = sc.fit_transform(rfm_c[['recency','frequency','monetary']])
    km = KMeans(n_clusters=4, random_state=42, n_init=10); rfm_c['seg'] = km.fit_predict(rfm_s)
    seg = rfm_c.groupby('seg').agg(u=('seg','count'), rec=('recency','mean'),
        freq=('frequency','mean'), mon=('monetary','mean'), rev=('monetary','sum')).round(1)
    seg['pu'] = (seg['u']/seg['u'].sum()*100).round(1)
    seg['pr'] = (seg['rev']/seg['rev'].sum()*100).round(1)
    so = seg.sort_values('mon', ascending=False)
    nms = {so.index[0]:'大额单次客户', so.index[1]:'潜力复购用户',
           so.index[2]:'流失预警', so.index[3]:'普通一次性'}
    seg['name'] = seg.index.map(nms)
    st.dataframe(
        seg[['name','u','pu','freq','mon','pr']]
        .rename(columns={'name':'用户群','u':'人数','pu':'占比%','freq':'人均次数',
                         'mon':'人均消费(BRL)','pr':'收入贡献%'})
        .set_index('用户群').style.format('{:.1f}', subset=['人均次数','人均消费(BRL)','收入贡献%','占比%']),
        use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="insight-box"><b>2.4%用户贡献19%收入。</b><br>'
                    '2,229人，人均R$1,138，是普通用户10倍。</div>', unsafe_allow_html=True)
    with col2:
        fig, ax = plt.subplots(figsize=(5.5, 4.2))
        sc2 = {0:'#95A5A6',1:'#F39C12',2:'#E74C3C',3:'#27AE60'}
        for s in range(4):
            sub = rfm_c[rfm_c['seg']==s].sample(min(400,(rfm_c['seg']==s).sum()))
            ax.scatter(sub['recency'],sub['monetary'],c=sc2[s],alpha=0.35,s=8,label=nms[s])
        ax.set_xlabel('Recency（天）',fontproperties=FONT_CN)
        ax.set_ylabel('Monetary（BRL）',fontproperties=FONT_CN)
        ax.set_title('RFM：Recency vs Monetary',fontweight='bold',fontproperties=FONT_CN_TITLE,pad=14)
        ax.set_xlim(0,800); ax.set_ylim(0,rfm_c['monetary'].quantile(0.95))
        leg=ax.legend(loc='upper right',framealpha=0.8)
        for t in leg.get_texts(): t.set_fontproperties(FONT_CN_SM)
        save_and_show(fig)
    st.markdown("---")

    # -- S4: Review --
    st.markdown('<p class="section-title">四、差评根因：商品还是物流？</p>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.bar(range(len(inst)), inst['v'],
               color=[C_LIGHT_BLUE,'#85C1E9','#5B9BD5',C_BLUE,'#1B4F72'],
               edgecolor='white',linewidth=1.2,width=0.6)
        for i,(_,rw) in enumerate(inst.iterrows()):
            ax.text(i,rw['v']+8,f"R$ {rw['v']:.0f}",ha='center',fontsize=10,fontweight='bold')
        ax.set_xticks(range(len(inst))); ax.set_xticklabels(inst['r'],fontproperties=FONT_CN)
        ax.set_ylabel('平均付款金额（BRL）',fontproperties=FONT_CN)
        ax.set_ylim(0,inst['v'].max()*1.28)
        ax.set_title('信用卡分期 vs 客单价',fontweight='bold',fontproperties=FONT_CN_TITLE,pad=14)
        save_and_show(fig)
        st.markdown('<div class="highlight-box"><b>分期是杠杆</b>：分12期消费=一次付清的3.5倍。</div>',
                    unsafe_allow_html=True)
    with col2:
        st.markdown("""
        ### 10.9万条评价归因
        | 维度 | 1星 | 5星 | 趋势 |
        |------|:--:|:--:|:---:|
        | 提前天数 | -9.0 | -13.0 | 越快越高 |
        | 运费/价格 | 35.2% | 31.1% | 越重越低 |
        | 商品价格 | R$123 | R$121 | **无关** |

        <div class="insight-box"><b>双杀验证</b><br>
        真延迟+高运费->差评率<b>75.2%</b>（整体11.4%，6.6x）</div>
        **结论**：物流体验是差评推手，不是商品质量。
        """, unsafe_allow_html=True)
    st.markdown("---")

    # -- S5: Forecast --
    st.markdown('<p class="section-title">五、未来3个月GMV预测</p>', unsafe_allow_html=True)
    gmv['ds'] = pd.to_datetime(gmv['month']+'-01'); gmv['y'] = gmv['gmv']
    bf = pd.DataFrame({'holiday':'bf','ds':pd.to_datetime(['2017-11-01']),
                        'lower_window':0,'upper_window':0})
    m = Prophet(yearly_seasonality=False,weekly_seasonality=False,daily_seasonality=False,
                holidays=bf,changepoint_prior_scale=0.5,seasonality_mode='additive')
    m.fit(gmv[['ds','y']])
    fut = m.make_future_dataframe(periods=3,freq='MS'); fc = m.predict(fut)
    fig, ax = plt.subplots(figsize=(9,4))
    ax.plot(gmv['ds'],gmv['y']/1e6,'ko-',markersize=6,label='实际',linewidth=2)
    ax.plot(fc['ds'],fc['yhat']/1e6,'-',color=C_BLUE,linewidth=1.5,alpha=0.7,label='拟合')
    fmk = fc['ds'] > gmv['ds'].max()
    ax.plot(fc[fmk]['ds'],fc[fmk]['yhat']/1e6,'D-',color=C_GREEN,markersize=9,linewidth=2.2,label='预测')
    ax.fill_between(fc['ds'],fc['yhat_lower']/1e6,fc['yhat_upper']/1e6,color='gray',alpha=0.1,label='95%CI')
    ax.set_ylabel('GMV（百万 BRL）',fontproperties=FONT_CN)
    ax.set_title('月度GMV趋势 & 预测',fontweight='bold',fontproperties=FONT_CN_TITLE,pad=14)
    leg=ax.legend(loc='upper left',framealpha=0.8)
    for t in leg.get_texts(): t.set_fontproperties(FONT_CN_SM)
    ax.set_ylim(0,gmv['y'].max()/1e6*1.22); save_and_show(fig)
    fd = fc[fmk][['ds','yhat','yhat_lower','yhat_upper']]
    fd['month'] = fd['ds'].dt.strftime('%Y-%m')
    c1,c2,c3 = st.columns(3)
    for i,(_,rw) in enumerate(fd.iterrows()):
        [c1,c2,c3][i].metric(f"{rw['month']} 预测",f"R$ {rw['yhat']:,.0f}",
                              delta=f"+/-R${rw['yhat']-rw['yhat_lower']:,.0f}",delta_color="off")
    st.markdown('<div class="insight-box"><b>建模</b>：仅20月数据，关年度季节性防过拟合。'
                '<b>预测</b>：未来3月82-85万 BRL，温和下行。</div>', unsafe_allow_html=True)
    st.markdown("---")

    # -- S6: Summary --
    st.markdown('<p class="section-title">六、总结与建议</p>', unsafe_allow_html=True)
    m1,m2,m3 = st.columns(3)
    m1.markdown('<div class="metric-card"><b>核心问题</b><br><br>'
                '<span style="font-size:2.4rem;font-weight:800;color:#C0392B;">97.6%</span><br>'
                '只买一次<br><span style="color:#999;font-size:0.85rem;">次月留存0.5%</span></div>',
                unsafe_allow_html=True)
    m2.markdown('<div class="metric-card"><b>根本原因</b><br><br>'
                '<span style="font-size:2.4rem;font-weight:800;color:#D68910;">运费+物流</span><br>'
                '驱动差评<br><span style="color:#999;font-size:0.85rem;">双杀差评率75.2%</span></div>',
                unsafe_allow_html=True)
    m3.markdown('<div class="metric-card"><b>增长方向</b><br><br>'
                '<span style="font-size:2.4rem;font-weight:800;color:#1E8449;">拉新+首单</span><br>'
                '价值最大化<br><span style="color:#999;font-size:0.85rem;">2.4%客户贡献19%收入</span></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="insight-box"><b>P0 首单体验拦截</b>：延迟+高运费订单差评前自动补偿。'
                '<b> P1 大额客户定向</b>：首单后7天关联推荐。'
                '<b> P1 分期引导</b>：商品页展示分期每期金额。</div>', unsafe_allow_html=True)

# ====================================================================
# TAB 2: 自主数据探索（动态筛选 + 图表）
# ====================================================================
with tab_explore:
    st.markdown("## 自主数据探索")
    st.caption("选择筛选条件，图表和指标实时更新。配合左侧分析助手，自由挖掘数据。")

    # ---- 筛选器 ----
    with st.container():
        st.markdown("### 筛选条件")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            t_range = st.select_slider(
                "时间范围", options=all_months,
                value=(all_months[0], all_months[-1]))
        with fc2:
            s_states = st.multiselect(
                "州（空=全部）", options=all_states,
                default=[], placeholder="选择州...")
            if not s_states: s_states = all_states
        with fc3:
            s_cats = st.multiselect(
                "品类（空=全部）", options=all_cats,
                default=[], placeholder="选择品类...")
            if not s_cats: s_cats = all_cats

    # ---- 动态 SQL 查询 ----
    @st.cache_data(ttl=300)
    def explore_data(month_from, month_to, states, cats):
        states_str = ",".join([f"'{s}'" for s in states])
        cats_list = ",".join([f"'{c}'" for c in cats])

        # GMV 趋势
        gmv_q = text(f"""
            SELECT DATE_FORMAT(o.order_purchase_timestamp,'%Y-%m') AS month,
                   ROUND(SUM(oi.price),2) AS gmv, COUNT(DISTINCT o.order_id) AS orders
            FROM orders o
            JOIN order_items oi ON o.order_id=oi.order_id
            JOIN customers c ON o.customer_id=c.customer_id
            JOIN products p ON oi.product_id=p.product_id
            JOIN product_category_translation pt ON p.product_category_name=pt.product_category_name
            WHERE o.order_status IN('delivered','shipped')
              AND o.order_purchase_timestamp IS NOT NULL
              AND DATE_FORMAT(o.order_purchase_timestamp,'%Y-%m') BETWEEN :m1 AND :m2
              AND c.customer_state IN ({states_str})
              AND pt.product_category_name_english IN ({cats_list})
            GROUP BY month
            HAVING COUNT(DISTINCT o.order_id)>=10 ORDER BY month
        """)
        gmv_ex = pd.read_sql(gmv_q, engine, params={"m1": month_from, "m2": month_to})

        # 州排名
        st_q = text(f"""
            SELECT c.customer_state, COUNT(DISTINCT o.order_id) AS orders,
                   ROUND(SUM(oi.price),2) AS revenue
            FROM orders o
            JOIN order_items oi ON o.order_id=oi.order_id
            JOIN customers c ON o.customer_id=c.customer_id
            JOIN products p ON oi.product_id=p.product_id
            JOIN product_category_translation pt ON p.product_category_name=pt.product_category_name
            WHERE o.order_status IN('delivered','shipped')
              AND DATE_FORMAT(o.order_purchase_timestamp,'%Y-%m') BETWEEN :m1 AND :m2
              AND c.customer_state IN ({states_str})
              AND pt.product_category_name_english IN ({cats_list})
            GROUP BY c.customer_state ORDER BY revenue DESC
        """)
        state_ex = pd.read_sql(st_q, engine, params={"m1": month_from, "m2": month_to})

        # 品类排名
        cat_q = text(f"""
            SELECT pt.product_category_name_english AS cat,
                   COUNT(DISTINCT o.order_id) AS orders,
                   ROUND(SUM(oi.price),2) AS revenue,
                   ROUND(AVG(oi.price),2) AS avg_price
            FROM orders o
            JOIN order_items oi ON o.order_id=oi.order_id
            JOIN customers c ON o.customer_id=c.customer_id
            JOIN products p ON oi.product_id=p.product_id
            JOIN product_category_translation pt ON p.product_category_name=pt.product_category_name
            WHERE o.order_status IN('delivered','shipped')
              AND DATE_FORMAT(o.order_purchase_timestamp,'%Y-%m') BETWEEN :m1 AND :m2
              AND c.customer_state IN ({states_str})
              AND pt.product_category_name_english IN ({cats_list})
            GROUP BY pt.product_category_name_english ORDER BY revenue DESC LIMIT 15
        """)
        cat_ex = pd.read_sql(cat_q, engine, params={"m1": month_from, "m2": month_to})

        # 支付
        pay_q = text(f"""
            SELECT op.payment_type, COUNT(*) AS cnt,
                   ROUND(AVG(op.payment_value),2) AS avg_val,
                   ROUND(SUM(op.payment_value),2) AS total_val
            FROM order_payments op
            JOIN orders o ON op.order_id=o.order_id
            JOIN order_items oi ON o.order_id=oi.order_id
            JOIN customers c ON o.customer_id=c.customer_id
            JOIN products p ON oi.product_id=p.product_id
            JOIN product_category_translation pt ON p.product_category_name=pt.product_category_name
            WHERE o.order_status IN('delivered','shipped')
              AND DATE_FORMAT(o.order_purchase_timestamp,'%Y-%m') BETWEEN :m1 AND :m2
              AND c.customer_state IN ({states_str})
              AND pt.product_category_name_english IN ({cats_list})
            GROUP BY op.payment_type ORDER BY total_val DESC
        """)
        pay_ex = pd.read_sql(pay_q, engine, params={"m1": month_from, "m2": month_to})

        return gmv_ex, state_ex, cat_ex, pay_ex

    gmv_ex, state_ex, cat_ex, pay_ex = explore_data(
        t_range[0], t_range[1], s_states, s_cats)

    # ---- 指标卡片 ----
    total_gmv = gmv_ex['gmv'].sum()
    total_orders = gmv_ex['orders'].sum()
    avg_aov = (gmv_ex['gmv'].sum() / gmv_ex['orders'].sum()) if total_orders > 0 else 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总 GMV", f"R$ {total_gmv:,.0f}")
    m2.metric("总订单", f"{total_orders:,}")
    m3.metric("月均 GMV", f"R$ {gmv_ex['gmv'].mean():,.0f}")
    m4.metric("平均客单价", f"R$ {avg_aov:.0f}")

    fig_info = f"州:{len(s_states)}个 | 品类:{len(s_cats)}个 | {t_range[0]}~{t_range[1]}"
    st.caption(f"当前筛选：{fig_info} | 数据月数：{len(gmv_ex)}")

    st.markdown("---")

    # ---- 图表区 ----
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### GMV 趋势")
        if len(gmv_ex) > 0:
            fig, ax = plt.subplots(figsize=(6, 3.5))
            xs = range(len(gmv_ex))
            ax.plot(xs, gmv_ex['gmv']/1e6, 'o-', color=C_BLUE, markersize=6, linewidth=2)
            ax.fill_between(xs, 0, gmv_ex['gmv']/1e6, alpha=0.06, color=C_BLUE)
            ax.set_ylabel('GMV（百万 BRL）', fontproperties=FONT_CN)
            ax.set_ylim(0, gmv_ex['gmv'].max()/1e6*1.2)
            ax.set_xticks([])
            ax.set_title('月度 GMV', fontweight='bold', fontproperties=FONT_CN_TITLE, pad=12)
            save_and_show(fig)
        else:
            st.warning("当前筛选条件下无足够数据。请放宽筛选条件。")

    with col_right:
        st.markdown("#### 州销售额 Top 10")
        if len(state_ex) > 0:
            fig, ax = plt.subplots(figsize=(6, 3.5))
            top_s = state_ex.head(10).iloc[::-1]
            colors = [C_BLUE if s == 'SP' else '#AED6F1' for s in top_s['customer_state']]
            ax.barh(range(len(top_s)), top_s['revenue']/1e3, color=colors, height=0.7)
            ax.set_yticks(range(len(top_s)))
            ax.set_yticklabels(top_s['customer_state'])
            ax.set_xlabel('Revenue（千 BRL）')
            ax.set_title('Top 10 州', fontweight='bold', fontproperties=FONT_CN_TITLE, pad=12)
            save_and_show(fig)
        else:
            st.warning("当前筛选条件下无足够数据。")

    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.markdown("#### 品类销售额 Top 10")
        if len(cat_ex) > 0:
            fig, ax = plt.subplots(figsize=(6, 4))
            top_c = cat_ex.head(10).iloc[::-1]
            ax.barh(range(len(top_c)), top_c['revenue']/1e3, color=C_BLUE, height=0.7)
            ax.set_yticks(range(len(top_c)))
            ax.set_yticklabels(top_c['cat'].str.replace('_',' ').str.title())
            ax.set_xlabel('Revenue（千 BRL）')
            ax.set_title('Top 10 品类', fontweight='bold', fontproperties=FONT_CN_TITLE, pad=12)
            save_and_show(fig)
        else:
            st.warning("当前筛选条件下无足够数据。")

    with col_right2:
        st.markdown("#### 支付方式分布")
        if len(pay_ex) > 0:
            fig, ax = plt.subplots(figsize=(6, 4))
            colors_p = ['#2471A3','#D68910','#1E8449','#C0392B','#7F8C8D']
            ax.pie(pay_ex['total_val'], labels=pay_ex['payment_type'],
                   autopct='%1.1f%%', colors=colors_p[:len(pay_ex)],
                   textprops={'fontsize':10}, startangle=90)
            ax.set_title('支付方式（按金额）', fontweight='bold', fontproperties=FONT_CN_TITLE, pad=12)
            save_and_show(fig)
        else:
            st.warning("当前筛选条件下无足够数据。")

    # ---- 明细表 ----
    st.markdown("---")
    st.markdown("#### 数据明细")
    tab_s, tab_c = st.tabs(["州排名", "品类排名"])
    with tab_s:
        st.dataframe(state_ex, use_container_width=True, hide_index=True)
    with tab_c:
        st.dataframe(cat_ex, use_container_width=True, hide_index=True)

    st.caption("提示：在侧边栏输入问题，分析助手可帮你解读当前图表。")

# Footer
st.markdown("---")
st.caption("Olist 电商经营分析项目  MySQL + Python + Prophet + Streamlit + Claude")
