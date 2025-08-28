import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from PIL import Image
import datetime
import pytz
from babel.dates import format_datetime

# Configurar o fuso horário de Brasília
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')

# Database setup
def init_db():
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    
    # Entidade forte: Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL,  -- admin, registrador, auditor
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Entidade forte: Lojas
    c.execute('''CREATE TABLE IF NOT EXISTS stores
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE NOT NULL)''')
    
    # Entidade forte: Produtos (com coluna code)
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE,
                  name TEXT NOT NULL,
                  category TEXT,  -- Herança potencial: ex., perecíveis
                  unit TEXT NOT NULL)''')  # ex., kg, unidade
    
    # Entidade fraca: Registros (depende de produto, loja, usuário)
    c.execute('''CREATE TABLE IF NOT EXISTS registrations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  product_id INTEGER NOT NULL,
                  store_id INTEGER NOT NULL,
                  quantity REAL NOT NULL,
                  registered_by INTEGER NOT NULL,
                  registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (product_id) REFERENCES products(id),
                  FOREIGN KEY (store_id) REFERENCES stores(id),
                  FOREIGN KEY (registered_by) REFERENCES users(id))''')
    
    # Entidade fraca: Auditorias (depende de registro)
    c.execute('''CREATE TABLE IF NOT EXISTS audits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  registration_id INTEGER NOT NULL,
                  actual_quantity REAL NOT NULL,
                  audited_by INTEGER NOT NULL,
                  audited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (registration_id) REFERENCES registrations(id),
                  FOREIGN KEY (audited_by) REFERENCES users(id))''')
    
    # Verificar e adicionar coluna code se não existir
    c.execute("PRAGMA table_info(products)")
    columns = [info[1] for info in c.fetchall()]
    if 'code' not in columns:
        c.execute("ALTER TABLE products ADD COLUMN code TEXT UNIQUE")
        c.execute("UPDATE products SET code = id WHERE code IS NULL")
        st.warning("Coluna 'code' adicionada à tabela products. Códigos existentes foram preenchidos com IDs. Atualize os códigos manualmente, se necessário.")
    
    # Dados iniciais
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        default_admin_pass = hashlib.sha256("123456".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                  ("admin", default_admin_pass, "admin"))
    
    c.execute("SELECT COUNT(*) FROM stores")
    if c.fetchone()[0] == 0:
        stores = ["SUSSUCA", "VIDA NOVA", "ALPHAVILLE"]
        for store in stores:
            c.execute("INSERT INTO stores (name) VALUES (?)", (store,))
    
    conn.commit()
    conn.close()

init_db()

# Funções auxiliares
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_credentials(username, password):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result and result[0] == hash_password(password):
        return result[1]  # retorna o papel
    return None

def get_stores():
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM stores")
    stores = c.fetchall()
    conn.close()
    return stores

def get_products():
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT id, code, name, category, unit FROM products")
    products = c.fetchall()
    conn.close()
    return products

def get_product_by_code(code):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT id, code, name, category, unit FROM products WHERE code = ?", (str(code),))
    product = c.fetchone()
    conn.close()
    if not product:
        st.warning(f"Nenhum produto encontrado para o código: {code}")
    return product

def add_product(code, name, category, unit):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO products (code, name, category, unit) VALUES (?, ?, ?, ?)", (code, name, category, unit))
        conn.commit()
        st.success(f"Produto '{name}' com código '{code}' adicionado com sucesso!")
    except sqlite3.IntegrityError:
        st.error(f"Erro: O código '{code}' já existe no banco de dados. Use um código único.")
    conn.close()

def register_blind(product_id, store_id, quantity, user_id):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("INSERT INTO registrations (product_id, store_id, quantity, registered_by) VALUES (?, ?, ?, ?)",
              (product_id, store_id, quantity, user_id))
    conn.commit()
    conn.close()

def get_registrations_without_audit():
    conn = sqlite3.connect('ceasa.db')
    df = pd.read_sql_query("""
        SELECT r.id, p.name as produto, s.name as loja, r.quantity as quantidade, r.registered_at
        FROM registrations r
        LEFT JOIN audits a ON r.id = a.registration_id
        JOIN products p ON r.product_id = p.id
        JOIN stores s ON r.store_id = s.id
        WHERE a.id IS NULL
    """, conn)
    # Converter registered_at para horário de Brasília e formato brasileiro
    df['registered_at'] = pd.to_datetime(df['registered_at']).dt.tz_localize('UTC').dt.tz_convert(BRASILIA_TZ)
    df['registered_at'] = df['registered_at'].apply(lambda x: format_datetime(x, "dd/MM/yyyy HH:mm:ss", locale='pt_BR'))
    conn.close()
    return df

def audit_registration(reg_id, actual_quantity, user_id):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("INSERT INTO audits (registration_id, actual_quantity, audited_by) VALUES (?, ?, ?)",
              (reg_id, actual_quantity, user_id))
    conn.commit()
    conn.close()

def get_divergent_products():
    conn = sqlite3.connect('ceasa.db')
    df = pd.read_sql_query("""
        SELECT p.name as produto, AVG(ABS(r.quantity - a.actual_quantity)) as divergencia_media,
               COUNT(*) as contagem
        FROM registrations r
        JOIN audits a ON r.id = a.registration_id
        JOIN products p ON r.product_id = p.id
        GROUP BY p.id
        ORDER BY divergencia_media DESC
        LIMIT 10
    """, conn)
    conn.close()
    return df

def get_users():
    conn = sqlite3.connect('ceasa.db')
    df = pd.read_sql_query("SELECT id, username as usuário, role as papel, created_at as criado_em FROM users", conn)
    # Converter created_at para horário de Brasília e formato brasileiro
    df['criado_em'] = pd.to_datetime(df['criado_em']).dt.tz_localize('UTC').dt.tz_convert(BRASILIA_TZ)
    df['criado_em'] = df['criado_em'].apply(lambda x: format_datetime(x, "dd/MM/yyyy HH:mm:ss", locale='pt_BR'))
    conn.close()
    return df

def add_user(username, password, role):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    pass_hash = hash_password(password)
    c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, pass_hash, role))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def change_password(user_id, new_password):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    pass_hash = hash_password(new_password)
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pass_hash, user_id))
    conn.commit()
    conn.close()

def get_user_id(username):
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def upload_products(file):
    try:
        st.info("Iniciando o upload do arquivo Excel...")
        df = pd.read_excel(file)
        # Verificar se as colunas necessárias existem
        required_columns = ['codigo', 'descricao', 'secao']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            st.error(f"Colunas ausentes no arquivo Excel: {', '.join(missing_columns)}")
            return False
        # Verificar se há dados válidos
        if df.empty:
            st.error("O arquivo Excel está vazio.")
            return False
        conn = sqlite3.connect('ceasa.db')
        c = conn.cursor()
        products_added = 0
        for _, row in df.iterrows():
            if pd.isna(row['descricao']) or row['descricao'].strip() == "" or pd.isna(row['codigo']) or row['codigo'].strip() == "":
                st.warning(f"Linha ignorada: Código ou descrição vazios/inválidos. Linha: {row}")
                continue
            c.execute("SELECT id FROM products WHERE code = ?", (str(row['codigo']),))
            if not c.fetchone():
                category = row.get('secao', 'Geral')
                unit = 'kg'  # Valor padrão
                c.execute("INSERT INTO products (code, name, category, unit) VALUES (?, ?, ?, ?)",
                          (str(row['codigo']), row['descricao'], category, unit))
                products_added += 1
        conn.commit()
        conn.close()
        st.success(f"Upload concluído! {products_added} produto(s) adicionado(s) com sucesso.")
        return True
    except Exception as e:
        st.error(f"Erro ao carregar o arquivo Excel: {str(e)}")
        return False

def get_all_products_df():
    conn = sqlite3.connect('ceasa.db')
    df = pd.read_sql_query("SELECT code as Código, name as Descrição, category as Seção, unit as Unidade FROM products", conn)
    conn.close()
    return df

# Streamlit app
st.set_page_config(page_title="Gerenciamento CEASA", page_icon="🍎", layout="wide")

# Logo
logo = Image.open("logo.png")  # Assume logo.png na mesma pasta
st.image(logo, width=200)

# Calculadora na barra lateral
with st.sidebar:
    st.subheader("Calculadora Rápida")
    calc_input = st.text_input("Digite o cálculo (ex.: 25+25)", key="calculadora")
    if calc_input:
        try:
            result = eval(calc_input)  # Avaliação simples, cuidado com entradas
            st.write(f"Resultado: {result}")
        except:
            st.error("Cálculo inválido")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.user_id = None
    st.session_state.username = None

if not st.session_state.logged_in:
    st.title("Login")
    with st.form(key="login_form"):
        username = st.text_input("Usuário", placeholder="Digite seu usuário", help="Usuário padrão: admin")
        password = st.text_input("Senha", type="password", placeholder="Digite sua senha", help="Senha padrão: 123456")
        submit = st.form_submit_button("Entrar")
    
    if submit:
        role = check_credentials(username, password)
        if role:
            st.session_state.logged_in = True
            st.session_state.role = role
            st.session_state.username = username
            st.session_state.user_id = get_user_id(username)
            st.success("Login realizado com sucesso!")
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")
else:
    st.sidebar.title(f"Bem-vindo, {st.session_state.username} ({st.session_state.role})")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.user_id = None
        st.session_state.username = None
        st.rerun()
    
    if st.session_state.role == "admin":
        change_pass = st.sidebar.checkbox("Alterar Senha")
        if change_pass:
            with st.sidebar.form("change_pass_form"):
                new_pass = st.text_input("Nova Senha", type="password")
                confirm_pass = st.text_input("Confirmar Senha", type="password")
                submit_change = st.form_submit_button("Alterar")
                if submit_change and new_pass == confirm_pass:
                    change_password(st.session_state.user_id, new_pass)
                    st.sidebar.success("Senha alterada com sucesso!")
                elif submit_change:
                    st.sidebar.error("As senhas não coincidem")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Registrar às Cegas", "Auditar", "Relatórios", "Gerenciar Usuários"])
    
    with tab1:
        if st.session_state.role in ["admin", "registrar"]:
            st.header("Registrar CEASA às Cegas")
            
            # Upload de arquivo Excel
            uploaded_file = st.file_uploader("Carregar arquivo Excel com produtos (colunas: codigo, descricao, secao)", type="xlsx", key="excel_uploader")
            if uploaded_file is not None:
                with st.spinner("Processando o upload do Excel..."):
                    if upload_products(uploaded_file):
                        st.experimental_rerun()  # Recarrega a página apenas após sucesso
                    else:
                        st.stop()  # Para a execução se houver erro
            
            # Exibir tabela de produtos para depuração
            st.subheader("Produtos Cadastrados")
            products_df = get_all_products_df()
            if products_df.empty:
                st.info("Nenhum produto cadastrado no banco de dados.")
            else:
                st.dataframe(products_df)
            
            # Input de código do produto
            product_code = st.text_input("Código do Produto", placeholder="Digite o código do produto (ex.: 001)", key="product_code_input")
            product_id = None
            if product_code:
                if product_code.strip() == "":
                    st.error("O código do produto não pode estar vazio.")
                else:
                    product = get_product_by_code(product_code)
                    if product:
                        product_id, code, name, category, unit = product
                        st.write(f"**Descrição**: {name}")
                        st.write(f"**Seção**: {category}")
                        st.write(f"**Unidade**: {unit}")
                    else:
                        st.warning(f"Produto com código '{product_code}' não encontrado.")
                        add_new = st.checkbox("Adicionar este produto ao banco de dados?", key="add_new_product")
                        if add_new:
                            with st.form("add_new_product_form"):
                                new_code = st.text_input("Código", value=product_code, disabled=True)
                                new_name = st.text_input("Descrição")
                                new_category = st.text_input("Seção")
                                new_unit = st.text_input("Unidade (ex.: kg)")
                                if st.form_submit_button("Adicionar Produto"):
                                    if new_name.strip() == "" or new_code.strip() == "":
                                        st.error("O código e a descrição do produto não podem estar vazios.")
                                    else:
                                        add_product(new_code, new_name, new_category, new_unit)
                                        st.experimental_rerun()
            
            stores = get_stores()
            store_options = {name: id for id, name in stores}
            selected_store = st.selectbox("Loja", list(store_options.keys()), key="store_select")
            quantity = st.number_input("Quantidade", min_value=0.0, key="quantity_input")
            if st.button("Registrar", key="register_button"):
                if product_id:
                    register_blind(product_id, store_options[selected_store], quantity, st.session_state.user_id)
                    st.success("Registrado com sucesso!")
                else:
                    st.error("Selecione um produto válido antes de registrar.")
        else:
            st.error("Acesso negado.")
    
    with tab2:
        if st.session_state.role in ["admin", "auditor"]:
            st.header("Auditar Quantidade Recebida")
            regs = get_registrations_without_audit()
            if regs.empty:
                st.info("Nenhum registro para auditar.")
            else:
                st.dataframe(regs)
                reg_id = st.number_input("ID do Registro para Auditar", min_value=1, key="audit_reg_id")
                actual_qty = st.number_input("Quantidade Real", min_value=0.0, key="audit_qty")
                if st.button("Auditar", key="audit_button"):
                    audit_registration(reg_id, actual_qty, st.session_state.user_id)
                    st.success("Auditado com sucesso!")
                    st.experimental_rerun()
        else:
            st.error("Acesso negado.")
    
    with tab3:
        st.header("Relatórios: Produtos com Maior Divergência")
        div = get_divergent_products()
        if div.empty:
            st.info("Nenhum dado disponível.")
        else:
            st.dataframe(div)
    
    with tab4:
        if st.session_state.role == "admin":
            st.header("Gerenciamento de Usuários")
            users_df = get_users()
            st.dataframe(users_df)
            
            st.subheader("Adicionar Usuário")
            with st.form("add_user"):
                new_username = st.text_input("Usuário")
                new_password = st.text_input("Senha", type="password")
                new_role = st.selectbox("Papel", ["registrador", "auditor", "admin"])
                if st.form_submit_button("Adicionar"):
                    add_user(new_username, new_password, new_role)
                    st.success("Usuário adicionado!")
                    st.experimental_rerun()
            
            st.subheader("Excluir Usuário")
            del_user_id = st.number_input("ID do Usuário para Excluir", min_value=1)
            if st.button("Excluir", key="delete_user_button"):
                delete_user(del_user_id)
                st.success("Usuário excluído!")
                st.experimental_rerun()
        else:
            st.error("Acesso negado.")

