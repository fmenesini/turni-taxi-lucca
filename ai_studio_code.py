import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Taxi Lucca Manager V2",
    page_icon="🚖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- COSTANTI ---
SHIFT_DETAILS = {
    'M': {'label': 'Mattina', 'hours': '04:30 - 16:00', 'color': '#dbeafe', 'text': '#1e40af', 'end': 16.0},
    'C': {'label': 'Centrale', 'hours': '07:00 - 21:00', 'color': '#dcfce7', 'text': '#166534', 'end': 21.0},
    'S': {'label': 'Sera', 'hours': '14:30 - 02:00', 'color': '#ffedd5', 'text': '#9a3412', 'end': 26.0},
    'MN': {'label': 'M/N', 'hours': '21:30 - 05:30', 'color': '#ef4444', 'text': '#ffffff', 'end': 29.5},
    'OFF': {'label': 'Assenza', 'hours': 'Ferie', 'color': '#e2e8f0', 'text': '#475569', 'end': 0},
    'R': {'label': 'Riposo', 'hours': '-', 'color': '#ffffff', 'text': '#cbd5e1', 'end': 0}
}

SHIFT_START = {'M': 4.5, 'C': 7.0, 'S': 14.5, 'MN': 21.5, 'R': 0, 'OFF': 0}
MONTH_NAMES = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

# --- FUNZIONI LOGICHE ---
def is_rest_ok(prev, curr, min_h):
    if prev in ['R', 'OFF'] or curr in ['R', 'OFF']: return True
    p_end = SHIFT_DETAILS[prev]['end']
    c_start = SHIFT_START[curr] + 24.0
    return (c_start - p_end) >= min_h

def generate_schedule(settings):
    results = []
    num_lic = settings['num_lic']
    
    # Inizializzazione stati dai nuovi editor
    consecutive_work = {i: 0 for i in range(1, num_lic + 1)}
    last_shift = {i: settings['default_last'] for i in range(1, num_lic + 1)}
    stats = {i: {k: 0 for k in SHIFT_DETAILS.keys()} for i in range(1, num_lic + 1)}

    # Applica Overrides dalla tabella
    for _, row in settings['df_overrides'].iterrows():
        l_id = int(row['Licenza'])
        if 1 <= l_id <= num_lic:
            last_shift[l_id] = row['Ultimo Turno']
            consecutive_work[l_id] = int(row['Gg Consecutivi'])

    curr_y, curr_m = settings['start_y'], settings['start_m']
    end_total = settings['end_y'] * 12 + settings['end_m']

    while (curr_y * 12 + curr_m) <= end_total:
        days_in_m = (date(curr_y, curr_m % 12 + 1, 1) - timedelta(days=1)).day if curr_m < 12 else 31
        month_matrix = {i: {} for i in range(1, num_lic + 1)}

        for day in range(1, days_in_m + 1):
            available = list(range(1, num_lic + 1))
            
            # 1. Gestione Assenze (dalla tabella)
            for _, row in settings['df_absences'].iterrows():
                l_id = int(row['Licenza'])
                if l_id in available and int(row['Inizio']) <= day <= int(row['Fine']):
                    month_matrix[l_id][day] = 'OFF'
                    stats[l_id]['OFF'] += 1
                    consecutive_work[l_id] = 0
                    last_shift[l_id] = 'OFF'
                    available.remove(l_id)

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

            # 4. Riposo per i restanti
            for lic in available:
                month_matrix[lic][day] = 'R'
                stats[lic]['R'] += 1
                consecutive_work[lic] = 0
                last_shift[lic] = 'R'

        results.append({'year': curr_y, 'month': curr_m, 'df': pd.DataFrame(month_matrix).T})
        curr_m += 1
        if curr_m > 12: curr_m = 1; curr_y += 1
            
    return results

# --- INTERFACCIA ---
with st.sidebar:
    st.title("🚖 Shift Manager V2")
    num_lic = st.number_input("Totale Licenze", 1, 50, 30)
    
    st.subheader("📅 Periodo")
    c1, c2 = st.columns(2)
    start_m = c1.selectbox("Mese Inizio", range(1, 13), format_func=lambda x: MONTH_NAMES[x-1])
    start_y = c2.selectbox("Anno Inizio", [2025, 2026], index=1)
    
    st.subheader("⚙️ Parametri")
    min_rest = st.select_slider("Riposo (ore)", options=[9, 11, 12, 14], value=11)
    allow_rest = st.toggle("Regola 6 giorni", value=True)
    
    st.subheader("📊 Quote Giornaliere")
    mq1, mq2 = st.columns(2)
    m_c = mq1.number_input("M", 0, 20, 9)
    c_c = mq2.number_input("C", 0, 20, 9)
    s_c = mq1.number_input("S", 0, 20, 9)
    mn_c = mq2.number_input("MN", 0, 5, 1)

    st.subheader("🔄 Stato Iniziale")
    default_last = st.selectbox("Ultimo turno default", ['R', 'M', 'C', 'S', 'MN'])
    df_over_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Ultimo Turno", "Gg Consecutivi"]),
        num_rows="dynamic", hide_index=True,
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic),
            "Ultimo Turno": st.column_config.SelectboxColumn(options=['M','C','S','MN','R']),
            "Gg Consecutivi": st.column_config.NumberColumn(min_value=0, max_value=6)
        }
    )

    st.subheader("🏖️ Assenze")
    df_abs_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Inizio", "Fine"]),
        num_rows="dynamic", hide_index=True,
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic),
            "Inizio": st.column_config.NumberColumn(min_value=1, max_value=31),
            "Fine": st.column_config.NumberColumn(min_value=1, max_value=31)
        }
    )

settings = {
    'start_m': start_m, 'start_y': start_y, 'end_m': start_m, 'end_y': start_y,
    'num_lic': num_lic, 'min_rest': min_rest, 'allow_rest': allow_rest,
    'm_c': m_c, 'c_c': c_c, 's_c': s_c, 'mn_c': mn_c,
    'df_overrides': df_over_input, 'df_absences': df_abs_input, 'default_last': default_last
}

# Calcolo e Visualizzazione
if st.sidebar.button("Genera Turni"):
    results = generate_schedule(settings)
    active_res = results[0]
    
    st.title(f"Calendario: {MONTH_NAMES[active_res['month']-1]} {active_res['year']}")
    
    def style_cells(val):
        color = SHIFT_DETAILS.get(val, {}).get('color', '#ffffff')
        text = SHIFT_DETAILS.get(val, {}).get('text', '#000000')
        return f'background-color: {color}; color: {text}; font-weight: bold; text-align: center'

    st.dataframe(active_res['df'].style.applymap(style_cells), use_container_width=True, height=600)
    
    # Export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        active_res['df'].to_excel(writer, sheet_name="Turni")
    st.download_button("📥 Scarica Excel", buffer.getvalue(), "Turni.xlsx")
