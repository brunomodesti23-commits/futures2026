import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import timedelta

# =====================================================================
# CONFIGURAZIONE INIZIALE - SIGNAL MACHINE
# =====================================================================
st.set_page_config(page_title="Trading Hub - Black Box", page_icon="🎯", layout="wide")
st.title("🎯 Black Box: Segnali Istituzionali Automatici")
st.markdown("*Niente impostazioni. Solo matematica, liquidità e livelli operativi precisi.*")

# =====================================================================
# PARAMETRI ISTITUZIONALI HARDCODATI (Il segreto dell'algoritmo)
# =====================================================================
# Questi sono i parametri ottimali fissati dal Pro Trader, inaccessibili all'utente.
VOL_LENGTH = 20          # Periodi per la media dei volumi
VOL_MULT = 1.5           # Moltiplicatore per identificare l'ingresso istituzionale
LOOKBACK_SWEEP = 10      # Candele per la caccia agli stop
RR_RATIO = 2.0           # Rapporto Rischio Rendimento blindato a 1:2

watchlists = {
    "🎯 Futures (Seleziona per i Segnali)": ["NQ=F", "ES=F", "RTY=F", "CL=F", "GC=F"]
}

# =====================================================================
# MOTORE DI CALCOLO E ALGORITMO SMC
# =====================================================================
@st.cache_data(ttl=60) # Si aggiorna ogni minuto
def carica_e_calcola(ticker):
    try:
        titolo = yf.Ticker(ticker)
        dati = titolo.history(period="5d", interval="15m")
        if dati.empty: return None
        dati = dati.dropna().copy()
        
        # ATR Intraday per i Buffer degli Stop Loss
        dati['TR'] = np.maximum(dati['High'] - dati['Low'], 
                     np.maximum(abs(dati['High'] - dati['Close'].shift(1)), 
                                abs(dati['Low'] - dati['Close'].shift(1))))
        dati['ATR_15m'] = dati['TR'].rolling(window=14).mean()
        
        # Volumi e VWAP
        dati['Volume_Medio'] = dati['Volume'].rolling(window=VOL_LENGTH).mean()
        dati['Data'] = dati.index.date
        dati['Prezzo_Tipico'] = (dati['High'] + dati['Low'] + dati['Close']) / 3
        dati['Cum_Volume'] = dati.groupby('Data')['Volume'].cumsum()
        dati['Cum_VP'] = dati.groupby('Data')['Volume_x_Prezzo'] = dati['Prezzo_Tipico'] * dati['Volume']
        dati['Cum_VP'] = dati.groupby('Data')['Volume_x_Prezzo'].cumsum()
        dati['VWAP'] = dati['Cum_VP'] / dati['Cum_Volume']
        
        return dati.dropna()
    except:
        return None

def calcola_fvg_smc(df):
    zones = []
    for i in range(max(3, LOOKBACK_SWEEP + 2), len(df)):
        curr, prev1, prev2 = df.iloc[i], df.iloc[i-1], df.iloc[i-2]
        
        # 1. Gestione Inversion (se rompe la zona)
        for z in zones:
            if z['status'] == 'active':
                z['end_idx'] = df.index[i]
                if z['type'] == 'bull' and curr['Close'] < z['bottom'] and prev1['Close'] >= z['bottom']:
                    z['status'] = 'inverted_short'
                elif z['type'] == 'bear' and curr['Close'] > z['top'] and prev1['Close'] <= z['top']:
                    z['status'] = 'inverted_long'

        # 2. Pattern SMC + Filtro Sweep + Filtro Volumi
        is_high_volume = prev1['Volume'] > (prev1['Volume_Medio'] * VOL_MULT)
        
        fvg_bull = curr['Low'] > prev2['High'] and prev1['Close'] > prev1['Open']
        fvg_bear = curr['High'] < prev2['Low'] and prev1['Close'] < prev1['Open']
        
        # Caccia alla liquidità obbligatoria
        lowest_past = df['Low'].iloc[i-2-LOOKBACK_SWEEP : i-2].min()
        highest_past = df['High'].iloc[i-2-LOOKBACK_SWEEP : i-2].max()
        
        valid_bull = fvg_bull and is_high_volume and (prev2['Low'] < lowest_past)
        valid_bear = fvg_bear and is_high_volume and (prev2['High'] > highest_past)
        
        if valid_bull:
            zones.append({'type': 'bull', 'status': 'active', 'start_idx': df.index[i-2], 'end_idx': df.index[i], 'top': curr['Low'], 'bottom': prev2['High']})
        if valid_bear:
            zones.append({'type': 'bear', 'status': 'active', 'start_idx': df.index[i-2], 'end_idx': df.index[i], 'top': prev2['Low'], 'bottom': curr['High']})
            
    for z in zones:
        if z['status'] == 'active' or z['status'].startswith('inverted'):
            z['end_idx'] = df.index[-1] + timedelta(minutes=45) 
            
    return zones

def trova_segnale_automatico(prezzo, vwap, atr, zone_attive):
    for z in reversed(zone_attive):  
        if z['bottom'] <= prezzo <= z['top']:
            buffer = atr * 0.5 # Aggiunge un po' di respiro allo stop loss basato sull'ATR
            
            # SEGNALE LONG
            if (z['status'] == 'active' and z['type'] == 'bull') or z['status'] == 'inverted_long':
                # Regola d'oro: Compriamo solo se siamo SOPRA o VICINISSIMI al VWAP
                if prezzo >= (vwap - atr): 
                    sl = z['bottom'] - buffer
                    tp = prezzo + ((prezzo - sl) * RR_RATIO)
                    return {"azione": "COMPRA AL MERCATO (LONG) 🟢", "colore": "#00C851", "entry": prezzo, "sl": sl, "tp": tp, "zona": z}
                    
            # SEGNALE SHORT
            elif (z['status'] == 'active' and z['type'] == 'bear') or z['status'] == 'inverted_short':
                # Regola d'oro: Vendiamo solo se siamo SOTTO o VICINISSIMI al VWAP
                if prezzo <= (vwap + atr):
                    sl = z['top'] + buffer
                    tp = prezzo - ((sl - prezzo) * RR_RATIO)
                    return {"azione": "VENDI AL MERCATO (SHORT) 🔴", "colore": "#ff4444", "entry": prezzo, "sl": sl, "tp": tp, "zona": z}
    return None

# =====================================================================
# CRUSCOTTO OPERATIVO (UI PULITA E DIRETTA)
# =====================================================================
asset_selezionato = st.selectbox("Seleziona il Mercato:", watchlists["🎯 Futures (Seleziona per i Segnali)"])
dati = carica_e_calcola(asset_selezionato)

if dati is not None:
    ultimo_prezzo = dati.iloc[-1]['Close']
    ultimo_vwap = dati.iloc[-1]['VWAP']
    ultimo_atr = dati.iloc[-1]['ATR_15m']
    zone_fvg = calcola_fvg_smc(dati)
    
    segnale = trova_segnale_automatico(ultimo_prezzo, ultimo_vwap, ultimo_atr, zone_fvg)
    
    # 1. PANNELLO SEGNALI (ENORME)
    if segnale:
        st.markdown(f"""
        <div style="background-color: {segnale['colore']}20; border: 2px solid {segnale['colore']}; padding: 20px; border-radius: 10px; text-align: center;">
            <h1 style="color: {segnale['colore']}; margin: 0; font-size: 40px;">{segnale['azione']}</h1>
            <p style="font-size: 20px; margin-top: 10px;">Le condizioni istituzionali (VWAP + FVG) sono allineate in questo preciso istante.</p>
        </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("1️⃣ INGRESSO", f"{segnale['entry']:.2f}")
        c2.metric("2️⃣ STOP LOSS (Imprescindibile)", f"{segnale['sl']:.2f}")
        c3.metric("3️⃣ TAKE PROFIT (Risk 1:2)", f"{segnale['tp']:.2f}")
    else:
        st.markdown("""
        <div style="background-color: #333333; border: 2px solid #555555; padding: 20px; border-radius: 10px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 40px;">⚪ MANI IN TASCA (NESSUN SEGNALE)</h1>
            <p style="font-size: 20px; margin-top: 10px; color: #aaaaaa;">Il prezzo sta facendo rumore. Attendiamo che cada nella nostra trappola di liquidità.</p>
        </div>
        """, unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Prezzo Attuale", f"{ultimo_prezzo:.2f}")
        c2.metric("VWAP (Bussola)", f"{ultimo_vwap:.2f}")
        c3.metric("Volatilità (ATR)", f"{ultimo_atr:.2f} pt")

    # 2. GRAFICO (Semplice, ti mostra solo il contesto)
    st.markdown("---")
    st.markdown(f"### Mappa del Campo di Battaglia ({asset_selezionato})")
    
    ultimi_giorni = dati.tail(70) 
    fig = go.Figure()
    
    fig.add_trace(go.Candlestick(
        x=ultimi_giorni.index, open=ultimi_giorni['Open'], high=ultimi_giorni['High'], 
        low=ultimi_giorni['Low'], close=ultimi_giorni['Close'], name='Prezzo'
    ))
    
    fig.add_trace(go.Scatter(
        x=ultimi_giorni.index, y=ultimi_giorni['VWAP'], 
        mode='lines', name='VWAP', line=dict(color='white', width=2, dash='dot')
    ))
    
    for z in zone_fvg:
        if z['end_idx'] >= ultimi_giorni.index[0]: 
            if z['status'] == 'active' and z['type'] == 'bull':
                fill_c, line_c = 'rgba(0, 255, 0, 0.15)', 'lime'
            elif z['status'] == 'active' and z['type'] == 'bear':
                fill_c, line_c = 'rgba(255, 0, 0, 0.15)', 'red'
            elif z['status'] == 'inverted_short':
                fill_c, line_c = 'rgba(255, 165, 0, 0.15)', 'orange'
            elif z['status'] == 'inverted_long':
                fill_c, line_c = 'rgba(0, 191, 255, 0.15)', 'deepskyblue'
            else:
                continue
            
            fig.add_shape(type="rect",
                x0=z['start_idx'], y0=z['bottom'], x1=z['end_idx'], y1=z['top'],
                line=dict(color=line_c, width=1), fillcolor=fill_c, layer="below"
            )

    if segnale:
        fig.add_hline(y=segnale['entry'], line_color="white", annotation_text="ENTRATA")
        fig.add_hline(y=segnale['sl'], line_dash="dot", line_color="red", annotation_text="STOP LOSS")
        fig.add_hline(y=segnale['tp'], line_dash="dot", line_color="green", annotation_text="TAKE PROFIT")

    fig.update_layout(
        xaxis_rangeslider_visible=False, template="plotly_dark", height=600, 
        margin=dict(l=10, r=60, t=10, b=10), yaxis=dict(side="right", tickformat=".2f"), showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.caption("Nota: I dati Yahoo Finance gratuiti possono avere fino a 15 min di ritardo. Usare questo algoritmo su un conto Prop in Live richiede un flusso dati in tempo reale (es. NinjaTrader/Tradovate) per eseguire l'ordine effettivo.")
else:
    st.error("Dati in caricamento o mercati chiusi.")
