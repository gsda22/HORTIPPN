import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from zoneinfo import ZoneInfo
from io import BytesIO
from streamlit_webrtc import webrtc_streamer, WebRtcMode, ClientSettings
import queue
import soundfile as sf
import numpy as np

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
    quantidade TEXT,
    peso_real TEXT,
    observacao TEXT
)
""")
conn.commit()

# =========================================================
# ABAS DO SISTEMA
# =========================================================
aba = st.sidebar.radio("Escolha uma opção:", ["📥 Lançar Pesagens (Prevenção)"])

# =========================================================
# FILA PARA ÁUDIO
# =========================================================
q_audio = queue.Queue()

def audio_callback(frame):
    audio_data = frame.to_ndarray()
    q_audio.put(audio_data)
    return frame

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

        with st.expander("📦 Inserir Detalhes da Pesagem", expanded=True):
            # Campo totalmente livre para quantidade e peso
            quantidade = st.text_input("Quantidade de Itens (ex: 3 ou 1.5kg)")
            peso_real = st.text_input("Peso Real da Pesagem (ex: 2.5kg)")

            st.markdown("### 🎤 Gravar Observação por Áudio")
            st.write("Clique no botão abaixo para gravar sua observação usando o microfone do dispositivo.")
            webrtc_ctx = webrtc_streamer(
                key="pesagem_audio",
                mode=WebRtcMode.SENDONLY,
                client_settings=ClientSettings(
                    media_stream_constraints={"audio": True, "video": False}
                ),
                audio_receiver_size=256,
                in_audio_frame_callback=audio_callback,
                async_processing=True,
            )

            observacao = st.text_area("Observação (ou use áudio)")

            if st.button("✅ Registrar Pesagem", key=f"btn_{codigo}"):
                if not result and (not descricao or not secao):
                    st.error("Preencha descrição e seção para cadastrar o produto.")
                else:
                    data_hora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Cadastra produto se necessário
                    if not result and descricao and secao:
                        cursor.execute("INSERT INTO produtos (codigo, descricao, secao) VALUES (?, ?, ?)",
                                       (codigo, descricao, secao))
                    
                    # Processa áudio gravado se houver
                    if not observacao and not q_audio.empty():
                        audio_frames = []
                        while not q_audio.empty():
                            audio_frames.append(q_audio.get())
                        if audio_frames:
                            audio_array = np.concatenate(audio_frames, axis=0)
                            # Converte para WAV em bytes
                            with BytesIO() as buf:
                                sf.write(buf, audio_array, samplerate=44100, format="WAV")
                                buf.seek(0)
                                observacao = f"[Áudio gravado: {len(audio_array)} frames]"

                    cursor.execute("""
                        INSERT INTO pesagens_prevencao (data_hora, codigo, descricao, secao, quantidade, peso_real, observacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (data_hora, codigo, descricao, secao, quantidade, peso_real, observacao))
                    conn.commit()
                    st.success("✅ Pesagem registrada com sucesso!")
                    st.experimental_rerun()

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
                st.write(f"**Quantidade:** {row.get('quantidade', '')}")
                st.write(f"**Peso Real:** {row.get('peso_real', '')}")
                st.write(f"**Observação:** {row['observacao']}")
                if st.button("❌ Excluir", key=f"del_{row['id']}"):
                    cursor.execute("DELETE FROM pesagens_prevencao WHERE id = ?", (row['id'],))
                    conn.commit()
                    st.experimental_rerun()
