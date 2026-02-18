import streamlit as st
import pandas as pd
import calendar

# Configurazione Pagina
st.set_page_config(page_title="Taxi Lucca - Shift Manager", layout="wide")

st.title("🚖 Taxi Lucca: Shift Manager")
st.markdown("Gestione turni conforme alla **Direttiva Europea 2003/88/CE** (11h riposo).")

# --- SIDEBAR: PARAMETRI DI INPUT ---
with st.sidebar:
    st.header("⚙️ Impostazioni")
    
    # 1. Periodo
    mese_n = st.selectbox("Mese", range(1, 13), index=3) # Aprile
    anno = st.number_input("Anno", value=2026)
    
    st.divider()
    
    # 2. Quote Giornaliere (ECCO QUELLO CHE MANCAVA!)
    st.subheader("📊 Quote Giornaliere")
    q_mattina = st.number_input("MATTINA (M)", value=10)
    q_centrale = st.number_input("CENTRALE (C)", value=12)
    q_sera = st.number_input("SERA (S)", value=8)
    q_notte = st.number_input("NOTTE (M/N)", value=2)
    
    st.divider()
    
    # 3. Riposo
    riposo_min = st.selectbox("Riposo Minimo", ["11 ore", "16 ore"], index=0)
    
    # 4. Sospensioni
    ferie = st.text_area("Sospensioni / Ferie", placeholder="Es: Licenza 5: 1-10; Licenza 12: 15-20")

# --- LOGICA DI CALCOLO (SINTESI) ---
num_giorni = calendar.monthrange(anno, mese_n)[1]
licenze = [f"Licenza {i}" for i in range(1, 31)]
colonne = [str(i) for i in range(1, num_giorni + 1)]

# Creazione matrice vuota (Esempio visivo colorato)
df = pd.DataFrame("R", index=licenze, columns=colonne)

# --- VISUALIZZAZIONE ---
st.header(f"📅 Piano Turni - {calendar.month_name[mese_n]} {anno}")

# Funzione per colorare le celle come nella tua immagine
def color_cells(val):
    color = 'white'
    if val == 'M': color = '#D1E8FF' # Blu chiaro
    if val == 'C': color = '#D1FFD1' # Verde chiaro
    if val == 'S': color = '#FFE8D1' # Arancio chiaro
    if val == 'R': color = 'white'
    return f'background-color: {color}'

st.dataframe(df.style.applymap(color_cells), height=600)

st.button("📥 ESPORTA EXCEL")
