from database import get_db_connection
import sqlite3


def register_patient(name, email, password):
    """
    Registers a new patient in the database.
    Returns the patient ID on success, or None if the email already exists or on error.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Note: In a real-world app, store password hashes, not plain text.
        cursor.execute("INSERT INTO pacientes (nome, email, senha) VALUES (?, ?, ?)", (name, email, password))
        conn.commit()
        return cursor.lastrowid # Retorna o ID do paciente recém-criado
    except sqlite3.IntegrityError:
        # IntegrityError ocorre se o email (UNIQUE NOT NULL) já existir
        print(f"Error registering patient: Email '{email}' already exists.")
        return None
    except Exception as e:
        print(f"Error registering patient: {e}")
        return None
    finally:
        conn.close()


def login_patient(email, password):
    """
    Authenticates a patient using email and password.
    Returns patient dict on success, or None on failure.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Busca o paciente pelo email
    cursor.execute("SELECT id, nome, email, senha FROM pacientes WHERE email = ?", (email,))
    row = cursor.fetchone()

    conn.close()

    if row:
        patient_id, name, retrieved_email, db_password = row
        # Compara a senha (plain text, para fins de teste)
        if password == db_password:
            return {"id": patient_id, "name": name, "email": retrieved_email}
    return None
