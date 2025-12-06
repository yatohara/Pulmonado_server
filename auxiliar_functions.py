from database import get_readings_by_exam, get_all_patient_exams_metrics
from scipy.integrate import trapezoid, cumulative_trapezoid
import plotly.express as px
import streamlit as st
import numpy as np
import pandas as pd


def calculate_fef2575(flow_data, cvf, time_step):
    """
    Calculates the Forced Expiratory Flow between 25% and 75% of CVF.
    This method is standard in spirometry analysis.
    """
    # Volume expirado acumulado
    # Esta é a curva Volume-Tempo
    volume_cumul = cumulative_trapezoid(flow_data, dx=time_step, initial=0)

    # 2. Pontos de 25% e 75% do volume total (CVF)
    vol_25_percent = 0.25 * cvf
    vol_75_percent = 0.75 * cvf

    if cvf <= 0:
        return 0.0

    # Encontrar os índices (pontos no tempo) correspondentes no volume acumulado
    # np.where retorna uma tupla de arrays; pegamos o primeiro elemento de volume_cumul >= vol_threshold.

    try:
        # Encontra o primeiro índice onde o volume atinge 25% da CVF
        idx25 = np.where(volume_cumul >= vol_25_percent)[0][0]
    except IndexError:
        # Se 25% da CVF nunca for alcançado (ex: expiração incompleta)
        idx25 = 0

    try:
        # Encontra o primeiro índice onde o volume atinge 75% da CVF
        idx75 = np.where(volume_cumul >= vol_75_percent)[0][0]
    except IndexError:
        # Se 75% da CVF nunca for alcançado
        idx75 = len(flow_data) - 1

    # Se os índices forem os mesmos ou invertidos (caso de dados ruins), retorne 0
    if idx75 <= idx25:
        return 0.0

    # Determinar o tempo total decorrido entre os dois volumes
    # Tempo = (índice final - índice inicial) * passo de tempo
    time_segment = (idx75 - idx25) * time_step

    # CÁLCULO FINAL (Método Clínico)
    # FEF25-75 = (Volume Total do Segmento) / (Tempo Total do Segmento)
    # Volume Total do Segmento = (0.75 * CVF) - (0.25 * CVF) = 0.50 * CVF

    volume_segment = vol_75_percent - vol_25_percent  # = 0.50 * cvf
    fef25_75_result = volume_segment / time_segment

    return fef25_75_result


def display_dashboard(patient_id):
    # Obter todos os dados do paciente
    raw_data = get_all_patient_exams_metrics(patient_id)

    if not raw_data:
        st.info("Nenhum exame encontrado para este paciente.")
        return

    df = pd.DataFrame(raw_data)

    # PRÉ-PROCESSAMENTO:
    # Garantir que a coluna do DB seja tratada como 'data'
    if 'Data' in df.columns and 'data' in df.columns:
        df = df.drop(columns=['Data'])

    df['data'] = pd.to_datetime(df['data'])

    # Renomear TODAS as colunas APENAS uma vez para uso na exibição
    df = df.rename(columns={
        'data': 'Data do Exame',
        'carga': 'Carga (L/min)',
        'vef1_result': 'VEF1 (L)',
        'cvf_result': 'CVF (L)',
        'vef1_cvf_ratio': 'VEF1/CVF (%)',
        'pef_result': 'PEF (L/s)',
        'cv_result': 'CV (L)'
    })

    df = df.sort_values(by='Data do Exame', ascending=True).reset_index(drop=True)

    # --- CONFIGURAÇÃO DE FILTROS ---
    st.sidebar.header("Filtros de Período")

    # Filtro principal: Últimos N Exames vs. Por Mês
    filter_type = st.sidebar.radio("Filtrar por:", ("Últimos 10 Exames", "Por Mês", "Intervalo de Datas"), index=0)
    filtered_df = df.copy()

    match filter_type:

        case "Últimos 10 Exames":
            N_exams = st.sidebar.slider("Número de Últimos Exames (N)", min_value=1, max_value=10,
                                        value=min(5, len(df)))
            filtered_df = df.tail(N_exams)

        case "Por Mês":
            month_names = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                           'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
            selected_months = st.sidebar.multiselect("Selecione os Meses", month_names, default=month_names)

            # Mapeia nomes para números de mês (1 a 12)
            month_numbers = [month_names.index(m) + 1 for m in selected_months]

            if month_numbers:
                filtered_df = df[df['Data do Exame'].dt.month.isin(month_numbers)]
            else:
                st.info("Selecione um ou mais meses para filtrar.")
                return

        case "Intervalo de Datas":
            min_date = df['Data do Exame'].min().date()
            max_date = df['Data do Exame'].max().date()

            col_start, col_end = st.sidebar.columns(2)
            start_date = col_start.date_input("De", min_value=min_date, max_value=max_date, value=min_date)
            end_date = col_end.date_input("Até", min_value=min_date, max_value=max_date, value=max_date)

            if start_date > end_date:
                st.sidebar.error("A Data Inicial deve ser anterior à Data Final.")
                return

                # Aplicar filtro de datas
            filtered_df = df[(df['Data do Exame'].dt.date >= start_date) & (df['Data do Exame'].dt.date <= end_date)]

    if filtered_df.empty:
        st.warning("Nenhum dado encontrado para o filtro selecionado.")
        return

    # Garantir que o DF filtrado esteja ordenado
    filtered_df = filtered_df.sort_values(by='Data do Exame', ascending=True).reset_index(drop=True)

    # --- CÁLCULO DE MÉTRICAS E PROGRESSÃO ---

    # Obter o último resultado do período filtrado
    latest_exam = filtered_df.iloc[-1]

    # Obter a base de comparação (média dos anteriores OU exame anterior)
    numeric_cols = ['Carga (L/min)', 'VEF1 (L)', 'CVF (L)', 'VEF1/CVF (%)']

    # --- NOVO BLOCO DE DEFINIÇÃO DA BASE ---
    if len(filtered_df) > 1:
        # Base para VEF1, CVF, Ratio: Média dos exames anteriores
        avg_base = filtered_df.iloc[:-1][numeric_cols].mean()

        # Base para Carga: O exame IMEDIATAMENTE anterior (penúltimo)
        penultimate_exam = filtered_df.iloc[-2]
        base_for_load = penultimate_exam['Carga (L/min)']

    else:
        # Se só há um exame, a base é o valor atual (delta será 0)
        avg_base = latest_exam[numeric_cols]
        base_for_load = latest_exam['Carga (L/min)']

        # Calcular a Variação (Delta)
    deltas = {}
    for col in numeric_cols:
        latest_val = latest_exam[col]

        # Define a base de comparação
        if col == 'Carga (L/min)' and len(filtered_df) > 1:
            base_val = base_for_load
        else:
            base_val = avg_base[col]

        delta_val = latest_val - base_val

        if base_val == 0 or np.isnan(base_val) or (len(filtered_df) <= 1):
            # Se a base é zero, NaN, ou é o primeiro exame (sem histórico), a variação é tratada.
            if latest_val > 0:
                delta_perc = 100.0  # Melhoria do zero para um valor positivo
            else:
                delta_perc = 0.0  # Zero para zero
        else:
            # Cálculo padrão
            delta_perc = (delta_val / base_val) * 100

        deltas[col] = np.nan_to_num(delta_perc)

    # --- LAYOUT DE MÉTRICAS (TOPO) ---
    st.header("🎯 Progresso no Período Selecionado")
    st.caption(
        f"Comparação do exame mais recente ({latest_exam['Data do Exame'].strftime('%d/%m/%Y')}) "
        f"com a média dos exames anteriores no filtro.")

    col_metric, col_performance = st.columns([3, 1])

    with col_metric:
        st.subheader("Métricas de Desempenho (Último Exame)")

        c1, c2, c3 = st.columns(3)
        # VEF1
        c1.metric("VEF1 (L)", f"{latest_exam['VEF1 (L)']:.3f}", f"{deltas['VEF1 (L)']:.1f}%")
        # CVF
        c2.metric("CVF (L)", f"{latest_exam['CVF (L)']:.3f}", f"{deltas['CVF (L)']:.1f}%")
        # Relação VEF1/CVF
        c3.metric("VEF1/CVF (%)", f"{latest_exam['VEF1/CVF (%)']:.1f}", f"{deltas['VEF1/CVF (%)']:.1f}%")

    with col_performance:
        st.subheader("Melhoria da Carga")

        # Indica a melhoria da carga
        carga_delta = deltas['Carga (L/min)']
        st.metric(
            "Carga Atual (L/min)",
            f"{latest_exam['Carga (L/min)']:.1f}",
            f"{carga_delta:.1f}% vs. Média"
        )
        if carga_delta > 0:
            st.success(f"Aumento de **{carga_delta:.1f}%** na carga. Bom progresso!")
        else:
            st.info("Carga estável ou em declínio. Analisar VEF1.")

    st.markdown("---")

    # CÁLCULO DA MÉDIA DIÁRIA (É sempre necessário, caso o filtro seja de múltiplos dias)
    cols_for_avg = ['Carga (L/min)', 'VEF1 (L)', 'CVF (L)', 'VEF1/CVF (%)', 'PEF (L/s)', 'CV (L)']
    df_daily_avg = filtered_df.groupby(filtered_df['Data do Exame'].dt.date)[cols_for_avg].mean().reset_index()
    df_daily_avg['Data do Exame'] = df_daily_avg['Data do Exame'].astype('datetime64[ns]')  # Garante o tipo datetime
    df_daily_avg = df_daily_avg.rename(columns={'Data do Exame': 'Dia do Exame'})

    # CÁLCULO DA MÉDIA MENSAL (Novo Agrupamento)
    # Agrupar pelo início do mês (to_period('M'))
    df_monthly_avg = filtered_df.copy()
    df_monthly_avg = df_monthly_avg.set_index('Data do Exame').resample('M')[cols_for_avg].mean().reset_index()
    df_monthly_avg = df_monthly_avg.rename(columns={'Data do Exame': 'Mês do Exame'})

    # Determina a dispersão temporal total (em dias)
    min_date = filtered_df['Data do Exame'].dt.date.min()
    max_date = filtered_df['Data do Exame'].dt.date.max()

    # Cálculo robusto da diferença total em dias. Se houver apenas 1 exame, a diferença é 0.
    date_range_days = (max_date - min_date).days
    total_exams = len(filtered_df)

    # DEFINIÇÃO DA MELHOR GRANULARIDADE
    if date_range_days <= 2 or total_exams <= 5:
        # Caso 1: Período muito curto (1 ou 2 dias) ou poucos pontos. Usa dados brutos.
        df_to_plot = filtered_df
        x_axis_label = 'Data do Exame'  # Mantém carimbo de data/hora
        plot_title_suffix = "Exames Brutos"

    elif date_range_days <= 30:
        # Caso 2: Período médio (até 1 mes). Usa Média Diária.
        df_to_plot = df_daily_avg
        x_axis_label = 'Dia do Exame'
        plot_title_suffix = "Média Diária Agrupada"

    else:
        # Caso 3: Período longo (mais de 1 mes). Usa Média Mensal.
        df_to_plot = df_monthly_avg
        x_axis_label = 'Mês do Exame'
        plot_title_suffix = "Média Mensal Agrupada"

    # --- GRÁFICOS SEPARADOS DE PROGRESSÃO (Visualização 2x2) ---

    st.header(f"Série Histórica ({total_exams} Exames)")
    st.caption(f"Os gráficos exibem os dados {plot_title_suffix}.")

    metrics_to_plot = ['Carga (L/min)', 'VEF1 (L)', 'CVF (L)', 'VEF1/CVF (%)']

    col_row1 = st.columns(2)
    col_row2 = st.columns(2)
    plot_containers = [col_row1[0], col_row1[1], col_row2[0], col_row2[1]]

    for i, metric in enumerate(metrics_to_plot):
        with plot_containers[i]:
            st.subheader(f"{metric}")

            # Plotagem usando o DataFrame e o label X definidos dinamicamente
            fig = px.line(
                df_to_plot,
                x=x_axis_label,  # Usa 'Data do Exame' ou 'Dia do Exame'
                y=metric,
                title=f'{metric}',
                markers=True
            )
            fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=40, b=10), height=300)
            st.plotly_chart(fig, use_container_width=True)

    # Tabela de Dados Detalhada (A tabela continua mostrando os dados de cada exame individualmente)
    st.markdown("---")
    st.subheader("Tabela de Dados Detalhada (Filtro Aplicado)")
    st.dataframe(filtered_df.style.format({
        'Carga (L/min)': "{:.1f}",
        'CV (L)': "{:.3f}",
        'CVF (L)': "{:.3f}",
        'VEF1 (L)': "{:.3f}",
        'PEF (L/s)': "{:.3f}",
        'FEF25-75% (L/s)': "{:.3f}",
        'VEF1/CVF (%)': "{:.1f}"
    }), hide_index=True)


def calculate_spirometry_metrics(exam_id, sample_rate_ms=10):
    """
    Calculates essential spirometry metrics from raw flow data.
    Flow is assumed to be in L/min or similar flow unit.
    """
    raw_readings = np.array(get_readings_by_exam(exam_id))

    if raw_readings.size == 0:
        return None

    # Coluna 1 do raw_readings é o fluxo (Flow)
    time_data = np.array(raw_readings[:, 0]).astype(np.datetime64)
    flow_data = np.array(raw_readings[:, 1]).astype(float)
    time_step = sample_rate_ms / 1000.0  # Tempo entre amostras em segundos

    # PEF (Peak Expiratory Flow): Fluxo Máximo
    pef = np.max(flow_data)

    # VEF1 (Forced Expiratory Volume in 1 second)
    first_time = time_data[0]
    time_limit = first_time + np.timedelta64(1, 's')
    vef1_index_limit_mask = time_data <= time_limit
    vef1_flow_slice = flow_data[vef1_index_limit_mask]

    vef1 = trapezoid(vef1_flow_slice, dx=time_step)  # Integração

    # CVF (Forced Vital Capacity): Volume Expiratório Total
    cvf = trapezoid(flow_data, dx=time_step)

    # Relação VEF1 / CVF
    vef1_cvf_ratio = (vef1 / cvf) * 100 if cvf > 0 else 0

    # CV (Capacidade Vital): Assumindo CVF = CV (muito comum em espirometria forçada)
    cv = cvf

    return {
        'CV': round(cv, 3),
        'CVF': round(cvf, 3),
        'VEF1': round(vef1, 3),
        'VEF1/CVF': round(vef1_cvf_ratio, 1),
        'PEF': round(pef, 3),
        'FEF25-75': round(calculate_fef2575(flow_data, cvf, time_step), 3)
    }
