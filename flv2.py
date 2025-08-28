import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from zoneinfo import ZoneInfo
from io import BytesIO

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(page_title="Recebimento FLV", layout="wide")
st.title("📦 Sistema de Recebimento de FLV")

# =========================================================
# CONEXÃO COM BANCO DE DADOS
# =========================================================
conn = sqlite3.connect("recebimento_flv.db", check_same_thread=False)
cursor = conn.cursor()

# =========================================================
# CRIAÇÃO DAS TABELAS
# =========================================================
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
    quantidade INTEGER DEFAULT 1,
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
    quantidade INTEGER DEFAULT 1,
    peso_real REAL,
    peso_sistema REAL,
    diferenca REAL,
    observacao TEXT
)
""")
conn.commit()

# =========================================================
# CAMPO DE CÁLCULO ESTILO EXCEL
# =========================================================
st.sidebar.header("📊 Campo de Cálculo")
calculo = st.sidebar.text_input("Digite sua fórmula (ex: 20+20*2-5)", value="20+20")
try:
    resultado = eval(calculo)
    st.sidebar.success(f"Resultado: {resultado}")
except Exception as e:
    st.sidebar.error("Erro na expressão! Verifique a fórmula.")

# =========================================================
# ABAS DO SISTEMA
# =========================================================
aba = st.sidebar.radio("Escolha uma opção:", ["📥 Lançar Pesagens (Prevenção)", "🧾 Auditar Recebimento"])

# =========================================================
# PESAGEM PREVENÇÃO
# =========================================================
if aba == "📥 Lançar Pesagens (Prevenção)":
    st.header("📥 Lançar Pesagens - Prevenção")
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

        # =========================================================
        # EXPANDER COMO POPUP
        # =========================================================
        with st.expander("📦 Inserir Detalhes da Pesagem", expanded=True):
            quantidade = st.number_input("Quantidade de Itens", min_value=1, step=1, value=1)
            peso_real = st.number_input("Peso Real da Pesagem (kg)", step=0.01)
            observacao = st.text_input("Observações (opcional)")

            if st.button("✅ Registrar Pesagem", key=f"btn_{codigo}"):
                data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
                
                # Cadastra produto se necessário
                if not result and descricao and secao:
                    cursor.execute("INSERT INTO produtos (codigo, descricao, secao) VALUES (?, ?, ?)",
                                   (codigo, descricao, secao))
                
                # Grava pesagem
                cursor.execute("""
                    INSERT INTO pesagens_prevencao (data_hora, codigo, descricao, secao, quantidade, peso_real, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (data_hora, codigo, descricao, secao, quantidade, peso_real, observacao))
                conn.commit()
                st.success("✅ Pesagem registrada com sucesso!")

    # =========================================================
    # EXIBIÇÃO DAS ÚLTIMAS PESAGENS
    # =========================================================
    st.markdown("### 📋 Últimas Pesagens Lançadas")
    df_pesagens = pd.read_sql_query(
        "SELECT * FROM pesagens_prevencao ORDER BY data_hora DESC LIMIT 50", conn
    ).iloc[::-1]
    
    if not df_pesagens.empty:
        for idx, row in df_pesagens.iterrows():
            with st.expander(f"🗂️ {row['data_hora']} | {row['codigo']} - {row['descricao']}"):
                st.write(f"**Quantidade:** {row.get('quantidade', 1)} unid.")
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
    st.header("🧾 Auditoria de Recebimento")
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
            for i in range(0, len(df_auditar), 2):
                cols = st.columns(2)
                for j in range(2):
                    if i+j < len(df_auditar):
                        row = df_auditar.iloc[i+j]
                        with cols[j]:
                            st.markdown(f"### 📦 {row['codigo']} - {row['descricao']}")
                            st.write(f"**Seção:** {row['secao']}")
                            st.write(f"**Quantidade:** {row.get('quantidade', 1)} unid.")
                            st.write(f"**Peso Real:** {row['peso_real']} kg")
                            peso_sistema = st.number_input(f"Peso Sistema", key=f"sistema_{row['id']}", step=0.01)
                            observ = st.text_input("Observações", key=f"obs_{row['id']}")
                            if st.button("💾 Salvar Auditoria", key=f"btn_{row['id']}"):
                                diferenca = row['peso_real'] - peso_sistema
                                data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
                                cursor.execute("""
                                    INSERT INTO auditorias (data_hora, codigo, descricao, secao, quantidade, peso_real, peso_sistema, diferenca, observacao)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (data_hora, row['codigo'], row['descricao'], row['secao'], row.get('quantidade', 1), row['peso_real'], peso_sistema, diferenca, observ))
                                conn.commit()
                                if diferenca != 0:
                                    st.toast(f"⚠️ Divergência de {diferenca:.2f} kg no produto {row['descricao']}", icon="⚠️")
                                else:
                                    st.toast(f"✅ Produto {row['descricao']} sem divergência", icon="✅")

    st.markdown("### 📊 Relatório de Divergências Auditadas")
    filtro_inicio = st.date_input("📆 De (para exportação)", key="data1", value=date.today())
    filtro_fim = st.date_input("📆 Até (para exportação)", key="data2", value=date.today())

    df_auditorias = pd.read_sql_query("""
        SELECT * FROM auditorias
        WHERE substr(data_hora, 1, 10) BETWEEN ? AND ?
        ORDER BY data_hora DESC
    """, conn, params=(str(filtro_inicio), str(filtro_fim)))

    st.dataframe(df_auditorias, use_container_width=True)

    if not df_auditorias.empty:
        buffer = BytesIO()
        df_auditorias.to_excel(buffer, index=False)
        st.download_button("📥 Baixar Excel das Auditorias", buffer.getvalue(), file_name="auditorias_recebimento.xlsx")
