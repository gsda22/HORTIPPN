import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from io import BytesIO
from zoneinfo import ZoneInfo  # Para horário de Brasília

# CONFIG
st.set_page_config(page_title="Recebimento FLV", layout="wide")

# LOGO E CABEÇALHO
st.image("logo.png", width=150)
st.markdown("<h1 style='text-align: center; color: #1565c0;'>📦 Sistema de Recebimento de FLV</h1>", unsafe_allow_html=True)

# CONEXÃO COM O BANCO
conn = sqlite3.connect("recebimento_flv.db", check_same_thread=False)
cursor = conn.cursor()

# CRIAÇÃO DAS TABELAS
cursor.execute("""
CREATE TABLE IF NOT EXISTS produtos (
    codigo TEXT PRIMARY KEY,
    descricao TEXT,
    secao TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pesagens_prevencao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,
    codigo TEXT,
    descricao TEXT,
    secao TEXT,
    peso_real REAL,
    observacao TEXT
)
""")

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
# CALCULADORA FLUTUANTE ESTILO WINDOWS (corrigida)
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

    # Layout dos botões (igual Windows)
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

# =========================================================
# UPLOAD DA BASE DE PRODUTOS
# =========================================================
with st.expander("📥 Upload da base de produtos (.xlsx)"):
    file = st.file_uploader("Carregue um arquivo com as colunas: codigo, descricao, secao", type=["xlsx"])
    if file:
        df = pd.read_excel(file)
        df.columns = [col.lower() for col in df.columns]
        df.to_sql("produtos", conn, if_exists="replace", index=False)
        st.success("✅ Base de produtos atualizada com sucesso!")

# =========================================================
# ABAS
# =========================================================
aba = st.sidebar.radio("Escolha uma opção:", ["📥 Lançar Pesagens (Prevenção)", "🧾 Auditar Recebimento"])

# =========================================================
# PESAGEM PREVENÇÃO
# =========================================================
if aba == "📥 Lançar Pesagens (Prevenção)":
    st.markdown("## 📥 Lançar Pesagens - Prevenção")
    codigo = st.text_input("Código do Produto (interno)", max_chars=10)

    descricao = ""
    secao = ""

    if codigo:
        cursor.execute("SELECT descricao, secao FROM produtos WHERE codigo = ?", (codigo,))
        result = cursor.fetchone()
        if result:
            descricao, secao = result
            st.success(f"Produto: {descricao} | Seção: {secao}")
        else:
            st.warning("Produto não encontrado. Preencha os campos abaixo para cadastrar novo.")
            descricao = st.text_input("Descrição")
            secao = st.text_input("Seção")

    peso_real = st.number_input("Peso Real da Pesagem (kg)", step=0.01)
    observacao = st.text_input("Observações (opcional)")

    if st.button("✅ Registrar Pesagem"):
        if not descricao or not secao:
            st.error("Preencha todos os campos obrigatórios.")
        else:
            # Horário de Brasília
            data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")

            # Cadastra novo produto se necessário
            cursor.execute("SELECT 1 FROM produtos WHERE codigo = ?", (codigo,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO produtos (codigo, descricao, secao) VALUES (?, ?, ?)",
                               (codigo, descricao, secao))

            # Grava pesagem
            cursor.execute("""
                INSERT INTO pesagens_prevencao (data_hora, codigo, descricao, secao, peso_real, observacao)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data_hora, codigo, descricao, secao, peso_real, observacao))
            conn.commit()
            st.success("✅ Pesagem registrada com sucesso!")

    st.markdown("### 📋 Últimas Pesagens Lançadas")
    df_pesagens = pd.read_sql_query(
        "SELECT * FROM pesagens_prevencao ORDER BY data_hora DESC LIMIT 50", conn
    ).iloc[::-1]  # Mantém as últimas 50 mas em ordem de coleta
    if not df_pesagens.empty:
        for idx, row in df_pesagens.iterrows():
            with st.expander(f"🗂️ {row['data_hora']} | {row['codigo']} - {row['descricao']}"):
                st.write(f"**Peso Real:** {row['peso_real']} kg")
                st.write(f"**Observação:** {row['observacao']}")
                if st.button("❌ Excluir", key=f"del_{row['id']}"):
                    cursor.execute("DELETE FROM pesagens_prevencao WHERE id = ?", (row['id'],))
                    conn.commit()
                    st.warning("Pesagem excluída. Recarregue a página para atualizar.")

# =========================================================
# AUDITORIA
# =========================================================
elif aba == "🧾 Auditar Recebimento":
    st.markdown("## 🧾 Auditoria de Recebimento")
    col1, col2 = st.columns(2)
    with col1:
        data_inicio = st.date_input("De", value=date.today())
    with col2:
        data_fim = st.date_input("Até", value=date.today())

    if data_inicio > data_fim:
        st.error("⚠️ A data inicial não pode ser maior que a final.")
    else:
        query = """
        SELECT * FROM pesagens_prevencao
        WHERE substr(data_hora, 1, 10) BETWEEN ? AND ?
        ORDER BY data_hora
        """
        df_auditar = pd.read_sql_query(query, conn, params=(str(data_inicio), str(data_fim)))
        
        if df_auditar.empty:
            st.info("Nenhuma pesagem encontrada no período.")
        else:
            # Criar cards em duas colunas
            for i in range(0, len(df_auditar), 2):
                cols = st.columns(2)
                for j in range(2):
                    if i+j < len(df_auditar):
                        row = df_auditar.iloc[i+j]
                        with cols[j]:
                            st.markdown(f"### 📦 {row['codigo']} - {row['descricao']}")
                            st.write(f"**Seção:** {row['secao']}")
                            st.write(f"**Peso Real:** {row['peso_real']} kg")
                            peso_sistema = st.number_input(f"Peso Sistema", key=f"sistema_{row['id']}", step=0.01)
                            observ = st.text_input("Observações", key=f"obs_{row['id']}")
                            if st.button("💾 Salvar Auditoria", key=f"btn_{row['id']}"):
                                diferenca = row['peso_real'] - peso_sistema
                                data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
                                cursor.execute("""
                                    INSERT INTO auditorias (data_hora, codigo, descricao, secao, peso_real, peso_sistema, diferenca, observacao)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (data_hora, row['codigo'], row['descricao'], row['secao'], row['peso_real'], peso_sistema, diferenca, observ))
                                conn.commit()

                                # Pop-up com divergência
                                with st.modal("📊 Resultado da Auditoria"):
                                    st.write(f"**Produto:** {row['descricao']}")
                                    st.write(f"**Peso Real:** {row['peso_real']} kg")
                                    st.write(f"**Peso Sistema:** {peso_sistema} kg")
                                    st.write(f"**Diferença:** {diferenca:.2f} kg")

                                    if diferenca != 0:
                                        st.error("⚠️ Divergência encontrada!")
                                    else:
                                        st.success("✅ Nenhuma divergência.")

                                    if st.button("OK, entendi", key=f"close_{row['id']}"):
                                        st.rerun()

    st.markdown("### 📊 Relatório de Divergências Auditadas")
    filtro_inicio = st.date_input("📆 De (para exportação)", key="data1", value=date.today())
    filtro_fim = st.date_input("📆 Até (para exportação)", key="data2", value=date.today())

    df_auditorias = pd.read_sql_query("""
        SELECT * FROM auditorias
        WHERE substr(data_hora, 1, 10) BETWEEN ? AND ?
        ORDER BY data_hora DESC
    """, conn, params=(str(filtro_inicio), str(filtro_fim)))

    st.dataframe(df_auditorias, use_container_width=True)

    # Exportar para Excel
    if not df_auditorias.empty:
        buffer = BytesIO()
        df_auditorias.to_excel(buffer, index=False)
        st.download_button("📥 Baixar Excel das Auditorias", buffer.getvalue(), file_name="auditorias_recebimento.xlsx")
