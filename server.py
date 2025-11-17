import streamlit as st
import time
import requests
import pandas as pd
import plotly.express as px
from database import create_tables, get_readings_by_exam, get_exam_metrics, get_all_patient_exams_metrics
from auth import register_patient, login_patient
from auxiliar_functions import display_dashboard


# Criar tabelas e garantir que o DB exista
create_tables()

FLASK_BASE_URL = "http://127.0.0.1:5001"
st.set_page_config(page_title="Pulmonado", page_icon="💨", layout="wide")

# Gerenciamento de estado da sessão
if "patient_info" not in st.session_state:
    st.session_state.patient_info = None
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
        load = 0.0

        match selected_mode:

            case "Manual":
                load = st.number_input(label="Carga do equipamento (L/min)", min_value=-0, step=1, max_value=100)

            case "Automático":
                default_load = 30
                load = st.number_input(label="Carga do equipamento (L/min)", min_value=-0,
                                       step=1,
                                       max_value=100,
                                       value=default_load
                                       )

        # Parâmetros de monitoramento
        CHECKS_PER_SECOND = 5
        MAX_DURATION_SECONDS = 3  # Limite de tempo máximo de espera

        if st.button("Iniciar Fisioterapia"):

            # 1. Enviar a carga para o Flask iniciar a sessão
            payload = {
                "patient_id": patient_id,
                "load": load
            }

            st.session_state.exam_readings = pd.DataFrame()

            try:
                response = requests.post(f"{FLASK_BASE_URL}/api/start_session", json=payload)
                response.raise_for_status()

                response_json = response.json()
                exam_id = response_json.get("exam_id")
                st.session_state.current_exam_id = exam_id

                st.info(
                    f"Sessão iniciada. Aguardando confirmação de {MAX_DURATION_SECONDS}s "
                    f"do ESP32...")

                progresso = st.progress(0)
                status_container = st.container()
                progresso_text = status_container.empty()
                block_messages = status_container.empty()
                MAX_WAIT_TIME_FOR_TRIGGER = 30
                start_time = time.time()

                # 2. Loop de monitoramento que espera o status "FINALIZADO"
                is_running = True
                is_measurement_active = False
                while is_running and (time.time() - start_time) < MAX_WAIT_TIME_FOR_TRIGGER:

                    # 2.1. Check progress (GET request)
                    progress_response = requests.get(f"{FLASK_BASE_URL}/api/check_progress/{patient_id}")
                    progress_response.raise_for_status()

                    progress_data = progress_response.json()
                    current_status = progress_data.get('status', 'AGUARDANDO')

                    # Atualiza a barra de progresso (baseado no tempo)
                    elapsed_time = time.time() - start_time

                    if current_status == "INICIAR" and not is_measurement_active:
                        is_measurement_active = True
                        measurement_start_time = time.time()

                    elif current_status == "INICIAR" and is_measurement_active:
                        # Medição em andamento
                        measurement_time = time.time() - measurement_start_time

                        progresso_percent = min(int(measurement_time / MAX_DURATION_SECONDS * 100), 100)

                        progresso.progress(progresso_percent)
                        progresso_text.text(
                            f"EXAME ATIVO. Medição: {int(measurement_time)}s de {MAX_DURATION_SECONDS}s.")

                    elif current_status == "TRIGGER_PENDENTE":
                        progresso_text.text(
                            f"Aguardando expiração"
                        )

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

                progresso_text.text(f"Exame em andamento. Tempo: {int(measurement_time)}s. Status: {current_status}")
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

                        # PROCESSAMENTO CRÍTICO: Aplica a Média Móvel de 2 períodos
                        # Cria a coluna suavizada
                        df['Flow (Smoothed)'] = df['Flow'].rolling(window=5, center=False).mean()

                        # Remove as linhas NaN iniciais criadas pelo filtro
                        df = df.dropna()

                        st.session_state.exam_readings = df

            except requests.exceptions.RequestException as e:
                st.error(f"Erro ao comunicar com o servidor Flask ou iniciar sessão: {e}")
                st.error("Verifique se o `api.py` está rodando e acessível em 127.0.0.1:5000.")

            # 5. Exibe o gráficos
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

            # 6. Exibe os dados do exame
            metrics_list = get_exam_metrics(st.session_state.current_exam_id)

            if metrics_list:
                # Converte a lista de tuplas em um dicionário para fácil acesso
                metrics_keys = ['CV (L)', 'CVF (L)', 'VEF1 (L)', 'VEF1/CVF (%)', 'PEF (L/s)', 'FEF25-75% (L/s)']
                metrics_dict = dict(zip(metrics_keys, metrics_list))

                st.markdown("---")
                st.subheader("📋 Resultados da Espirometria")

                # Exibir em colunas para organização
                col1, col2, col3 = st.columns(3)

                col1.metric("Capacidade Vital (CV)", f"{metrics_dict['CV (L)']:.3f} L")
                col1.metric("CV Forçada (CVF)", f"{metrics_dict['CVF (L)']:.3f} L")
                col2.metric("VEF1 (1º Segundo)", f"{metrics_dict['VEF1 (L)']:.3f} L")
                col2.metric("Relação VEF1/CVF", f"{metrics_dict['VEF1/CVF (%)']:.1f} %")
                col3.metric("Pico de Fluxo (PEF)", f"{metrics_dict['PEF (L/s)']:.3f} L/s")
                col3.metric("Fluxo Médio (FEF 25-75%)", f"{metrics_dict['FEF25-75% (L/s)']:.3f} L/s")

    with tab_dashboard:

        display_dashboard(patient_id)

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

                try:
                    requests.post(f"{FLASK_BASE_URL}/api/set_patient_id/{patient_info['id']}")
                except Exception as e:
                    st.warning(f"Não foi possível notificar o Flask sobre o login: {e}")

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
