import streamlit as st
import time
import requests
import pandas as pd
import plotly.express as px
from database import create_tables, get_readings_by_exam
from auth import register_patient, login_patient

# Criar tabelas e garantir que o DB exista
create_tables()

FLASK_BASE_URL = "http://127.0.0.1:5001"
st.set_page_config(page_title="Pulmonado", page_icon="💨", layout="wide")

# Gerenciamento de estado da sessão
if "patient_info" not in st.session_state:
    st.session_state.patient_info = None
if "last_blocks_received" not in st.session_state:
    st.session_state.last_blocks_received = 0
if "current_exam_id" not in st.session_state:
    st.session_state.current_exam_id = None

if "exam_readings" not in st.session_state:
    # DataFrame vazio para armazenar os dados do gráfico
    st.session_state.exam_readings = pd.DataFrame()

# Se já está logado, mostra o dashboard
if st.session_state.patient_info:

    patient_id = st.session_state.patient_info['id']
    patient_name = st.session_state.patient_info['name']

    tab_exam, tab_dashboard = st.tabs(["Iniciar Fisioterapia", "Histórico de exames"])

    with tab_exam:
        st.header("⚙️Ajuste dos parâmetros")

        modes = ['Manual', 'Automático']
        selected_mode = st.selectbox("Modo do Pulmonado", modes)
        load = 0.0  # Inicializa a carga

        match selected_mode:

            case "Manual":
                load = st.number_input(label="Carga do equipamento", min_value=-0.0, step=0.1, max_value=40.0)

            case "Automático":
                default_load = 5.0
                load = st.number_input(label="Carga do equipamento", min_value=-0.0,
                                       step=0.1,
                                       max_value=40.0,
                                       value=default_load
                                       )

        # Parâmetros de monitoramento
        CHECKS_PER_SECOND = 5
        MAX_DURATION_SECONDS = 15  # Limite de tempo máximo de espera

        if st.button("Iniciar Fisioterapia"):

            # 1. Enviar a carga para o Flask iniciar a sessão
            payload = {
                "patient_id": patient_id,
                "load": load
            }

            st.session_state.last_blocks_received = 0
            st.session_state.exam_readings = pd.DataFrame()

            try:
                response = requests.post(f"{FLASK_BASE_URL}/api/start_session", json=payload)
                response.raise_for_status()

                response_json = response.json()
                exam_id = response_json.get("exam_id")
                st.session_state.current_exam_id = exam_id

                st.info(
                    f"Sessão iniciada (Exame ID: {exam_id}). Aguardando confirmação de {MAX_DURATION_SECONDS}s "
                    f"do ESP32...")

                progresso = st.progress(0)
                status_container = st.container()
                progresso_text = status_container.empty()
                block_messages = status_container.empty()
                start_time = time.time()

                # 2. Loop de monitoramento que espera o status "FINALIZADO"
                is_running = True
                while is_running and (time.time() - start_time) < MAX_DURATION_SECONDS:

                    # 2.1. Check progress (GET request)
                    progress_response = requests.get(f"{FLASK_BASE_URL}/api/check_progress/{patient_id}")
                    progress_response.raise_for_status()

                    progress_data = progress_response.json()
                    current_blocks = progress_data.get('blocks_received', 0)
                    current_status = progress_data.get('status', 'AGUARDANDO')

                    # Atualiza a barra de progresso (baseado no tempo)
                    elapsed_time = time.time() - start_time
                    progresso_percent = min(int(elapsed_time / MAX_DURATION_SECONDS * 100), 100)
                    progresso.progress(progresso_percent)
                    progresso_text.text(f"Exame em andamento. Tempo: {int(elapsed_time)}s. Status: {current_status}")

                    # Verifica se novos blocos chegaram
                    new_blocks = current_blocks - st.session_state.last_blocks_received

                    if new_blocks > 0:
                        latest_message = f"Bloco(s) de dados recebido(s)! Total: **{current_blocks}** blocos"
                        block_messages.markdown(latest_message)
                        st.session_state.last_blocks_received = current_blocks  # Atualiza o estado

                    # CONDIÇÃO DE SAÍDA: O ESP32 terminou e o Flask confirmou
                    if current_status == "FINALIZADO":
                        is_running = False
                        break

                    # Espera o intervalo
                    time.sleep(1 / CHECKS_PER_SECOND)

                # 3. Finaliza a sessão no Flask (Garantia de limpeza do estado)
                finalize_response = requests.post(f"{FLASK_BASE_URL}/api/finalize_session",
                                                  json={"patient_id": patient_id})
                finalize_response.raise_for_status()

                progresso_text.text(f"Exame em andamento. Tempo: {int(elapsed_time + 1)}s. Status: {current_status}")
                progresso.progress(100)

                # 4. Busca os dados finais e processa para o gráfico
                if st.session_state.current_exam_id:
                    raw_readings = get_readings_by_exam(st.session_state.current_exam_id)

                    if raw_readings:
                        # Cria o DataFrame
                        df = pd.DataFrame(raw_readings, columns=['timestamp', 'Flow'])

                        # Converte a coluna timestamp para datetime
                        df['timestamp'] = pd.to_datetime(df['timestamp'])

                        # Calcula a coluna de segundos decorridos
                        df['Seconds'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds().round(2)

                        # PROCESSAMENTO CRÍTICO: Aplica a Média Móvel de 5 períodos
                        # Cria a coluna suavizada
                        df['Flow (Smoothed)'] = df['Flow'].rolling(window=5, center=False).mean()

                        # Remove as linhas NaN iniciais criadas pelo filtro
                        df = df.dropna()

                        st.session_state.exam_readings = df

                st.success(f"Sessão concluída! Total de blocos recebidos: {st.session_state.last_blocks_received}")

            except requests.exceptions.RequestException as e:
                st.error(f"Erro ao comunicar com o servidor Flask ou iniciar sessão: {e}")
                st.error("Verifique se o `api.py` está rodando e acessível em 127.0.0.1:5000.")

            # 5. Exibe os dois gráficos se houver dados
            if not st.session_state.exam_readings.empty:
                plot_df = st.session_state.exam_readings.copy()
                plot_df = plot_df.dropna(subset=['Flow (Smoothed)', 'Seconds'])

                if not plot_df.empty:

                    st.subheader("Gráfico 1: Fluxo Pulmonar")

                    fig = px.line(
                        plot_df,
                        x='Seconds',
                        y='Flow (Smoothed)',
                        title='Fluxo Pulmonar Suavizado (Média de 5 Amostras)',
                        labels={
                            'Seconds': 'Tempo (segundos)',
                            'Flow (Smoothed)': 'Fluxo (Unidade Arbitrária)'
                        }
                    )

                    # CÁLCULO DINÂMICO DO RANGE X E Y
                    y_max = plot_df['Flow (Smoothed)'].max() if not plot_df.empty else 10
                    x_max = plot_df['Seconds'].max() if not plot_df.empty else 15

                    # Força a escala Y e X (resolve o problema de corte)
                    fig.update_layout(
                        yaxis_range=[0, y_max * 1.2],
                        xaxis_range=[0, x_max * 1.05]
                    )
                    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

                else:
                    st.warning(
                        "O DataFrame está vazio após a limpeza dos dados (pode haver inconsistência nos dados brutos).")

            else:
                st.warning("Nenhum dado de leitura recebido ou salvo para esta sessão.")

    with tab_dashboard:

        st.sidebar.header("Filtros 📅")
        st.sidebar.date_input("Selecione a data", format="DD/MM/YYYY")
        st.sidebar.button("Filtrar")

        # Dashboard
        st.title(f"📊 Dashboard de {patient_name}")
        st.info("Aqui futuramente você verá seus exames e gráficos de desempenho pulmonar.")
        st.sidebar.success(f"Paciente: {patient_name} (ID: {patient_id})")

    if st.sidebar.button("Sair"):
        st.session_state.patient_info = None
        st.rerun()

# Se ainda não está logado, mostra a tela de login/registro
else:
    st.title("💨 Pulmonado - Login")

    tab_login, tab_registro = st.tabs(["Login", "Registrar"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Senha", type="password", key="login_senha")

        if st.button("Entrar", key="btn_login"):
            # FUNÇÃO PADRONIZADA: login_patient
            patient_info = login_patient(email, password)
            if patient_info:
                st.session_state.patient_info = patient_info
                st.rerun()
            else:
                st.error("Email ou senha incorretos.")

    with tab_registro:
        name = st.text_input("Nome completo", key="reg_nome")
        email = st.text_input("Email para cadastro", key="reg_email")
        password = st.text_input("Senha", type="password", key="reg_senha")

        if st.button("Registrar", key="btn_registrar"):
            if name and email and password:
                patient_id = register_patient(name, email, password)
                if patient_id:
                    st.success(f"Conta criada com sucesso! Seu ID é {patient_id}. Faça login para começar.")
                else:
                    st.error("Esse email já está cadastrado ou ocorreu um erro.")
            else:
                st.warning("Preencha todos os campos!")
