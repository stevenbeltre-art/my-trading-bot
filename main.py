import streamlit as st
import pandas as pd
import time
import datetime
import sqlite3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bot.engine import TradingEngine


# --- Configuration ---
st.set_page_config(
    page_title="Elite Quant Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="st-"] {
        font-family: 'Roboto Mono', monospace !important;
    }
    
    /* Restore Material Icons that were overwritten by the global font */
    .material-symbols-rounded, 
    [data-testid="collapsedControl"] span,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stHeader"] span {
        font-family: 'Material Symbols Rounded' !important;
        font-weight: normal !important;
        font-size: 24px !important;
    }
    
    /* Make the persistent Streamlit Header invisible to blend into Dark Mode */
    [data-testid="stHeader"] {
        background: rgba(0,0,0,0) !important;
    }
    
    /* Sleek Dark Mode Background */
    .stApp {
        background-color: #121212 !important;
        color: #E0E0E0 !important;
    }
    
    /* Push main content block down to clear the absolute-positioned sidebar toggle */
    .block-container {
        padding-top: 4rem !important;
    }
    
    /* Premium Glassmorphism for containers and sidebar */
    [data-testid="stSidebar"] {
        background: rgba(10, 10, 14, 0.95) !important;
        backdrop-filter: blur(20px) !important;
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* Rounded buttons with hover effects */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        transition: all 0.2s ease-in-out !important;
        background: linear-gradient(145deg, rgba(30, 30, 30, 0.8), rgba(15, 15, 15, 0.8)) !important;
        color: #fff !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(0, 230, 118, 0.15) !important;
        border-color: rgba(0, 230, 118, 0.5) !important;
    }
    
    /* Primary Kill Switch Button Styling */
    button[kind="primary"] {
        background: linear-gradient(145deg, #FF1744, #D50000) !important;
        color: white !important;
        border-color: transparent !important;
        box-shadow: 0 4px 12px rgba(255, 23, 68, 0.3) !important;
    }
    button[kind="primary"]:hover {
        box-shadow: 0 6px 16px rgba(255, 23, 68, 0.6) !important;
    }

    /* Beautiful Metrics Cards (Top Bar) */
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, rgba(30, 30, 35, 0.8), rgba(20, 20, 25, 0.6)) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 12px !important;
        padding: 1.2rem !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4) !important;
        backdrop-filter: blur(15px) !important;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 230, 118, 0.1) !important;
    }
    
    /* Metric Value Colors */
    div[data-testid="metric-container"] label {
        color: #A0A0A0 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00E676 !important; /* Neon Green Tint */
        font-weight: 700 !important;
        font-size: 2.4rem !important;
        text-shadow: 0 2px 10px rgba(0, 230, 118, 0.3);
    }

    /* Prevent Streamlit from 'dimming' ANY stale components during auto-refreshes */
    [data-stale="true"],
    div[data-stale="true"],
    span[data-stale="true"] {
        opacity: 1 !important;
        transition: none !important;
        filter: none !important;
    }
    
    /* Hide the top-right 'Running...' indicator to stop flashing text */
    [data-testid="stStatusWidget"] {
        visibility: hidden !important;
    }
    
    /* Selectbox styling */
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: rgba(30, 30, 30, 0.8) !important;
        border-radius: 8px;
        color: white;
        border: 1px solid rgba(255,255,255,0.1);
    }
    hr {
        border-color: rgba(255,255,255,0.05) !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Ensure Engine Exists as a Global Singleton ---
@st.cache_resource
def get_engine():
    return TradingEngine()

try:
    engine = get_engine()
except Exception as e:
    st.error(f"Initialization Error: Please ensure you have copied `.env` and added your API keys. Error: {e}")
    st.stop()

# --- Sidebar ---
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #00E676;'>⚡ ELITE QUANT</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.write(f"**Tracking Universe**: {len(engine.symbols)} Assets")
    st.write(f"**Exchange Route**: Alpaca (Paper)")
    
    st.markdown("<br>", unsafe_allow_html=True)
    view_symbol = st.selectbox("🎯 Target Component", ["ALL"] + engine.symbols)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    status_text = "🟢 ONLINE" if engine.is_running else "🔴 OFFLINE"
    st.markdown(f"**Engine Status**: {status_text}")
    
    if st.button("▶ START ENGINE", width='stretch', disabled=engine.is_running):
        engine.start()
        st.rerun()

# --- Top Bar / Header Area ---
st.markdown("## 📊 TERMINAL OVERVIEW")

@st.fragment(run_every="2s")
def render_terminal_metrics():
    col_bal, col_eq, col_pnl, col_kill = st.columns([1, 1, 1, 1])
    
    try:
        balance_info = engine.exchange.fetch_balance()
        avail = balance_info.get("USD", {}).get('free', 0.0)
        total = balance_info.get("USD", {}).get('total', 0.0)
    except:
        avail, total = 0.0, 0.0

    with col_bal:
        st.metric(label="AVAILABLE BALANCE", value=f"${avail:,.2f}" if avail else "Syncing...")

    with col_eq:
        st.metric(label="TOTAL EQUITY", value=f"${total:,.2f}" if total else "WAITING")

    with col_pnl:
        total_trades = 0
        try:
            with engine.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM trades")
                res = cursor.fetchone()
                if res: total_trades = res[0]
        except:
            pass
        st.metric(label="LIFETIME EXECUTIONS", value=str(total_trades))

    with col_kill:
        st.write("") # Vertical padding
        if st.button("🛑 KILL SWITCH", width='stretch', disabled=not engine.is_running, type="primary"):
            engine.stop()
            st.rerun()

# Render the dynamic header
render_terminal_metrics()

st.markdown("---")

# --- Main Logic / Refresh ---
@st.fragment(run_every="4s")
def render_dashboard_metrics():
    """Isolated dashboard component to refresh metrics without losing browser scroll position."""
    
    # 1. Main Stage Interactive Chart
    if view_symbol == "ALL":
        st.subheader("🌐 Global Macro Universe (Live % Change)")
        try:
            now = time.time()
            if 'cached_all_fig' not in st.session_state or now - st.session_state.get('last_all_update', 0) > 60:
                fig = go.Figure()
                for sym in engine.symbols:
                    try:
                        ohlcv = engine.exchange.fetch_ohlcv(sym, timeframe='15m', limit=50) 
                        if ohlcv:
                            df_chart = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                            df_chart['time'] = pd.to_datetime(df_chart['time'], unit='ms', utc=True).dt.tz_convert('America/New_York')
                            
                            baseline = df_chart['close'].iloc[0]
                            df_chart['pct_change'] = ((df_chart['close'] - baseline) / baseline) * 100
                            
                            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['pct_change'], name=sym, line=dict(width=2)))
                    except Exception:
                        continue
                        
                fig.update_layout(
                    yaxis_title='Price Change (%)',
                    xaxis_rangeslider_visible=False,
                    height=500,
                    template="plotly_dark",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0, r=0, t=30, b=0),
                    hovermode='x unified',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.session_state.cached_all_fig = fig
                st.session_state.last_all_update = now
                
            st.plotly_chart(st.session_state.cached_all_fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Terminal syncing chart data... ({e})")
            
    else:
        st.subheader(f"📈 {view_symbol} Live Tracking")
        try:
            ohlcv = engine.exchange.fetch_ohlcv(view_symbol, timeframe='15m', limit=150)
            df_chart = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_chart['time'] = pd.to_datetime(df_chart['time'], unit='ms', utc=True).dt.tz_convert('America/New_York')
            
            # Calculate Moving Averages
            df_chart['MA7'] = df_chart['close'].rolling(window=7).mean()
            df_chart['MA25'] = df_chart['close'].rolling(window=25).mean()
            
            # Build Figure
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, subplot_titles=('', ''), 
                                row_width=[0.2, 0.7])
            
            # Candlesticks
            fig.add_trace(go.Candlestick(x=df_chart['time'], open=df_chart['open'], high=df_chart['high'],
                low=df_chart['low'], close=df_chart['close'], name='Price',
                increasing_line_color='#00E676', decreasing_line_color='#FF1744'), row=1, col=1)
                
            # MAs
            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['MA7'], line=dict(color='rgba(255,255,255,0.6)', width=1, dash='dot'), name='MA(7)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['MA25'], line=dict(color='#00BFFF', width=1.5), name='MA(25)'), row=1, col=1)
            
            # Volume
            colors = ['#FF1744' if row['open'] - row['close'] >= 0 else '#00E676' for index, row in df_chart.iterrows()]
            fig.add_trace(go.Bar(x=df_chart['time'], y=df_chart['volume'], marker_color=colors, name='Volume'), row=2, col=1)
            
            fig.update_layout(
                yaxis_title='Price (USD)',
                xaxis_rangeslider_visible=False,
                height=550,
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Terminal syncing chart data... ({e})")

    # 2. Advanced Data Grid Section
    st.markdown("---")
    st.subheader("⚡ Live Tracking Matrix")
    
    if engine.is_running and hasattr(engine.strategy, 'metrics'):
        grid_data = []
        for sym in engine.symbols:
            metrics = engine.strategy.metrics.get(sym, {})
            price = metrics.get('last_price', 'N/A')
            
            # Smart money volume formatting
            vol_spike = metrics.get('volume_spike', False)
            vol_status = "🔥 SURGE" if vol_spike else "Ranging"
                
            grid_data.append({
                "Asset": sym,
                "Price": f"${price:,.2f}" if isinstance(price, (float, int)) else price,
                "RSI (15m)": str(round(metrics.get('rsi', 0.0), 2)) if metrics.get('rsi') else "N/A",
                "MACD (15m)": metrics.get('tech_signal', 'WAITING'),
                "Smart Volume": vol_status,
                "Macro Trend (4H)": metrics.get('macro_trend', 'WAITING'),
                "NLTK Sentiment": metrics.get('sentiment', 'WAITING'),
                "Engine Status": metrics.get('rejection_reason', 'Monitoring...')
            })
        
        df_grid = pd.DataFrame(grid_data)
        
        # Native Pandas Styler for Conditional Formatting
        def highlight_sentiment(val):
            if 'BULLISH' in str(val): return 'color: #00E676; font-weight: bold; background-color: rgba(0, 230, 118, 0.1)'
            if 'BEARISH' in str(val): return 'color: #FF1744; font-weight: bold; background-color: rgba(255, 23, 68, 0.1)'
            return 'color: #00BFFF'

        def highlight_rsi(val):
            if val == 'N/A': return 'color: #888888'
            try:
                v = float(val)
                if v >= 70: return 'color: #FF1744; font-weight: bold; background-color: rgba(255, 23, 68, 0.1)'
                if v <= 40: return 'color: #00E676; font-weight: bold; background-color: rgba(0, 230, 118, 0.1)'
            except: pass
            return 'color: #E0E0E0'

        def highlight_trend(val):
            if val == 'BULLISH': return 'color: #00E676; font-weight: bold'
            if val == 'BEARISH': return 'color: #FF1744; font-weight: bold'
            return 'color: #E0E0E0'
            
        def highlight_volume(val):
            if 'SURGE' in str(val): return 'color: #FF9100; font-weight: bold; text-shadow: 0 0 5px rgba(255, 145, 0, 0.5)'
            return 'color: #888888'

        styled_df = df_grid.style.map(highlight_rsi, subset=['RSI (15m)']) \
                                 .map(highlight_sentiment, subset=['NLTK Sentiment']) \
                                 .map(highlight_trend, subset=['Macro Trend (4H)', 'MACD (15m)']) \
                                 .map(highlight_volume, subset=['Smart Volume'])

        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350)
    else:
        st.info("Terminal standing by. Click 'START ENGINE' to populate matrix.")

    # 3. Trades & Logs
    st.markdown("---")
    col_t1, col_t2 = st.columns([1.2, 1])
    
    with col_t1:
        st.subheader("Recent Executions")
        trades = engine.db.get_recent_trades(10)
        if trades:
            df_trades = pd.DataFrame(trades)
            df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'], utc=True).dt.tz_convert('America/New_York').dt.strftime('%m-%d %I:%M:%S %p')
            df_trades['cost'] = df_trades['cost'].fillna(0.0) 
            st.dataframe(df_trades, width='stretch', hide_index=True)
        else:
            st.info("No trades executed yet.")
            
    with col_t2:
        st.subheader("System Console")
        with engine.db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT 20")
            logs = [dict(row) for row in cursor.fetchall()]
            
        if logs:
            log_messages = []
            for log in logs:
                color = "#00E676" if log['level'] == "INFO" else "#FF1744" if log['level'] == "ERROR" else "#888888"
                # Convert UTC timestamp string to localized NY time
                local_time = pd.to_datetime(log['timestamp'], utc=True).tz_convert('America/New_York')
                time_str = local_time.strftime('%Y-%m-%d %I:%M:%S %p')
                log_messages.append(f"<span style='color:{color}'>[{time_str}]</span> {log['message']}")
            
            st.markdown(
                f"<div style='background:rgba(15,15,18,0.8); padding:15px; border-radius:12px; font-family:\"Roboto Mono\", monospace; font-size:12px; height:350px; overflow-y:auto; border:1px solid rgba(255,255,255,0.05);'>"
                + "<br>".join(log_messages) + "</div>",
                unsafe_allow_html=True
            )
        else:
            st.info("No logs generated yet.")

# Execute UI rendering fragments
try:
    render_dashboard_metrics()
except Exception as e:
    st.error(f"UI Loading Error: {e}")

