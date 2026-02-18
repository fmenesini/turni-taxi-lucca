import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import io

# --- CONFIGURAZIONE E COSTANTI ---
SHIFT_DETAILS = {
    'M': {'label': 'Mattina', 'hours': '04:30 - 16:00', 'end_time': 16.0},
    'C': {'label': 'Centrale', 'hours': '07:00 - 21:00', 'end_time': 21.0},
    'S': {'label': 'Sera', 'hours': '14:30 - 02:00', 'end_time': 26.0},  # 02:00 del giorno dopo
    'MN': {'label': 'Mattina/Notte', 'hours': '21:30 - 05:30', 'end_time': 29.5}, # 05:30 del giorno dopo
    'OFF': {'label': 'Assenza', 'hours': 'Ferie/Sospensione', 'end_time': 0},
    'R': {'label': 'Riposo', 'hours': '-', 'end_time': 0}
}

SHIFT_START_TIMES = {
    'M': 4.5,
    'C': 7.0,
    'S': 14.5,
    'MN': 21.5
}

# --- LOGICA DI SCHEDULING ---
def is_rest_sufficient(prev_shift, next_shift, min_rest):
    if prev_shift in ['R', 'OFF'] or next_shift in ['R', 'OFF']:
        return True
    
    prev_end = SHIFT_DETAILS[prev_shift]['end_time']
    next_start = SHIFT_START_TIMES[next_shift] + 24.0 # Inizio nel giorno successivo
    
    return (next_start - prev_end) >= min_rest

def parse_absences(raw_str):
    absences = {}
    if not raw_str:
        return absences
    
    entries = raw_str.split(';')
    for entry in entries:
        try:
            if ':' in entry:
                lic_part, days_part = entry.split(':')
                lic_id = int(''.join(filter(str.isdigit, lic_part)))
                start_day, end_day = map(int, days_part.split('-'))
                if lic_id not in absences:
                    absences[lic_id] = []
                absences[lic_id].append((start_day, end_day))
        except:
            continue
    return absences

def generate_schedule(settings):
    results = []
    absences = parse_absences(settings['absences_raw'])
    
    # Inizializzazione stati
    consecutive_days = {i: 0 for i in range(1, settings['num_licenses'] + 1)}
    last_shift = {i: 'R' for i in range(1, settings['num_licenses'] + 1)}
    global_stats = {i: {s: 0 for s in SHIFT_DETAILS.keys()} for i in range(1, settings['num_licenses'] + 1)}

    curr_date = date(settings['start_year'], settings['start_month'], 1)
    end_date = date(settings['end_year'], settings['end_month'], 1)
    
    # Iterazione mesi
    while curr_date <= end_date:
        year, month = curr_date.year, curr_date.month
        days_in_month = pd.Period(f'{year}-{month}').days_in_month
        month_data = []

        for day in range(1, days_in_month + 1):
            daily_assignments = {i: 'R' for i in range(1, settings['num_licenses'] + 1)}
            available_licenses = list(range(1, settings['num_licenses'] + 1))

            # 1. Gestione Assenze
            for lic in list(available_licenses):
                if lic in absences:
                    for start, end in absences[lic]:
                        if start <= day <= end:
                            daily_assignments[lic] = 'OFF'
                            global_stats[lic]['OFF'] += 1
                            consecutive_days[lic] = 0
                            last_shift[lic] = 'OFF'
                            available_licenses.remove(lic)
                            break

            # 2. Gestione Riposo Obbligatorio (max 6gg)
            if settings['allow_rest']:
                for lic in list(available_licenses):
                    if consecutive_days[lic] >= 6:
                        daily_assignments[lic] = 'R'
                        global_stats[lic]['R'] += 1
                        consecutive_days[lic] = 0
                        last_shift[lic] = 'R'
                        available_licenses.remove(lic)

            # 3. Assegnazione Turni
            shifts_to_assign = (['MN'] * settings['mn_count'] + 
                                ['M'] * settings['m_count'] + 
                                ['C'] * settings['c_count'] + 
                                ['S'] * settings['s_count'])
            
            for stype in shifts_to_assign:
                if not available_licenses:
                    break
                
                # Ordinamento per equità (chi ha fatto meno quel turno)
                available_licenses.sort(key=lambda x: global_stats[x][stype])
                
                assigned = False
                for lic in available_licenses:
                    if is_rest_sufficient(last_shift[lic], stype, settings['min_rest']):
                        daily_assignments[lic] = stype
                        global_stats[lic][stype] += 1
                        consecutive_days[lic] += 1
                        last_shift[lic] = stype
                        available_licenses.remove(lic)
                        assigned = True
                        break
                
            # Chi resta fuori va in riposo
            for lic in available_licenses:
                daily_assignments[lic] = 'R'
                global_stats[lic]['R'] += 1
                consecutive_days[lic] = 0
                last_shift[lic] = 'R'

            month_data.append(daily_assignments)

        # Trasformazione in DataFrame per il mese
        df_month = pd.DataFrame(month_data, index=range(1, days_in_month + 1)).T
        df_month.index.name = 'Licenza'
        results.append({'month': month, 'year': year, 'df': df_month})
        
        # Incremento mese
        if month == 12:
            curr_date = date(year + 1, 1, 1)
        else:
            curr_date = date(year, month + 1, 1)

    return results

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Taxi Lucca Shift Manager", layout="wide")

st.title("🚖 Taxi Lucca: Shift Manager")
st.markdown("Gestione turni conforme alla **Direttiva Europea 2003/88/CE** (11h riposo).")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configurazione")
    
    with st.expander("📅 Periodo", expanded=True):
        col1, col2 = st.columns(2)
        start_m = col1.selectbox("Mese Inizio", range(1, 13), index=datetime.now().month - 1)
        start_y = col2.selectbox("Anno Inizio", [2024, 2025, 2026], index=1)
        
        end_m = col1.selectbox("Mese Fine", range(1, 13), index=datetime.now().month)
        end_y = col2.selectbox("Anno Fine", [2024, 2025, 2026], index=1)

    with st.expander("⚖️ Vincoli e Quote", expanded=True):
        min_rest = st.select_slider("Riposo Minimo (ore)", options=[8, 9, 10, 11, 12, 14], value=11)
        if min_rest < 11:
            st.warning("⚠️ Sotto le 11h non conforme a standard UE.")
            
        num_lic = st.number_input("Numero Licenze", 1, 50, 30)
        col_s1, col_s2 = st.columns(2)
        m_c = col_s1.number_input("Mattina (M)", 0, 20, 9)
        c_c = col_s2.number_input("Centrale (C)", 0, 20, 9)
        s_c = col_s1.number_input("Sera (S)", 0, 20, 9)
        mn_c = col_s2.number_input("Notte (MN)", 0, 5, 1)

    with st.expander("🏖️ Sospensioni / Ferie"):
        abs_raw = st.text_area("Formato: Licenza X: Inizio-Fine", 
                              value="Licenza 5: 1-10; Licenza 12: 15-20",
                              help="Usa il punto e virgola per separare le licenze.")

# Generazione
settings = {
    'start_year': start_y, 'start_month': start_m,
    'end_year': end_y, 'end_month': end_m,
    'num_licenses': num_lic, 'min_rest': min_rest,
    'm_count': m_c, 'c_count': c_c, 's_count': s_c, 'mn_count': mn_c,
    'absences_raw': abs_raw, 'allow_rest': True
}

all_months = generate_schedule(settings)

# Visualizzazione
if all_months:
    st.subheader(f"📅 Piano Turni")
    
    # Selettore mese visualizzato
    month_options = [f"{m['month']}/{m['year']}" for m in all_months]
    selected_month_str = st.select_slider("Seleziona Mese da Visualizzare", options=month_options)
    
    selected_idx = month_options.index(selected_month_str)
    current_df = all_months[selected_idx]['df']
    
    # Styling del DataFrame
    def color_shifts(val):
        color = 'white'
        if val == 'M': color = '#dbeafe'
        elif val == 'C': color = '#dcfce7'
        elif val == 'S': color = '#ffedd5'
        elif val == 'MN': color = '#fee2e2'
        elif val == 'OFF': color = '#f1f5f9'
        return f'background-color: {color}'

    st.dataframe(current_df.style.applymap(color_shifts), use_container_width=True, height=500)

    # Export
    st.divider()
    col_exp1, col_exp2 = st.columns([1, 4])
    
    # Preparazione file Excel in memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for m_data in all_months:
            sheet_name = f"{m_data['month']}-{m_data['year']}"
            m_data['df'].to_excel(writer, sheet_name=sheet_name)
    
    st.download_button(
        label="📥 Scarica Calendario Completo (Excel)",
        data=output.getvalue(),
        file_name=f"turni_taxi_lucca_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Legenda
st.info("""
**Legenda Turni:**
- **M**: Mattina (04:30 - 16:00)
- **C**: Centrale (07:00 - 21:00)
- **S**: Sera (14:30 - 02:00)
- **MN**: Mattina/Notte (21:30 - 05:30)
- **OFF**: Ferie o Sospensione
- **R**: Riposo
""")