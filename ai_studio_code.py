import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Taxi Shift Manager Pro",
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
    'OFF': {'label': 'Assenza', 'hours': 'Ferie/Sosp.', 'color': '#e2e8f0', 'text': '#475569', 'end': 0},
    'R': {'label': 'Riposo', 'hours': '-', 'color': '#ffffff', 'text': '#cbd5e1', 'end': 0}
}

SHIFT_START = {'M': 4.5, 'C': 7.0, 'S': 14.5, 'MN': 21.5, 'R': 0, 'OFF': 0}
MONTH_NAMES = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

# --- MOTORE DI CALCOLO ---

def is_rest_ok(prev, curr, min_h):
    if prev in ['R', 'OFF'] or curr in ['R', 'OFF']: return True
    p_end = SHIFT_DETAILS[prev]['end']
    c_start = SHIFT_START[curr] + 24.0
    return (c_start - p_end) >= min_h

def generate_schedule(settings):
    results = []
    alerts = []
    num_lic = settings['num_lic']
    
    consecutive_work = {i: 0 for i in range(1, num_lic + 1)}
    last_shift = {i: settings['default_last'] for i in range(1, num_lic + 1)}
    stats = {i: {k: 0 for k in SHIFT_DETAILS.keys() if k not in ['R', 'OFF']} for i in range(1, num_lic + 1)}

    # Processo dati iniziali (Overrides)
    df_over = settings['df_overrides'].dropna(subset=['Licenza', 'Ultimo Turno'])
    for _, row in df_over.iterrows():
        try:
            l_id = int(row['Licenza'])
            if 1 <= l_id <= num_lic:
                last_shift[l_id] = row['Ultimo Turno']
                consecutive_work[l_id] = int(row.get('Gg Consecutivi', 0))
        except: continue

    # Processo Assenze
    df_abs = settings['df_absences'].dropna(subset=['Licenza', 'Inizio', 'Fine'])
    abs_list = []
    for _, row in df_abs.iterrows():
        try:
            abs_list.append({'id': int(row['Licenza']), 'start': int(row['Inizio']), 'end': int(row['Fine'])})
        except: continue

    curr_y, curr_m = settings['start_y'], settings['start_m']
    days_in_m = (date(curr_y, curr_m % 12 + 1, 1) - timedelta(days=1)).day if curr_m < 12 else 31
    
    month_matrix = {i: {} for i in range(1, num_lic + 1)}

    for day in range(1, days_in_m + 1):
        available = list(range(1, num_lic + 1))
        assigned_today = {'M': 0, 'C': 0, 'S': 0, 'MN': 0}
        
        # 1. Assenze
        for a in abs_list:
            if a['id'] in available and a['start'] <= day <= a['end']:
                month_matrix[a['id']][day] = 'OFF'
                consecutive_work[a['id']] = 0
                last_shift[a['id']] = 'OFF'
                available.remove(a['id'])

        # 2. Riposo 6gg
        if settings['allow_rest']:
            for lic in list(available):
                if consecutive_work[lic] >= 6:
                    month_matrix[lic][day] = 'R'
                    consecutive_work[lic] = 0
                    last_shift[lic] = 'R'
                    available.remove(lic)

        # 3. Assegnazione
        to_assign = (['MN'] * settings['mn_c'] + ['M'] * settings['m_c'] + 
                     ['C'] * settings['c_c'] + ['S'] * settings['s_c'])
        
        for stype in to_assign:
            if not available: break
            available.sort(key=lambda x: stats[x][stype])
            
            found = next((lic for lic in available if is_rest_ok(last_shift[lic], stype, settings['min_rest'])), None)
            if found:
                month_matrix[found][day] = stype
                stats[found][stype] += 1
                assigned_today[stype] += 1
                consecutive_work[found] += 1
                last_shift[found] = stype
                available.remove(found)

        # Radar Conflitti: verifica sottocopertura
        req = {'M': settings['m_c'], 'C': settings['c_c'], 'S': settings['s_c'], 'MN': settings['mn_c']}
        for k, v in req.items():
            if assigned_today[k] < v:
                alerts.append({'Giorno': day, 'Turno': k, 'Richiesti': v, 'Assegnati': assigned_today[k]})

        # Riposo rimanenti
        for lic in available:
            month_matrix[lic][day] = 'R'
            consecutive_work[lic] = 0
            last_shift[lic] = 'R'

    df_final = pd.DataFrame(month_matrix).T
    df_stats = pd.DataFrame(stats).T
    
    return df_final, df_stats, alerts

# --- INTERFACCIA ---

with st.sidebar:
    st.title("🚖 Gestione Turni")
    st.divider()
    num_lic = st.number_input("Licenze totali", 1, 50, 30)
    
    st.subheader("📅 Periodo")
    c1, c2 = st.columns(2)
    start_m = c1.selectbox("Mese", range(1, 13), format_func=lambda x: MONTH_NAMES[x-1])
    start_y = c2.selectbox("Anno", [2025, 2026], index=1)
    
    st.subheader("📊 Fabbisogno")
    mq1, mq2 = st.columns(2)
    m_c = mq1.number_input("M", 0, 20, 9)
    c_c = mq2.number_input("C", 0, 20, 9)
    s_c = mq1.number_input("S", 0, 20, 9)
    mn_c = mq2.number_input("MN", 0, 5, 1)

    st.subheader("🔄 Stato Iniziale")
    df_over_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Ultimo Turno", "Gg Consecutivi"]),
        num_rows="dynamic", hide_index=True,
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic, format="%d"),
            "Ultimo Turno": st.column_config.SelectboxColumn(options=['M','C','S','MN','R']),
            "Gg Consecutivi": st.column_config.NumberColumn(min_value=0, max_value=6, format="%d")
        }
    )

    st.subheader("🏖️ Assenze")
    df_abs_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Inizio", "Fine"]),
        num_rows="dynamic", hide_index=True,
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic, format="%d"),
            "Inizio": st.column_config.NumberColumn(min_value=1, max_value=31, format="%d"),
            "Fine": st.column_config.NumberColumn(min_value=1, max_value=31, format="%d")
        }
    )

if st.sidebar.button("🚀 Genera Analisi e Turni"):
    settings = {
        'start_m': start_m, 'start_y': start_y, 'num_lic': num_lic,
        'm_c': m_c, 'c_c': c_c, 's_c': s_c, 'mn_c': mn_c,
        'df_overrides': df_over_input, 'df_absences': df_abs_input,
        'default_last': 'R', 'min_rest': 11, 'allow_rest': True
    }
    
    df_turni, df_stats, alerts = generate_schedule(settings)
    
    tab1, tab2, tab3 = st.tabs(["📅 Calendario Turni", "📈 Analisi Equità", "🚨 Radar Conflitti"])
    
    with tab1:
        st.header(f"Tabellone {MONTH_NAMES[start_m-1]} {start_y}")
        def style_cells(val):
            color = SHIFT_DETAILS.get(val, {}).get('color', '#ffffff')
            text = SHIFT_DETAILS.get(val, {}).get('text', '#000000')
            return f'background-color: {color}; color: {text}; font-weight: bold; text-align: center'
        st.dataframe(df_turni.style.applymap(style_cells), use_container_width=True, height=600)
        
        # Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_turni.to_excel(writer, sheet_name="Turni")
        st.download_button("📥 Scarica Excel", buffer.getvalue(), "Turni_Taxi.xlsx")

    with tab2:
        st.header("Distribuzione dei Turni (Telemetria)")
        st.info("Questo grafico mostra quanti turni di ogni tipo sono stati assegnati a ciascuna licenza. Una distribuzione piatta indica massima equità.")
        st.bar_chart(df_stats)
        
        st.subheader("Dettaglio Statistico")
        st.table(df_stats)

    with tab3:
        st.header("Monitoraggio Copertura")
        if not alerts:
            st.success("✅ Nessun conflitto rilevato. Tutte le quote giornaliere sono coperte.")
        else:
            st.error(f"⚠️ Rilevati {len(alerts)} problemi di copertura.")
            df_alerts = pd.DataFrame(alerts)
            st.warning("I seguenti giorni presentano una carenza di auto rispetto alla quota richiesta:")
            st.table(df_alerts)
            st.info("Suggerimento: Controlla le assenze inserite o riduci il fabbisogno giornaliero (M/C/S/MN) nel sidebar.")

    # Legenda
    with st.expander("ℹ️ Legenda"):
        cols = st.columns(6)
        for i, (k, v) in enumerate(SHIFT_DETAILS.items()):
            with cols[i]:
                st.markdown(f"<div style='background-color:{v['color']}; color:{v['text']}; padding:10px; border-radius:10px; text-align:center'><b>{k}</b><br><small>{v['label']}</small></div>", unsafe_allow_html=True)
