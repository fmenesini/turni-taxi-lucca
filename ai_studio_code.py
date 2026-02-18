import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io
import re

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Taxi Lucca Shift Manager",
    page_icon="🚖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- COSTANTI E DATI ---
SHIFT_DETAILS = {
    'M': {'label': 'Mattina', 'hours': '04:30 - 16:00', 'color': '#dbeafe', 'text': '#1e40af', 'end': 16.0},
    'C': {'label': 'Centrale', 'hours': '07:00 - 21:00', 'color': '#dcfce7', 'text': '#166534', 'end': 21.0},
    'S': {'label': 'Sera', 'hours': '14:30 - 02:00', 'color': '#ffedd5', 'text': '#9a3412', 'end': 26.0},
    'MN': {'label': 'M/N', 'hours': '21:30 - 05:30', 'color': '#ef4444', 'text': '#ffffff', 'end': 29.5},
    'OFF': {'label': 'Assenza', 'hours': 'Ferie', 'color': '#e2e8f0', 'text': '#475569', 'end': 0},
    'R': {'label': 'Riposo', 'hours': '-', 'color': '#ffffff', 'text': '#cbd5e1', 'end': 0}
}

SHIFT_START = {'M': 4.5, 'C': 7.0, 'S': 14.5, 'MN': 21.5, 'R': 0, 'OFF': 0}

MONTH_NAMES = [
    'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
    'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'
]

# --- LOGICA DI CALCOLO ---

def parse_absences(raw_str):
    absences = []
    if not raw_str: return absences
    entries = raw_str.split(';')
    for entry in entries:
        match = re.search(r'Licenza\s*(\d+)\s*:\s*(\d+)\s*-\s*(\d+)', entry, re.I)
        if match:
            absences.append({
                'id': int(match.group(1)),
                'start': int(match.group(2)),
                'end': int(match.group(3))
            })
    return absences

def parse_overrides(raw_str):
    overrides = {}
    if not raw_str: return overrides
    entries = raw_str.split(';')
    for entry in entries:
        match = re.search(r'Licenza\s*(\d+)\s*:\s*(\w+)\s*,\s*(\d+)', entry, re.I)
        if match:
            overrides[int(match.group(1))] = {
                'last': match.group(2).upper().replace('M/N', 'MN'),
                'days': int(match.group(3))
            }
    return overrides

def is_rest_ok(prev, curr, min_h):
    if prev in ['R', 'OFF'] or curr in ['R', 'OFF']: return True
    p_end = SHIFT_DETAILS[prev]['end']
    c_start = SHIFT_START[curr] + 24.0
    return (c_start - p_end) >= min_h

def generate_schedule(settings):
    results = []
    absences = parse_absences(settings['absences_raw'])
    overrides = parse_overrides(settings['initial_overrides'])
    
    # Inizializzazione stati
    consecutive_work = {i: 0 for i in range(1, settings['num_lic'] + 1)}
    last_shift = {i: settings['default_last'] for i in range(1, settings['num_lic'] + 1)}
    stats = {i: {k: 0 for k in SHIFT_DETAILS.keys()} for i in range(1, settings['num_lic'] + 1)}

    # Applica Overrides
    for lic_id, ov in overrides.items():
        if lic_id in consecutive_work:
            consecutive_work[lic_id] = ov['days']
            last_shift[lic_id] = ov['last']

    curr_y, curr_m = settings['start_y'], settings['start_m']
    end_total = settings['end_y'] * 12 + settings['end_m']

    while (curr_y * 12 + curr_m) <= end_total:
        days_in_m = (date(curr_y, curr_m % 12 + 1, 1) - timedelta(days=1)).day if curr_m < 12 else 31
        if curr_m == 12: days_in_m = 31 # Dicembre
        
        month_matrix = {} # {lic_id: {day: shift}}
        for i in range(1, settings['num_lic'] + 1): month_matrix[i] = {}

        for day in range(1, days_in_m + 1):
            available = list(range(1, settings['num_lic'] + 1))
            
            # 1. Assenze
            for lic in list(available):
                if any(a['id'] == lic and a['start'] <= day <= a['end'] for a in absences):
                    month_matrix[lic][day] = 'OFF'
                    stats[lic]['OFF'] += 1
                    consecutive_work[lic] = 0
                    last_shift[lic] = 'OFF'
                    available.remove(lic)

            # 2. Riposo 6gg
            if settings['allow_rest']:
                for lic in list(available):
                    if consecutive_work[lic] >= 6:
                        month_matrix[lic][day] = 'R'
                        stats[lic]['R'] += 1
                        consecutive_work[lic] = 0
                        last_shift[lic] = 'R'
                        available.remove(lic)

            # 3. Assegnazione Turni
            to_assign = (['MN'] * settings['mn_c'] + ['M'] * settings['m_c'] + 
                         ['C'] * settings['c_c'] + ['S'] * settings['s_c'])
            
            for stype in to_assign:
                if not available: break
                # Equità
                available.sort(key=lambda x: stats[x][stype])
                
                found = None
                for lic in available:
                    if is_rest_ok(last_shift[lic], stype, settings['min_rest']):
                        found = lic
                        break
                
                if found:
                    month_matrix[found][day] = stype
                    stats[found][stype] += 1
                    consecutive_work[found] += 1
                    last_shift[found] = stype
                    available.remove(found)

            # 4. Restanti in Riposo
            for lic in available:
                month_matrix[lic][day] = 'R'
                stats[lic]['R'] += 1
                consecutive_work[lic] = 0
                last_shift[lic] = 'R'

        results.append({
            'year': curr_y, 'month': curr_m, 'days': days_in_m,
            'df': pd.DataFrame(month_matrix).T
        })
        
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
            
    return results

# --- INTERFACCIA UTENTE ---

# Sidebar: Celle di Selezione
with st.sidebar:
    st.markdown("### 🚖 Taxi Lucca Shift Manager")
    st.divider()
    
    st.subheader("📅 Selezione Intervallo")
    col_y1, col_y2 = st.columns(2)
    start_m = col_y1.selectbox("Mese Inizio", range(1, 13), index=0, format_func=lambda x: MONTH_NAMES[x-1])
    start_y = col_y2.selectbox("Anno Inizio", [2025, 2026, 2027], index=1)
    end_m = col_y1.selectbox("Mese Fine", range(1, 13), index=2, format_func=lambda x: MONTH_NAMES[x-1])
    end_y = col_y2.selectbox("Anno Fine", [2025, 2026, 2027], index=1)

    st.subheader("⚖️ Riposo e Vincoli")
    min_rest = st.select_slider("Riposo Minimo (ore)", options=[8, 9, 10, 11, 12, 14, 16], value=11)
    
    # Nota Direttiva UE
    st.info(f"**Direttiva 2003/88/CE**: {'✅ Conforme' if min_rest >= 11 else '⚠️ Non conforme'}")
    
    allow_rest = st.toggle("Riposo obbligatorio (24h ogni 6gg)", value=True)
    num_lic = st.number_input("Numero totale licenze", 1, 50, 30)

    st.subheader("📊 Quote di Selezione")
    col_q1, col_q2 = st.columns(2)
    m_c = col_q1.number_input("Mattina (M)", 0, 30, 9)
    c_c = col_q2.number_input("Centrale (C)", 0, 30, 9)
    s_c = col_q1.number_input("Sera (S)", 0, 30, 9)
    mn_c = col_q2.number_input("Notte (MN)", 0, 10, 1)

    st.subheader("🔄 Stato Iniziale")
    default_last = st.selectbox("Ultimo turno default", ['R', 'M', 'C', 'S', 'MN'])
    initial_overrides = st.text_area("Eccezioni (Licenza X: Turno, Gg)", 
                                   placeholder="Licenza 3: S, 5; Licenza 8: M, 2", 
                                   help="Format: Licenza ID: TIPO, GIORNI_CONSECUTIVI")

    st.subheader("🏖️ Assenze / Ferie")
    abs_raw = st.text_area("Sospensioni (Licenza X: Inizio-Fine)", 
                          placeholder="Licenza 5: 1-10; Licenza 12: 15-20")

    st.divider()
    
# Logica di Generazione
settings = {
    'start_m': start_m, 'start_y': start_y, 'end_m': end_m, 'end_y': end_y,
    'min_rest': min_rest, 'allow_rest': allow_rest, 'num_lic': num_lic,
    'm_c': m_c, 'c_c': c_c, 's_c': s_c, 'mn_c': mn_c,
    'absences_raw': abs_raw, 'initial_overrides': initial_overrides,
    'default_last': default_last
}

results = generate_schedule(settings)

# --- AREA PRINCIPALE ---

# Header
st.title(f"📅 Calendario Turni: {MONTH_NAMES[results[0]['month']-1]} {results[0]['year']}")

# Navigazione Mesi (Celle di Selezione Rapida)
if len(results) > 1:
    month_labels = [f"{MONTH_NAMES[r['month']-1]} {r['year']}" for r in results]
    selected_month_label = st.select_slider("Naviga tra i mesi generati", options=month_labels)
    active_idx = month_labels.index(selected_month_label)
else:
    active_idx = 0

active_res = results[active_idx]
df_display = active_res['df']

# Formattazione Tabella
def style_table(val):
    if val in SHIFT_DETAILS:
        d = SHIFT_DETAILS[val]
        return f'background-color: {d["color"]}; color: {d["text"]}; font-weight: bold; text-align: center'
    return 'text-align: center'

# Visualizzazione Matrix
st.markdown("#### Tabellone Licenze")
st.dataframe(
    df_display.style.applymap(style_table),
    use_container_width=True,
    height=600
)

# Pulsanti di Azione
st.divider()
col_btn1, col_btn2 = st.columns([1, 4])

# Export Excel
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    for r in results:
        sheet_name = f"{MONTH_NAMES[r['month']-1][:3]}_{r['year']}"
        r['df'].to_excel(writer, sheet_name=sheet_name)

col_btn1.download_button(
    label="📥 Esporta Calendario Excel",
    data=buffer.getvalue(),
    file_name=f"Turni_Taxi_Lucca_{start_y}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# Legenda
with st.expander("ℹ️ Legenda Turni e Orari"):
    cols = st.columns(6)
    for i, (k, v) in enumerate(SHIFT_DETAILS.items()):
        with cols[i]:
            st.markdown(f"""
            <div style="background-color:{v['color']}; color:{v['text']}; padding:10px; border-radius:10px; border:1px solid #ddd; text-align:center">
                <div style="font-weight:bold; font-size:1.2em">{k}</div>
                <div style="font-size:0.8em">{v['label']}</div>
                <div style="font-size:0.7em">{v['hours']}</div>
            </div>
            """, unsafe_allow_html=True)

# Footer Normativo
st.success(f"""
**Informativa Algoritmo:**
- **Continuità**: Lo stato finale di {MONTH_NAMES[active_res['month']-1]} è stato usato come input per il mese successivo.
- **Equità**: Il sistema ha bilanciato i turni {m_c}M, {c_c}C, {s_c}S, {mn_c}MN tra le {num_lic} licenze attive.
- **Sicurezza**: Riposo minimo garantito di {min_rest} ore tra ogni turno.
""")
