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

# --- Ensure Engine Exists as a Global Singleton ---
@st.cache_resource
def get_engine():
    return TradingEngine()

try:
    engine = get_engine()
except Exception as e:
    st.error(f"Initialization Error: Please ensure you have copied `.env` and added your API keys. Error: {e}")
    st.stop()

@st.fragment(run_every="4s")
def render_sidebar_metrics():
    """Isolated sidebar component to fetch balances natively without relying on cross-layout placeholders."""
    balance_info = engine.exchange.fetch_balance()
    quote_currency = "USD"
    available_balance = balance_info.get(quote_currency, {}).get('free', 0.0)
    st.metric(label=f"Available {quote_currency}", value=f"${available_balance:,.2f}")

# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ Bot Controls")
    
    st.write(f"**Tracking**: {len(engine.symbols)} Coins")
    st.write(f"**Exchange**: {engine.exchange_id.title()} Crypto Sandbox")
    
    st.markdown("---")
    view_symbol = st.selectbox("View Coin Details", ["ALL"] + engine.symbols)
    
    status_text = "🟢 RUNNING" if engine.is_running else "🔴 STOPPED"
    st.markdown(f"### Status: {status_text}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Bot", use_container_width=True, disabled=engine.is_running, type="primary"):
            engine.start()
            st.rerun()
            
    with col2:
        if st.button("Kill Switch", use_container_width=True, disabled=not engine.is_running, type="primary"):
            engine.stop()
            st.rerun()
            
    st.markdown("---")
    st.write("### Account Balance")
    try:
        render_sidebar_metrics()
    except Exception as e:
        st.error(f"Balance error: {e}")

# --- Main Logic / Refresh ---
st.markdown("---")

@st.fragment(run_every="3s")
def render_dashboard_metrics():
    """Isolated dashboard component to refresh metrics without losing browser scroll position."""
    
    # 1. Overview Section
    if view_symbol == "ALL":
        st.subheader("Live Strategy Metrics: Portfolio Overview")
        col_m1, col_m2, col_m3 = st.columns(3)
        open_positions = len([p for p in engine.open_positions.values() if p is not None])
        col_m1.metric("Active Trades", f"{open_positions} / {len(engine.symbols)}")
        col_m2.metric("Tracked Markets", len(engine.symbols))
        col_m3.metric("System Status", "🟢 EVALUATING" if engine.is_running else "🔴 STANDBY")
    else:
        st.subheader(f"Live Strategy Metrics: {view_symbol}")
        col_m1, col_m2, col_m3 = st.columns(3)
            
        # Update Live Strategy Metrics
        if engine.is_running:
            metrics = engine.strategy.metrics.get(view_symbol, {}) if engine.strategy and hasattr(engine.strategy, 'metrics') else {}
            rsi_val = metrics.get('rsi', 50.0)
            macd_val = metrics.get('macd', 0.0)
            sentiment = metrics.get('sentiment', 'WAITING')
            tech_sig = metrics.get('tech_signal', 'NEUTRAL')
            
            col_m1.metric("Current RSI", f"{rsi_val:.2f}", delta=tech_sig, delta_color="normal")
            col_m2.metric("Current MACD", f"{macd_val:.4f}")
            col_m3.metric("AI Sentiment News", sentiment)
        else:
            col_m1.info("Start bot to see metrics")
            col_m2.info("Start bot to see metrics")
            col_m3.info("Start bot to see metrics")
        
    # 2. Chart Section
    st.markdown("---")
    if view_symbol == "ALL":
        st.title("Live Chart: ALL (Comparative % Change)")
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
                    except Exception as e:
                        continue
                        
                fig.update_layout(
                    yaxis_title='Price Change (%)',
                    xaxis_rangeslider_visible=False,
                    height=600,
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=30, b=0),
                    hovermode='x unified'
                )
                st.session_state.cached_all_fig = fig
                st.session_state.last_all_update = now
                
            st.plotly_chart(st.session_state.cached_all_fig, use_container_width=True)
            st.caption("Note: 'ALL' chart refreshes every 60s to prevent API rate limiting.")
        except Exception as e:
            st.warning(f"Waiting for chart data to populate... ({e})")
    else:
        st.title(f"Live Chart: {view_symbol}")
        try:
            ohlcv = engine.exchange.fetch_ohlcv(view_symbol, timeframe='15m', limit=150)
            df_chart = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_chart['time'] = pd.to_datetime(df_chart['time'], unit='ms', utc=True).dt.tz_convert('America/New_York')
            
            # Calculate Moving Averages
            df_chart['MA7'] = df_chart['close'].rolling(window=7).mean()
            df_chart['MA25'] = df_chart['close'].rolling(window=25).mean()
            df_chart['MA99'] = df_chart['close'].rolling(window=99).mean()
            
            # Build Figure
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, subplot_titles=(view_symbol, 'Volume'), 
                                row_width=[0.2, 0.7])
            
            # Candlesticks
            fig.add_trace(go.Candlestick(x=df_chart['time'], open=df_chart['open'], high=df_chart['high'],
                low=df_chart['low'], close=df_chart['close'], name='Price'), row=1, col=1)
                
            # MAs
            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['MA7'], line=dict(color='purple', width=1), name='MA(7)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['MA25'], line=dict(color='blue', width=1), name='MA(25)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_chart['time'], y=df_chart['MA99'], line=dict(color='orange', width=1), name='MA(99)'), row=1, col=1)
            
            # Volume
            colors = ['red' if row['open'] - row['close'] >= 0 else 'green' for index, row in df_chart.iterrows()]
            fig.add_trace(go.Bar(x=df_chart['time'], y=df_chart['volume'], marker_color=colors, name='Volume'), row=2, col=1)
            
            fig.update_layout(
                yaxis_title='Price (USD)',
                xaxis_rangeslider_visible=False,
                height=600,
                template="plotly_dark",
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Waiting for chart data to populate... ({e})")
        
    # 3. Trades Section
    st.markdown("---")
    st.subheader("Recent Trades")
    trades = engine.db.get_recent_trades(10)
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
        # Fill missing costs to 0 for display aesthetics if old data has None
        df_trades['cost'] = df_trades['cost'].fillna(0.0) 
        st.dataframe(df_trades, use_container_width=True, hide_index=True)
    else:
        st.info("No trades executed yet.")
        
    # 4. Logs Section
    st.markdown("---")
    st.subheader("System Logs")
    with engine.db._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT 15")
        logs = [dict(row) for row in cursor.fetchall()]
        
    if logs:
        log_messages = []
        for log in logs:
            color = "green" if log['level'] == "INFO" else "red" if log['level'] == "ERROR" else "grey"
            log_messages.append(f":{color}[{log['timestamp']} - {log['message']}]")
        st.markdown("  \n".join(log_messages))
    else:
        st.info("No logs generated yet.")

# Execute UI rendering fragments
try:
    render_dashboard_metrics()
except Exception as e:
    st.error(f"UI Loading Error: {e}")

