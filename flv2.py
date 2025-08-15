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

# CALCULADORA FLUTUANTE
with st.sidebar.expander("🧮 Calculadora"):
    st.markdown("Simples como a calculadora padrão do Windows.")
    calc_col1, calc_col2 = st.columns(2)
    with calc_col1:
        num1 = st.number_input("Valor 1", key="calc1", label_visibility="collapsed", placeholder="0")
    with calc_col2:
        num2 = st.number_input("Valor 2", key="calc2", label_visibility="collapsed", placeholder="0")
    operacao = st.selectbox("Operação", ["+", "-", "×", "÷"], key="operacao")
    if operacao == "+":
        resultado = num1 + num2
    elif operacao == "-":
        resultado = num1 - num2
    elif operacao == "×":
        resultado = num1 * num2
    elif operacao == "÷":
        resultado = num1 / num2 if num2 != 0 else "Erro"
    st.text_input("Resultado", value=str(resultado), disabled=True)

# UPLOAD DA BASE DE PRODUTOS
with st.expander("📥 Upload da base de produtos (.xlsx)"):
    file = st.file_uploader("Carregue um arquivo com as colunas: codigo, descricao, secao", type=["xlsx"])
    if file:
        df = pd.read_excel(file)
        df.columns = [col.lower() for col in df.columns]
        df.to_sql("produtos", conn, if_exists="replace", index=False)
        st.success("✅ Base de produtos atualizada com sucesso!")

# ABAS
aba = st.sidebar.radio("Escolha uma opção:", ["📥 Lançar Pesagens (Prevenção)", "🧾 Auditar Recebimento"])

# ============================================
# PESAGEM PREVENÇÃO
# ============================================
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

# ============================================
# AUDITORIA
# ============================================
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
                                st.success("✅ Auditoria salva com sucesso!")

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
