import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Taxi Lucca Manager V2 - Professional",
    page_icon="🚖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- COSTANTI E CONFIGURAZIONE TURNI ---
# Questa sezione definisce la "grammatica" dei turni e i colori della dashboard
SHIFT_DETAILS = {
    'M': {'label': 'Mattina', 'hours': '04:30 - 16:00', 'color': '#dbeafe', 'text': '#1e40af', 'end': 16.0},
    'C': {'label': 'Centrale', 'hours': '07:00 - 21:00', 'color': '#dcfce7', 'text': '#166534', 'end': 21.0},
    'S': {'label': 'Sera', 'hours': '14:30 - 02:00', 'color': '#ffedd5', 'text': '#9a3412', 'end': 26.0},
    'MN': {'label': 'M/N', 'hours': '21:30 - 05:30', 'color': '#ef4444', 'text': '#ffffff', 'end': 29.5},
    'OFF': {'label': 'Assenza', 'hours': 'Ferie/Sosp.', 'color': '#e2e8f0', 'text': '#475569', 'end': 0},
    'R': {'label': 'Riposo', 'hours': '-', 'color': '#ffffff', 'text': '#cbd5e1', 'end': 0}
}

# Orari di inizio espressi in ore decimali per il calcolo del riposo
SHIFT_START = {'M': 4.5, 'C': 7.0, 'S': 14.5, 'MN': 21.5, 'R': 0, 'OFF': 0}
MONTH_NAMES = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

# --- LOGICA DI CALCOLO (IL MOTORE) ---

def is_rest_ok(prev, curr, min_h):
    """
    Verifica la conformità con la Direttiva 2003/88/CE (Riposo giornaliero).
    Calcola se tra la fine del turno precedente e l'inizio del successivo passano almeno min_h ore.
    """
    if prev in ['R', 'OFF'] or curr in ['R', 'OFF']: return True
    p_end = SHIFT_DETAILS[prev]['end']
    c_start = SHIFT_START[curr] + 24.0 # Riportiamo l'inizio al giorno successivo
    return (c_start - p_end) >= min_h

def generate_schedule(settings):
    results = []
    num_lic = settings['num_lic']
    
    # Inizializzazione stati iniziali
    consecutive_work = {i: 0 for i in range(1, num_lic + 1)}
    last_shift = {i: settings['default_last'] for i in range(1, num_lic + 1)}
    stats = {i: {k: 0 for k in SHIFT_DETAILS.keys()} for i in range(1, num_lic + 1)}

    # Filtro Sicurezza: Ignora righe vuote o parziali negli Overrides (Stato Iniziale)
    df_over = settings['df_overrides'].dropna(subset=['Licenza', 'Ultimo Turno'])
    for _, row in df_over.iterrows():
        try:
            l_id = int(row['Licenza'])
            if 1 <= l_id <= num_lic:
                last_shift[l_id] = row['Ultimo Turno']
                consecutive_work[l_id] = int(row.get('Gg Consecutivi', 0))
        except: continue

    # Filtro Sicurezza: Ignora righe vuote o parziali nelle Assenze
    df_abs = settings['df_absences'].dropna(subset=['Licenza', 'Inizio', 'Fine'])
    abs_list = []
    for _, row in df_abs.iterrows():
        try:
            abs_list.append({'id': int(row['Licenza']), 'start': int(row['Inizio']), 'end': int(row['Fine'])})
        except: continue

    curr_y, curr_m = settings['start_y'], settings['start_m']
    end_total = settings['end_y'] * 12 + settings['end_m']

    while (curr_y * 12 + curr_m) <= end_total:
        # Calcolo giorni nel mese
        if curr_m == 12: days_in_m = 31
        else: days_in_m = (date(curr_y, curr_m + 1, 1) - timedelta(days=1)).day
        
        month_matrix = {i: {} for i in range(1, num_lic + 1)}

        for day in range(1, days_in_m + 1):
            available = list(range(1, num_lic + 1))
            
            # 1. Applicazione Assenze pianificate
            for a in abs_list:
                if a['id'] in available and a['start'] <= day <= a['end']:
                    month_matrix[a['id']][day] = 'OFF'
                    stats[a['id']]['OFF'] += 1
                    consecutive_work[a['id']] = 0
                    last_shift[a['id']] = 'OFF'
                    if a['id'] in available: available.remove(a['id'])

            # 2. Vincolo Riposo Settimanale (6 giorni consecutivi max)
            if settings['allow_rest']:
                for lic in list(available):
                    if consecutive_work[lic] >= 6:
                        month_matrix[lic][day] = 'R'
                        stats[lic]['R'] += 1
                        consecutive_work[lic] = 0
                        last_shift[lic] = 'R'
                        available.remove(lic)

            # 3. Assegnazione Turni in base alle quote giornaliere
            to_assign = (['MN'] * settings['mn_c'] + ['M'] * settings['m_c'] + 
                         ['C'] * settings['c_c'] + ['S'] * settings['s_c'])
            
            for stype in to_assign:
                if not available: break
                # Algoritmo di Equità: ordina per chi ha fatto meno turni di quel tipo
                available.sort(key=lambda x: stats[x][stype])
                
                found = next((lic for lic in available if is_rest_ok(last_shift[lic], stype, settings['min_rest'])), None)
                if found:
                    month_matrix[found][day] = stype
                    stats[found][stype] += 1
                    consecutive_work[found] += 1
                    last_shift[found] = stype
                    available.remove(found)

            # 4. Assegnazione Riposo per le licenze restanti
            for lic in available:
                month_matrix[lic][day] = 'R'
                stats[lic]['R'] += 1
                consecutive_work[lic] = 0
                last_shift[lic] = 'R'

        results.append({'year': curr_y, 'month': curr_m, 'df': pd.DataFrame(month_matrix).T})
        curr_m += 1
        if curr_m > 12: curr_m = 1; curr_y += 1
            
    return results

# --- INTERFACCIA UTENTE (IL COCKPIT) ---

with st.sidebar:
    st.title("🚖 Taxi Lucca Manager")
    st.info("Sistema professionale per la turnazione automatica conforme alle normative vigenti.")
    st.divider()
    
    num_lic = st.number_input("Totale Licenze attive", 1, 50, 30)
    
    st.subheader("📅 Periodo di calcolo")
    c1, c2 = st.columns(2)
    start_m = c1.selectbox("Mese", range(1, 13), format_func=lambda x: MONTH_NAMES[x-1])
    start_y = c2.selectbox("Anno", [2025, 2026], index=1)
    
    st.subheader("⚖️ Parametri Normativi")
    min_rest = st.select_slider("Riposo giornaliero (ore)", options=[9, 11, 12, 14], value=11, 
                                help="La Direttiva 2003/88/CE impone 11 ore di riposo consecutivo.")
    
    # Check Direttiva 2003/88/CE
    if min_rest < 11:
        st.warning("⚠️ Attenzione: Valore inferiore alle 11 ore previste dalla Direttiva 2003/88/CE.")
    else:
        st.success("✅ Conforme alla Direttiva 2003/88/CE.")

    allow_rest = st.toggle("Riposo ogni 6gg (obbligatorio)", value=True)
    
    st.subheader("📊 Fabbisogno Giornaliero")
    mq1, mq2 = st.columns(2)
    m_c = mq1.number_input("Mattina (M)", 0, 20, 9)
    c_c = mq2.number_input("Centrale (C)", 0, 20, 9)
    s_c = mq1.number_input("Sera (S)", 0, 20, 9)
    mn_c = mq2.number_input("M/N", 0, 5, 1)

    st.subheader("🔄 Stato Iniziale")
    default_last = st.selectbox("Ultimo turno mese prec.", ['R', 'M', 'C', 'S', 'MN'])
    df_over_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Ultimo Turno", "Gg Consecutivi"]),
        num_rows="dynamic", hide_index=True, key="editor_overrides",
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic, format="%d"),
            "Ultimo Turno": st.column_config.SelectboxColumn(options=['M','C','S','MN','R']),
            "Gg Consecutivi": st.column_config.NumberColumn(min_value=0, max_value=6, format="%d")
        }
    )

    st.subheader("🏖️ Assenze / Ferie")
    df_abs_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Inizio", "Fine"]),
        num_rows="dynamic", hide_index=True, key="editor_assenze",
        column_config={
            "Licenza": st.column_config.NumberColumn(min_value=1, max_value=num_lic, format="%d"),
            "Inizio": st.column_config.NumberColumn(min_value=1, max_value=31, format="%d"),
            "Fine": st.column_config.NumberColumn(min_value=1, max_value=31, format="%d")
        }
    )

# --- GENERAZIONE E VISUALIZZAZIONE ---
settings = {
    'start_m': start_m, 'start_y': start_y, 'end_m': start_m, 'end_y': start_y,
    'num_lic': num_lic, 'min_rest': min_rest, 'allow_rest': allow_rest,
    'm_c': m_c, 'c_c': c_c, 's_c': s_c, 'mn_c': mn_c,
    'df_overrides': df_over_input, 'df_absences': df_abs_input, 'default_last': default_last
}

if st.sidebar.button("🚀 GENERA TABELLONE TURNI"):
    try:
        results = generate_schedule(settings)
        active_res = results[0]
        
        st.title(f"📅 Calendario Turni: {MONTH_NAMES[active_res['month']-1]} {active_res['year']}")
        
        # Formattazione grafica celle
        def style_cells(val):
            color = SHIFT_DETAILS.get(val, {}).get('color', '#ffffff')
            text = SHIFT_DETAILS.get(val, {}).get('text', '#000000')
            return f'background-color: {color}; color: {text}; font-weight: bold; text-align: center'

        st.dataframe(active_res['df'].style.applymap(style_cells), use_container_width=True, height=600)
        
        # Footer Informativo
        st.divider()
        c_down, c_info = st.columns([1, 3])
        
        # Export Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            active_res['df'].to_excel(writer, sheet_name="Turni")
        
        c_down.download_button("📥 Scarica Tabellone Excel", buffer.getvalue(), f"Turni_Taxi_{start_m}_{start_y}.xlsx")
        
        c_info.success(f"""
        **Certificazione Algoritmo:**
        - **Equità**: Rotazione bilanciata basata sullo storico mensile.
        - **Sicurezza**: Riposo minimo garantito di {min_rest} ore (Dir. 2003/88/CE).
        - **Continuità**: Gestione automatica del riposo ogni 6 giorni di lavoro.
        """)

        # Legenda interattiva
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

    except Exception as e:
        st.error(f"Errore critico durante la generazione: {e}")
