import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================================================
# BANCO DE DADOS
# =========================================================
conn = sqlite3.connect("auditoria.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS auditorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,
    codigo TEXT,
    descricao TEXT,
    secao TEXT,
    peso_real REAL,
    peso_sistema REAL,
    diferenca REAL,
    observacao TEXT
)
""")
conn.commit()

# =========================================================
# TABELA SIMULADA DE PRODUTOS (EXEMPLO)
# =========================================================
produtos = pd.DataFrame([
    {"id": 1, "codigo": "001", "descricao": "Banana", "secao": "FLV", "peso_sistema": 20.0},
    {"id": 2, "codigo": "002", "descricao": "Maçã", "secao": "FLV", "peso_sistema": 15.0},
    {"id": 3, "codigo": "003", "descricao": "Tomate", "secao": "FLV", "peso_sistema": 18.0},
])

st.set_page_config(page_title="Auditoria FLV", layout="wide")

st.title("🍌 Auditoria de Produtos FLV")

# =========================================================
# LOOP DOS PRODUTOS PARA AUDITORIA
# =========================================================
for i, row in produtos.iterrows():
    with st.expander(f"{row['descricao']} ({row['codigo']}) - Sistema: {row['peso_sistema']} kg"):
        peso_real = st.number_input("Peso real (kg)", key=f"peso_{row['id']}", min_value=0.0, step=0.01)
        observ = st.text_input("Observação", key=f"obs_{row['id']}")

        if st.button("💾 Salvar Auditoria", key=f"btn_{row['id']}"):
            diferenca = peso_real - row['peso_sistema']
            data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO auditorias (data_hora, codigo, descricao, secao, peso_real, peso_sistema, diferenca, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data_hora, row['codigo'], row['descricao'], row['secao'], peso_real, row['peso_sistema'], diferenca, observ))
            conn.commit()

            # Notificação rápida
            if diferenca != 0:
                st.toast(f"⚠️ Divergência de {diferenca:.2f} kg no produto {row['descricao']}", icon="⚠️")
            else:
                st.toast(f"✅ Produto {row['descricao']} sem divergência", icon="✅")

# =========================================================
# VISUALIZAR AUDITORIAS
# =========================================================
st.subheader("📋 Histórico de Auditorias")
auditorias = pd.read_sql_query("SELECT * FROM auditorias ORDER BY id DESC", conn)
st.dataframe(auditorias, use_container_width=True)

# =========================================================
# CALCULADORA ESTILO WINDOWS
# =========================================================
with st.sidebar.expander("🧮 Calculadora"):
    st.markdown("### Calculadora (estilo Windows)")

    if "calc_display" not in st.session_state:
        st.session_state.calc_display = ""

    def press(btn):
        if btn == "C":
            st.session_state.calc_display = ""
        elif btn == "=":
            try:
                expr = st.session_state.calc_display.replace("×", "*").replace("÷", "/")
                st.session_state.calc_display = str(eval(expr))
            except:
                st.session_state.calc_display = "Erro"
        else:
            st.session_state.calc_display += btn

    st.text_input("Display", value=st.session_state.calc_display, key="disp", disabled=True)

    # Layout dos botões
    buttons = [
        ["7", "8", "9", "÷"],
        ["4", "5", "6", "×"],
        ["1", "2", "3", "-"],
        ["0", ".", "=", "+"],
        ["C"]
    ]

    for row in buttons:
        cols = st.columns(len(row))
        for i, btn in enumerate(row):
            if cols[i].button(btn, key=f"btn_{btn}"):
                press(btn)
