# --- SEZIONE STATO INIZIALE CON AVVISO ---
    st.subheader("🔄 Stato Iniziale")
    with st.expander("❓ Come compilare lo Stato Iniziale"):
        st.caption("""
        **Usa questa tabella se vuoi che il calcolo prosegua dal mese scorso:**
        - **Licenza**: Inserisci il numero (es. 5).
        - **Ultimo Turno**: Seleziona l'ultimo fatto (M, C, S, MN o R).
        - **Gg Consecutivi**: Quanti giorni ha lavorato di fila fino a ieri? (Max 6).
        """)

    df_over_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Ultimo Turno", "Gg Consecutivi"]),
        num_rows="dynamic", hide_index=True, key="editor_overrides",
        column_config={
            "Licenza": st.column_config.NumberColumn("N°", min_value=1, max_value=num_lic, help="Inserisci solo il numero della licenza"),
            "Ultimo Turno": st.column_config.SelectboxColumn("Turno", options=['M','C','S','MN','R'], help="L'ultimo turno effettuato nel mese precedente"),
            "Gg Consecutivi": st.column_config.NumberColumn("Gg", min_value=0, max_value=6, help="Giorni di lavoro consecutivi accumulati")
        }
    )

    # --- SEZIONE ASSENZE CON AVVISO ---
    st.subheader("🏖️ Assenze / Ferie")
    st.info("💡 **Istruzioni**: Inserisci una riga per ogni periodo di assenza. Es: Licenza 5, dal giorno 1 al 10.")
    
    df_abs_input = st.data_editor(
        pd.DataFrame(columns=["Licenza", "Inizio", "Fine"]),
        num_rows="dynamic", hide_index=True, key="editor_assenze",
        column_config={
            "Licenza": st.column_config.NumberColumn("N° Licenza", min_value=1, max_value=num_lic, format="%d", help="Numero della licenza assente"),
            "Inizio": st.column_config.NumberColumn("Dal giorno", min_value=1, max_value=31, format="%d", help="Giorno di inizio assenza (numero)"),
            "Fine": st.column_config.NumberColumn("Al giorno", min_value=1, max_value=31, format="%d", help="Giorno di fine assenza (numero)")
        }
    )
