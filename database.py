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

    # Generates a timestamp for each reading using the interval
    for i, flow in enumerate(flow_readings):
        timestamp = (start_timestamp + timedelta(milliseconds=i * milliseconds_interval)).isoformat()
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


# Example usage
if __name__ == '__main__':
    # We add table creation here to ensure it exists
    create_tables()
