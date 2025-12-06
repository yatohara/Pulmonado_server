import sqlite3
from datetime import datetime, timedelta

DB_NAME = 'pulmonado.db'


def create_tables():
    """
    Creates the database tables if they do not exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Criar tabela de pacientes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL
    )
    """)

    # Criar tabela de exames
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            carga REAL,

            -- NOVAS COLUNAS PARA MÉTRICAS CLÍNICAS
            cv_result REAL,
            cvf_result REAL,
            vef1_result REAL,
            vef1_cvf_ratio REAL,
            pef_result REAL, 
            fef2575_result REAL,

            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        )
        """)

    # Criar tabela de leituras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leituras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exame_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        fluxo REAL,
        FOREIGN KEY (exame_id) REFERENCES exames(id)
    )
    """)

    conn.commit()
    conn.close()


def get_db_connection():
    """Returns a connection object to the database."""
    return sqlite3.connect(DB_NAME)


def start_new_exam(patient_id, load):
    """Creates a new exam record and returns the ID of the new exam."""
    conn = get_db_connection()
    cursor = conn.cursor()
    current_date = datetime.now().isoformat()
    try:
        cursor.execute("INSERT INTO exames (paciente_id, data, carga) VALUES (?, ?, ?)",
                       (patient_id, current_date, load))
        conn.commit()
        return cursor.lastrowid  # Returns the ID of the newly created exam
    except Exception as e:
        print(f"Error starting new exam: {e}")
        return None
    finally:
        conn.close()


def save_flow_readings(exam_id, flow_readings):
    """Saves a list of flow readings for a specific exam."""
    conn = get_db_connection()
    cursor = conn.cursor()

    data_to_insert = []
    start_timestamp = datetime.now()
    milliseconds_interval = 10  # 10ms interval simulated from ESP32
    readings_amount = len(flow_readings)

    # Generates a timestamp for each reading using the interval
    for i, flow in enumerate(flow_readings):
        timestamp = (start_timestamp - timedelta(milliseconds=(readings_amount - i) * milliseconds_interval)).isoformat()
        data_to_insert.append((exam_id, timestamp, flow))

    try:
        # Use executemany for efficient insertion
        cursor.executemany("INSERT INTO leituras (exame_id, timestamp, fluxo) VALUES (?, ?, ?)",
                           data_to_insert)
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving readings: {e}")
        return False
    finally:
        conn.close()


def get_readings_by_exam(exam_id):
    """Fetches all flow readings and timestamps for a given exam."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Busca todas as colunas de leituras ordenadas por timestamp
    cursor.execute("""
        SELECT timestamp, fluxo 
        FROM leituras 
        WHERE exame_id = ?
        ORDER BY timestamp
    """, (exam_id,))

    # Retorna os resultados como uma lista de tuplas [(timestamp, flow), ...]
    readings = cursor.fetchall()

    conn.close()
    return readings


def get_exam_metrics(exam_id):
    """Fetches all calculated clinical metrics for a given exam."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT cv_result, cvf_result, vef1_result, vef1_cvf_ratio, pef_result, fef2575_result
        FROM exames 
        WHERE id = ?
    """, (exam_id,))

    metrics = cursor.fetchone()
    conn.close()
    return metrics


def update_exam_metrics(exam_id, metrics):
    """Updates the exam record with the calculated clinical metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE exames SET 
                cv_result = ?, 
                cvf_result = ?, 
                vef1_result = ?, 
                vef1_cvf_ratio = ?, 
                pef_result = ?, 
                fef2575_result = ?
            WHERE id = ?
        """, (
            metrics['CV'],
            metrics['CVF'],
            metrics['VEF1'],
            metrics['VEF1/CVF'],
            metrics['PEF'],
            metrics['FEF25-75'],
            exam_id
        ))

        conn.commit()
        return True
    except Exception as e:
        print(f"ERRO DE UPDATE NO DB: Falha ao salvar métricas para o Exame {exam_id}: {e}")
        return False
    finally:
        conn.close()


def get_all_patient_exams_metrics(patient_id):
    """
    Busca todos os exames e suas métricas para um paciente, ordenados por data.
    Retorna uma lista de dicionários.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Seleciona todos os dados de interesse para o dashboard
    cursor.execute("""
        SELECT 
            data, carga, 
            cv_result, cvf_result, vef1_result, vef1_cvf_ratio, 
            pef_result, fef2575_result
        FROM exames 
        WHERE paciente_id = ?
        ORDER BY data DESC 
    """, (patient_id,))

    # Obtém os nomes das colunas
    column_names = [description[0] for description in cursor.description]

    # Converte os resultados em uma lista de dicionários
    exams_data = [dict(zip(column_names, row)) for row in cursor.fetchall()]

    conn.close()
    return exams_data

