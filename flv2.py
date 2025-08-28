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
                  role TEXT NOT NULL,  -- admin, registrar, auditor
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

def get_unique_categories():
    conn = sqlite3.connect('ceasa.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return ["Todas"] + sorted(categories)  # Adiciona "Todas" como opção padrão

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

def get_divergent_products(category_filter=None, start_date=None, end_date=None):
    conn = sqlite3.connect('ceasa.db')
    query = """
        SELECT p.name as produto, AVG(ABS(r.quantity - a.actual_quantity)) as divergencia_media,
               COUNT(*) as contagem
        FROM registrations r
        JOIN audits a ON r.id = a.registration_id
        JOIN products p ON r.product_id = p.id
        WHERE 1=1
    """
    params = []
    
    # Filtro por seção
    if category_filter and category_filter != "Todas":
        query += " AND p.category = ?"
        params.append(category_filter)
    
    # Filtro por intervalo de datas
    if start_date and end_date:
        query += " AND r.registered_at BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    elif start_date:
        query += " AND r.registered_at >= ?"
        params.append(start_date)
    elif end_date:
        query += " AND r.registered_at <= ?"
        params.append(end_date)

    query += " GROUP BY p.id ORDER BY divergencia_media DESC LIMIT 10"
    
    df = pd.read_sql_query(query, conn, params=params)
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
            st.experimental_rerun()
        else:
            st.error("Usuário ou senha inválidos")
else:
    st.sidebar.title(f"Bem-vindo, {st.session_state.username} ({st.session_state.role})")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.user_id = None
        st.session_state.username = None
        st.experimental_rerun()
    
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
                    st.sidebar
