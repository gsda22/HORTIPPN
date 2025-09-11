import streamlit as st
import pandas as pd
import datetime
import io
import base64
import locale
import openpyxl
import sqlite3
import os
import pytz

# --- Configurações da página (sidebar e estilo) ---
st.set_page_config(
    page_title="Gestão de Recebimentos",
    page_icon="📦",
    layout="wide",
)

st.markdown(
    """
    <style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .sidebar .sidebar-content {
        background: #e0e0e0;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
    }
    h1, h2, h3 {
        color: #004d40;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Dicionário para traduzir o dia da semana
dias_semana = {
    'Monday': 'Segunda-feira',
    'Tuesday': 'Terça-feira',
    'Wednesday': 'Quarta-feira',
    'Thursday': 'Quinta-feira',
    'Friday': 'Sexta-feira',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}

# Define o fuso horário de Brasília
brasilia_tz = pytz.timezone('America/Sao_Paulo')

# --- Funções do Banco de Dados (SQLite) ---
DB_FILE = "gestao_recebimentos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            codigo_produto TEXT PRIMARY KEY,
            descricao_produto TEXT,
            secao_produto TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS recebimentos (
            id_recebimento INTEGER PRIMARY KEY,
            codigo_produto TEXT,
            quantidade_recebida REAL,
            condicao_produto TEXT,
            data_recebimento TEXT,
            dia_semana TEXT,
            hora_recebimento TEXT,
            foto_evidencia TEXT,
            conferente TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS auditorias (
            id_auditoria INTEGER PRIMARY KEY,
            codigo_produto TEXT,
            quantidade_sistema REAL,
            quantidade_divergente REAL,
            data_auditoria TEXT,
            auditor TEXT,
            status_divergencia TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario TEXT PRIMARY KEY,
            nome_usuario TEXT,
            tipo_acesso TEXT,
            senha TEXT
        )
    """)
    
    # Inserir usuários padrão se a tabela estiver vazia
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?)", ('admin', 'Gestor Admin', 'Gestor', 'admin'))
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?)", ('conf1', 'Conferente 1', 'Conferente', '123'))
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?)", ('prev1', 'Prevenção 1', 'Prevenção', '123'))

    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# --- Funções de Lógica ---
def get_product_info(codigo):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM produtos WHERE codigo_produto = ?", conn, params=(codigo,))
    conn.close()
    return df.iloc[0] if not df.empty else None

def save_reception(data):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO recebimentos (codigo_produto, quantidade_recebida, condicao_produto,
                                  data_recebimento, dia_semana, hora_recebimento,
                                  foto_evidencia, conferente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['codigo_produto'], data['quantidade_recebida'], data['condicao_produto'],
          data['data_recebimento'], data['dia_semana'], data['hora_recebimento'],
          data['foto_evidencia'], data['conferente']))
    conn.commit()
    conn.close()

def get_consolidated_recebimentos():
    conn = get_db_connection()
    query = "SELECT codigo_produto, SUM(quantidade_recebida) as quantidade_total_recebida FROM recebimentos GROUP BY codigo_produto"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def save_audit(data):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO auditorias (codigo_produto, quantidade_sistema, quantidade_divergente,
                                  data_auditoria, auditor, status_divergencia)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data['codigo_produto'], data['quantidade_sistema'], data['quantidade_divergente'],
          data['data_auditoria'], data['auditor'], data['status_divergencia']))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM usuarios", conn)
    conn.close()
    return df

def get_user(user_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM usuarios WHERE id_usuario = ?", conn, params=(user_id,))
    conn.close()
    return df.iloc[0] if not df.empty else None

def save_user(user_id, nome, tipo, senha):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO usuarios (id_usuario, nome_usuario, tipo_acesso, senha) VALUES (?, ?, ?, ?)", (user_id, nome, tipo, senha))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id_usuario = ?", (user_id,))
    conn.commit()
    conn.close()

# --- Funções de Interface do Usuário (UI) ---
def login_page():
    st.sidebar.image("logo.png", width=150) # Adiciona a logo na sidebar
    st.sidebar.title("Login")
    username = st.sidebar.text_input("Usuário")
    password = st.sidebar.text_input("Senha", type="password")
    
    if st.sidebar.button("Entrar"):
        user = get_user(username)
        if user is not None and user['senha'] == password:
            st.session_state.logged_in = True
            st.session_state.user_role = user['tipo_acesso']
            st.session_state.user_id = user['id_usuario']
            st.rerun()
        else:
            st.sidebar.error("Usuário ou senha incorretos.")

def main_app():
    st.sidebar.image("logo.png", width=150) # Adiciona a logo na sidebar logada
    st.sidebar.title(f"Bem-vindo, {st.session_state.user_id}!")
    st.sidebar.markdown(f"**Acesso:** {st.session_state.user_role}")
    
    # Menu de abas
    menu_items = {
        "Conferente": ["Recebimento"],
        "Prevenção": ["Auditoria", "Divergentes"],
        "Gestor": ["Recebimento", "Auditoria", "Divergentes", "Relatórios", "Gestão de Usuários"],
    }
    
    current_role = st.session_state.user_role
    selected_page = st.sidebar.radio("Navegação", menu_items.get(current_role, []))
    
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.user_id = None
        st.rerun()

    # Exibição das páginas
    st.title("Sistema de Gestão de Recebimentos 📦")
    st.image("logo.png", width=100) # Adiciona a logo no corpo principal do app
    st.markdown("---") # Adiciona uma linha para separar a logo do conteúdo

    if selected_page == "Recebimento":
        show_recebimento_page()
    elif selected_page == "Auditoria":
        show_auditoria_page()
    elif selected_page == "Divergentes":
        show_divergentes_page()
    elif selected_page == "Relatórios":
        show_relatorios_page()
    elif selected_page == "Gestão de Usuários":
        show_gestao_usuarios_page()

def show_recebimento_page():
    st.header("Coleta de Recebimento")
    
    st.subheader("Subir Base de Produtos (Excel)")
    uploaded_file = st.file_uploader("Escolha um arquivo Excel", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            conn = get_db_connection()
            # Renomeia colunas para o padrão do DB
            df = df.rename(columns={
                'codigo': 'codigo_produto',
                'descricao': 'descricao_produto',
                'secao': 'secao_produto'
            })
            # Salva no DB
            df.to_sql('produtos', conn, if_exists='replace', index=False)
            conn.close()
            st.success("Base de produtos carregada com sucesso!")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
    st.markdown("---")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Lançamento de Produto")
        with st.form("form_recebimento", clear_on_submit=True):
            codigo = st.text_input("Código do Produto", key="codigo_input").strip()
            
            with st.expander("Calculadora rápida"):
                expr = st.text_input("Insira uma expressão matemática (ex: 25+25)", key="calc_input")
                if expr:
                    try:
                        result = eval(expr)
                        st.info(f"Resultado: {result}")
                    except:
                        st.error("Expressão inválida.")

            quantidade = st.number_input("Quantidade", value=0.0, format="%.2f", min_value=0.0)
            condicao = st.radio("Condição do Produto", ('Bom', 'Ruim'))
            foto_evidencia = None
            if condicao == 'Ruim':
                uploaded_photo = st.camera_input("Tire uma foto do produto")
                if uploaded_photo:
                    foto_evidencia = base64.b64encode(uploaded_photo.read()).decode()
            
            submit_button = st.form_submit_button("Registrar Recebimento")
    
    with col2:
        st.subheader("Informações do Produto")
        if codigo:
            prod_info = get_product_info(codigo)
            if prod_info is not None:
                st.write(f"**Código:** {prod_info['codigo_produto']}")
                st.write(f"**Descrição:** {prod_info['descricao_produto']}")
                st.write(f"**Seção:** {prod_info['secao_produto']}")
            else:
                st.warning("Produto não encontrado na base. Por favor, digite as informações manualmente.")
                descricao_manual = st.text_input("Descrição (manual)")
                secao_manual = st.text_input("Seção (manual)")
                if descricao_manual and secao_manual:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO produtos VALUES (?, ?, ?)", (codigo, descricao_manual, secao_manual))
                    conn.commit()
                    conn.close()
                    st.success("Produto adicionado à base.")

    if submit_button:
        if codigo and quantidade > 0:
            now = datetime.datetime.now(brasilia_tz) 
            data_recebimento = now.strftime('%d/%m/%Y %H:%M')
            dia_semana_ingles = now.strftime('%A')
            dia_semana_br = dias_semana.get(dia_semana_ingles, dia_semana_ingles)
            
            reception_data = {
                'codigo_produto': codigo,
                'quantidade_recebida': quantidade,
                'condicao_produto': condicao,
                'data_recebimento': data_recebimento,
                'dia_semana': dia_semana_br,
                'hora_recebimento': now.strftime('%H:%M'),
                'foto_evidencia': foto_evidencia,
                'conferente': st.session_state.user_id
            }
            save_reception(reception_data)
            st.success("Recebimento registrado com sucesso!")
            st.rerun()

    st.markdown("---")
    st.subheader("Histórico de Recebimentos")
    conn = get_db_connection()
    recebimentos_df = pd.read_sql_query("SELECT * FROM recebimentos", conn)
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()

    if not recebimentos_df.empty:
        df_display = recebimentos_df.merge(produtos_df, on='codigo_produto', how='left')
        st.dataframe(df_display.drop(columns=['foto_evidencia']))
    else:
        st.info("Nenhum recebimento registrado.")

def show_auditoria_page():
    st.header("Auditoria de Recebimentos")

    # --- NOVO: SEÇÃO DE HISTÓRICO DE AUDITORIAS ---
    st.subheader("Histórico de Auditorias Realizadas")

    conn = get_db_connection()
    # Puxa todas as auditorias, não apenas as divergentes
    df_auditorias_hist = pd.read_sql_query("SELECT * FROM auditorias", conn)
    produtos_df_hist = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()

    if df_auditorias_hist.empty:
        st.info("Nenhuma auditoria foi registrada ainda.")
    else:
        # Adiciona a descrição do produto ao histórico
        df_auditorias_hist = df_auditorias_hist.merge(produtos_df_hist[['codigo_produto', 'descricao_produto']], on='codigo_produto', how='left')
        df_auditorias_hist['data_auditoria_dt'] = pd.to_datetime(df_auditorias_hist['data_auditoria'], format='%d/%m/%Y %H:%M')

        # Filtros de data
        start_date_hist = st.date_input("Data de Início", value=None, key="audit_start_date")
        end_date_hist = st.date_input("Data de Fim", value=None, key="audit_end_date")

        df_filtered_hist = df_auditorias_hist.copy()
        if start_date_hist:
            df_filtered_hist = df_filtered_hist[df_filtered_hist['data_auditoria_dt'].dt.date >= start_date_hist]
        if end_date_hist:
            df_filtered_hist = df_filtered_hist[df_filtered_hist['data_auditoria_dt'].dt.date <= end_date_hist]

        # Exibe o dataframe filtrado
        st.dataframe(df_filtered_hist.drop(columns=['data_auditoria_dt']))
    
    st.markdown("---")
    
    # --- SEÇÃO ORIGINAL DE REGISTRO DE AUDITORIA (mantida abaixo) ---
    st.subheader("Registrar Nova Auditoria")

    consolidado = get_consolidated_recebimentos()
    if consolidado.empty:
        st.info("Nenhum recebimento registrado para auditar.")
        return
        
    conn = get_db_connection()
    produtos_df = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()

    consolidado = consolidado.merge(produtos_df, on='codigo_produto', how='left')
    
    opcoes_produtos = consolidado['codigo_produto'].tolist()
    
    if not opcoes_produtos:
        st.warning("Não há produtos para auditar.")
        return
        
    prod_audit = st.selectbox(
        "Selecione o Produto para Auditar",
        opcoes_produtos,
        key="prod_audit_selectbox"
    )
    
    quant_receb = 0
    if prod_audit:
        quant_receb = consolidado[consolidado['codigo_produto'] == prod_audit]['quantidade_total_recebida'].iloc[0]
    
    st.metric("Quantidade Total Recebida (Coletada)", f"{quant_receb:.2f}")

    with st.form("form_auditoria", clear_on_submit=True):
        quant_sistema = st.number_input("Quantidade do Sistema (Informada)", value=0.0, format="%.2f", min_value=0.0, key="quant_sistema_input")
        submit_audit = st.form_submit_button("Registrar Auditoria")

    if submit_audit:
        if prod_audit and quant_sistema >= 0:
            divergencia = quant_receb - quant_sistema
            status = "Aberta" if divergencia != 0 else "Solucionada"
            
            now = datetime.datetime.now(brasilia_tz)
            audit_data = {
                'codigo_produto': prod_audit, 
                'quantidade_sistema': quant_sistema,
                'quantidade_divergente': divergencia,
                'data_auditoria': now.strftime('%d/%m/%Y %H:%M'),
                'auditor': st.session_state.user_id,
                'status_divergencia': status
            }
            save_audit(audit_data)
            if divergencia != 0:
                st.warning(f"Divergência encontrada: {divergencia:.2f} unidades.")
            else:
                st.success("Auditoria registrada sem divergências.")
            st.rerun()
        else:
            st.error("Por favor, selecione um produto e insira a quantidade do sistema.")


def show_divergentes_page():
    st.header("Divergências Encontradas")

    conn = get_db_connection()
    df_auditorias = pd.read_sql_query("SELECT * FROM auditorias", conn)
    df_recebimentos = pd.read_sql_query("SELECT * FROM recebimentos", conn)
    df_produtos = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()

    if not df_auditorias.empty:
        df_auditorias['data_auditoria_dt'] = pd.to_datetime(df_auditorias['data_auditoria'], format='%d/%m/%Y %H:%M')

    df_divergentes = df_auditorias[df_auditorias['status_divergencia'] != 'Solucionada']
    if df_divergentes.empty:
        st.info("Nenhuma pendência em aberto.")
        return
    
    df_divergentes = df_divergentes.merge(df_produtos[['codigo_produto', 'descricao_produto']], on='codigo_produto', how='left')
    
    st.markdown("---")
    st.subheader("Pendências Abertas")
    
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Filtrar por Status", ["Todos"] + list(df_divergentes['status_divergencia'].unique()))
    with col2:
        min_date = df_divergentes['data_auditoria_dt'].min().date() if not df_divergentes.empty else None
        max_date = df_divergentes['data_auditoria_dt'].max().date() if not df_divergentes.empty else None
        
        start_date = st.date_input("Data de Início", value=None, min_value=min_date, max_value=max_date, key="diverg_start_date")
        end_date = st.date_input("Data de Fim", value=None, min_value=min_date, max_value=max_date, key="diverg_end_date")

    df_filtered = df_divergentes.copy()

    if status_filter != "Todos":
        df_filtered = df_filtered[df_filtered['status_divergencia'] == status_filter]
    
    if start_date:
        df_filtered = df_filtered[df_filtered['data_auditoria_dt'].dt.date >= start_date]
    
    if end_date:
        df_filtered = df_filtered[df_filtered['data_auditoria_dt'].dt.date <= end_date]

    if start_date and end_date and start_date > end_date:
        st.error("A data de início não pode ser maior que a data de fim.")
        st.dataframe(pd.DataFrame()) 
    else:
        st.dataframe(df_filtered.drop(columns=['data_auditoria_dt'])[['id_auditoria', 'codigo_produto', 'descricao_produto', 'quantidade_divergente', 'data_auditoria', 'auditor', 'status_divergencia']])
    
    st.markdown("---")
    st.subheader("Tratamento de Pendência")

    if not df_filtered.empty:
        selected_audit = st.selectbox("Selecione a divergência para tratamento", df_filtered['id_auditoria'].tolist())
        
        if selected_audit:
            divergence_info = df_filtered[df_filtered['id_auditoria'] == selected_audit].iloc[0]
            st.write(f"**Produto:** {divergence_info['descricao_produto']}")
            st.write(f"**Divergência:** {divergence_info['quantidade_divergente']} unidades")
            st.write(f"**Status Atual:** {divergence_info['status_divergencia']}")

            reception_record = df_recebimentos[df_recebimentos['codigo_produto'] == divergence_info['codigo_produto']]
            if not reception_record.empty and reception_record['condicao_produto'].iloc[0] == 'Ruim' and reception_record['foto_evidencia'].iloc[0]:
                st.subheader("Evidência Registrada")
                image_bytes = base64.b64decode(reception_record['foto_evidencia'].iloc[0])
                st.image(image_bytes, caption="Foto do produto ruim")

            new_status = st.radio("Mudar Status", ["Aberta", "Em tratamento", "Solucionada"], index=["Aberta", "Em tratamento", "Solucionada"].index(divergence_info['status_divergencia']))
            
            if st.button("Atualizar Status"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("UPDATE auditorias SET status_divergencia = ? WHERE id_auditoria = ?", (new_status, int(selected_audit)))
                conn.commit()
                conn.close()
                st.success("Status atualizado com sucesso!")
                st.rerun()
    else:
        st.info("Nenhuma divergência encontrada para os filtros selecionados.")

def show_relatorios_page():
    st.header("Relatórios Detalhados")
    
    conn = get_db_connection()
    df_receb = pd.read_sql_query("SELECT * FROM recebimentos", conn)
    conn.close()

    if df_receb.empty:
        st.info("Nenhum dado para gerar relatório.")
        return
        
    df_receb['data_recebimento_dt'] = pd.to_datetime(df_receb['data_recebimento'], format='%d/%m/%Y %H:%M')
    
    col1, col2 = st.columns(2)
    with col1:
        recebedor_filter = st.selectbox("Filtrar por Recebedor", ["Todos"] + list(df_receb['conferente'].unique()))
    with col2:
        start_date = st.date_input("Data de Início", value=None, key="rel_start_date")
        end_date = st.date_input("Data de Fim", value=None, key="rel_end_date")

    df_filtered = df_receb.copy()
    if recebedor_filter != "Todos":
        df_filtered = df_filtered[df_filtered['conferente'] == recebedor_filter]
    
    if start_date and end_date:
        df_filtered = df_filtered[(df_filtered['data_recebimento_dt'].dt.date >= start_date) & (df_filtered['data_recebimento_dt'].dt.date <= end_date)]

    st.markdown("---")
    st.subheader("Resultados")
    st.dataframe(df_filtered.drop(columns=['foto_evidencia', 'data_recebimento_dt']))

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df_filtered.to_excel(writer, index=False, sheet_name='Relatório de Recebimentos')
    
    st.download_button(
        label="Download Relatório (Excel)",
        data=excel_buffer.getvalue(),
        file_name='relatorio_recebimentos.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

def show_gestao_usuarios_page():
    st.header("Gestão de Usuários")
    
    if st.session_state.user_role != 'Gestor':
        st.warning("Você não tem permissão para acessar esta página.")
        return

    st.subheader("Usuários Existentes")
    df_users = get_all_users()
    st.dataframe(df_users)

    st.markdown("---")
    st.subheader("Criar/Alterar Usuário")
    with st.form("form_usuario", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            user_id = st.text_input("ID do Usuário")
            nome_usuario = st.text_input("Nome Completo")
        with col2:
            tipo_acesso = st.selectbox("Tipo de Acesso", ["Conferente", "Prevenção", "Gestor"])
            senha = st.text_input("Senha", type="password")
        
        submit_user = st.form_submit_button("Salvar Usuário")
        
    if submit_user:
        if user_id and nome_usuario and senha:
            save_user(user_id, nome_usuario, tipo_acesso, senha)
            st.success("Usuário salvo com sucesso!")
            st.rerun()
        else:
            st.error("Todos os campos devem ser preenchidos.")

    st.markdown("---")
    st.subheader("Excluir Usuário")
    user_to_delete = st.selectbox("Selecione o usuário para excluir", df_users['id_usuario'].tolist())
    if st.button("Excluir Usuário"):
        if user_to_delete:
            delete_user(user_to_delete)
            st.warning(f"Usuário {user_to_delete} excluído com sucesso.")
            st.rerun()

# --- Execução Principal ---
if __name__ == '__main__':
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    init_db()
    
    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()
