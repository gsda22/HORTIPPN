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
# CAMPO DE CÁLCULO ESTILO EXCEL
# =========================================================
st.sidebar.header("📊 Campo de Cálculo")
calculo = st.sidebar.text_input("Digite sua fórmula (ex: =20+20*2-5)", value="=20+20")
if calculo.startswith("="):
    try:
        expr = calculo[1:]  # remove o "="
        resultado = eval(expr)
        st.sidebar.success(f"Resultado: {resultado}")
    except Exception as e:
        st.sidebar.error("Erro na expressão! Verifique a fórmula.")

# =========================================================
# LOOP DOS PRODUTOS PARA AUDITORIA
# =========================================================
for i, row in produtos.iterrows():
    with st.expander(f"{row['descricao']} ({row['codigo']}) - Sistema: {row['peso_sistema']} kg"):
        peso_real = st.number_input("Peso real (kg)", key=f"peso_{row['id']}", min_value=0.0, step=0.01)
        observ = st.text_input("Observação", key=f"obs_{row['id']}")

        if st.button("💾 Salvar Auditoria", key=f"btn_save_{row['id']}"):
            diferenca = peso_real - row['peso_sistema']
            data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO auditorias (data_hora, codigo, descricao, secao, peso_real, peso_sistema, diferenca, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data_hora, row['codigo'], row['descricao'], row['secao'],
                  peso_real, row['peso_sistema'], diferenca, observ))
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
