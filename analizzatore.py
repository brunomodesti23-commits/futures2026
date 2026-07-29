import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# =====================================================================
# CONFIGURAZIONE INIZIALE (Stile Formi.life)
# =====================================================================
st.set_page_config(page_title="Trading Hub - Prop Firm Edition", page_icon="🐜", layout="wide")
st.title("🐜 Hub Intraday: Prop Firm Challenge Edition")
st.markdown("*L'efficienza del cecchino: Entrate precise, Stop stretti, Nessun Overnight.*")

# =====================================================================
# WATCHLIST ESCLUSIVA DAY TRADING
# =====================================================================
watchlists = {
    "🎯 Micro/Mini Futures": [
        "NQ=F",   # Nasdaq 100
        "ES=F",   # S&P 500
        "RTY=F",  # Russell 2000 
        "CL=F",   # Petrolio
        "GC=F"    # Oro
    ]
}

# =====================================================================
# MOTORE DI CALCOLO ROBUSTO (FVG + VWAP + VOLUMI)
# =====================================================================
@st.cache_data(ttl=60)
def carica_e_calcola_smart_money(ticker):
    try:
        titolo = yf.Ticker(ticker)
        # Scarichiamo gli ultimi 5 giorni a 15 minuti per avere storico solido
        dati = titolo.history(period="5d", interval="15m")
        if dati is None or len(dati) < 30:
            return None
        
        dati = dati.dropna().copy()
        
        # 1. Volumi e Media Mobile dei Volumi
        vol_length = 20
        vol_mult = 1.5
        dati['Avg_Vol'] = dati['Volume'].rolling(window=vol_length).mean()
        dati['High_Volume'] = dati['Volume'] > (dati['Avg_Vol'] * vol_mult)
        
        # 2. Fair Value Gaps (FVG)
        dati['FVG_Bull'] = (dati['Low'] > dati['High'].shift(2)) & (dati['Close'].shift(1) > dati['Open'].shift(1))
        dati['FVG_Bear'] = (dati['High'] < dati['Low'].shift(2)) & (dati['Close'].shift(1) < dati['Open'].shift(1))
        
        # 3. ATR Intraday per Stop Loss dinamico
        dati['TR'] = np.maximum(dati['High'] - dati['Low'], 
                     np.maximum(abs(dati['High'] - dati['Close'].shift(1)), 
                                abs(dati['Low'] - dati['Close'].shift(1))))
        dati['ATR'] = dati['TR'].rolling(window=14).mean()
        
        # 4. VWAP Giornaliero
        dati['Data'] = dati.index.date
        dati['Prezzo_Tipico'] = (dati['High'] + dati['Low'] + dati['Close']) / 3
        dati['VP'] = dati['Prezzo_Tipico'] * dati['Volume']
        dati['Cum_Vol'] = dati.groupby('Data')['Volume'].cumsum()
        dati['Cum_VP'] = dati.groupby('Data')['VP'].cumsum()
        dati['VWAP'] = dati['Cum_VP'] / dati['Cum_Vol']
        
        # 5. Breakout Operativo (Incrocio VWAP con Volumi - Setup d'assalto)
        dati['VWAP_Cross_Bull'] = (dati['Close'] > dati['VWAP']) & (dati['Close'].shift(1) < dati['VWAP'].shift(1)) & dati['High_Volume']
        dati['VWAP_Cross_Bear'] = (dati['Close'] < dati['VWAP']) & (dati['Close'].shift(1) > dati['VWAP'].shift(1)) & dati['High_Volume']
        
        return dati.dropna()
    except Exception as e:
        return None

# =====================================================================
# INTERFACCIA UTENTE (SIDEBAR & HUD)
# =====================================================================
st.sidebar.header("⚙️ Configurazione Cecchino")
asset_selezionato = st.sidebar.selectbox("Seleziona Asset:", watchlists["🎯 Micro/Mini Futures"])

st.sidebar.markdown("---")
st.sidebar.markdown("### Regole di Gestione")
st.sidebar.markdown("- **Rischio/Rendimento:** 1 : 2")
st.sidebar.markdown("- **Filtro Volumi:** 1.5x la media")
st.sidebar.markdown("- **Orario Operativo:** 15:30 - 21:30 (NY Session)")

st.warning("⚠️ **REGOLA D'ORO PROP FIRM:** Chiudi TUTTE le posizioni prima delle 22:00. Zero overnight!")

# Caricamento dati
dati = carica_e_calcola_smart_money(asset_selezionato)

if dati is not None and not dati.empty:
    ultimo = dati.iloc[-1]
    prezzo_corrente = ultimo['Close']
    vwap_val = ultimo['VWAP']
    atr_val = ultimo['ATR']
    
    # Controllo delle ultime 3 candele per segnali freschi
    ultime_3 = dati.tail(3)
    
    # Setup 1: FVG (Cecchino - Raro ma letale)
    fvg_long = ultime_3['FVG_Bull'].any() and (prezzo_corrente > vwap_val)
    fvg_short = ultime_3['FVG_Bear'].any() and (prezzo_corrente < vwap_val)
    
    # Setup 2: VWAP Breakout (Assalto in apertura - Più frequente)
    vwap_cross_long = ultime_3['VWAP_Cross_Bull'].any()
    vwap_cross_short = ultime_3['VWAP_Cross_Bear'].any()
    
    segnale_long = fvg_long or vwap_cross_long
    segnale_short = fvg_short or vwap_cross_short
    
    tipo_setup = ""
    if fvg_long or fvg_short:
        tipo_setup = "CECCHINO (FVG)"
    elif vwap_cross_long or vwap_cross_short:
        tipo_setup = "ASSALTO (Breakout Volumi)"
    
    # Cruscotto HUD (Head-Up Display)
    col_hud1, col_hud2, col_hud3 = st.columns(3)
    
    with col_hud1:
        st.metric(label="Prezzo Attuale", value=f"{prezzo_corrente:.2f}")
    with col_hud2:
        st.metric(label="VWAP Istituzionale", value=f"{vwap_val:.2f}")
    with col_hud3:
        if segnale_long:
            st.success(f"🟢 STATO: SEGNALE LONG [{tipo_setup}]")
        elif segnale_short:
            st.error(f"🔴 STATO: SEGNALE SHORT [{tipo_setup}]")
        else:
            st.info("⚪ STATO: MANI IN TASCA (Attendi)")

    # Dettagli operativi se c'è un segnale
    if segnale_long:
        entry = prezzo_corrente
        sl = entry - (atr_val * 1.0)
        tp = entry + (atr_val * 2.0)
        st.markdown(f"""
        ### 🎯 Piano Operativo LONG
        - **Ingresso Consigliato:** `{entry:.2f}`
        - **Stop Loss (Rischio):** `{sl:.2f}` (Distanza: `{entry - sl:.2f} pt`)
        - **Take Profit (Target):** `{tp:.2f}` (Distanza: `{tp - entry:.2f} pt`)
        """)
    elif segnale_short:
        entry = prezzo_corrente
        sl = entry + (atr_val * 1.0)
        tp = entry - (atr_val * 2.0)
        st.markdown(f"""
        ### 🎯 Piano Operativo SHORT
        - **Ingresso Consigliato:** `{entry:.2f}`
        - **Stop Loss (Rischio):** `{sl:.2f}` (Distanza: `{sl - entry:.2f} pt`)
        - **Take Profit (Target):** `{tp:.2f}` (Distanza: `{entry - tp:.2f} pt`)
        """)
    else:
        st.markdown("---")
        st.markdown("### 🧘‍♂️ Zona di Attesa")
        st.markdown("Il mercato sta oscillando senza toccare le zone istituzionali con volumi anomali. **Nessuna operazione da fare.** Proteggere il capitale è il primo guadagno.")

    # Grafico Principale Pulito
    st.markdown(f"### 📊 Grafico Operativo 15m - {asset_selezionato}")
    
    # Mostriamo le ultime 80 candele per massima nitidezza
    grafico_dati = dati.tail(80)
    
    fig = go.Figure()
    
    # Candele
    fig.add_trace(go.Candlestick(
        x=grafico_dati.index,
        open=grafico_dati['Open'],
        high=grafico_dati['High'],
        low=grafico_dati['Low'],
        close=grafico_dati['Close'],
        name='Prezzo 15m'
    ))
    
    # VWAP (Linea Oro Istituzionale)
    fig.add_trace(go.Scatter(
        x=grafico_dati.index,
        y=grafico_dati['VWAP'],
        mode='lines',
        name='VWAP',
        line=dict(color='#d4af37', width=2.5)
    ))
    
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=550,
        margin=dict(l=10, r=60, t=10, b=10),
        yaxis=dict(side="right", tickformat=".2f")
    )
    
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("⏳ **Caricamento dati in corso o mercato in pausa:** Yahoo Finance sta elaborando i flussi. Ricarica la pagina tra qualche istante.")
