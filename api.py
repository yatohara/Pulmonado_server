from flask import Flask, request, jsonify
from database import start_new_exam, save_flow_readings, update_exam_metrics
from auxiliar_functions import calculate_spirometry_metrics

app = Flask(__name__)

# Global state variable to store the ongoing exam data
# Structure: {'patient_id_str': {'exam_id': int, 'load': float, 'status': str, 'blocks_received': int}}
SESSION_STATE = {}
LAST_LOGGED_PATIENT_ID = 0


@app.route('/api/start_session', methods=['POST'])
def start_session():
    """Endpoint for Streamlit to initiate an exam session."""
    data = request.get_json()
    patient_id = data.get('patient_id')
    load = data.get('load')

    if not patient_id or load is None:
        return jsonify({"error": "Missing data: patient_id and load are required"}), 400

    exam_id = start_new_exam(patient_id, load)

    if not exam_id:
        return jsonify({"error": "Could not create exam record in the database"}), 500

    patient_id_str = str(patient_id)

    # Initializes the session state with zero blocks
    SESSION_STATE[patient_id_str] = {
        'exam_id': exam_id,
        'load': load,
        'status': 'TRIGGER_PENDENTE',  # Command for ESP32
        'blocks_received': 0,
        'patient_id': patient_id
    }

    # DEBUG: Print the updated state
    print(f"DEBUG: STATE AFTER START SESSION for ID {patient_id}: {SESSION_STATE.get(patient_id_str)}")

    return jsonify({
        "message": "Session successfully initiated",
        "exam_id": exam_id
    }), 200


@app.route('/api/receive_flow/<int:patient_id>', methods=['POST'])  # Renamed endpoint
def receive_flow(patient_id):
    """Endpoint for ESP32 to send flow readings."""
    data = request.get_json()
    flow = data.get('flow')
    exam_id = data.get('exam_id')

    if not flow or not exam_id:
        return jsonify({"error": "No flow data or exam_id sent"}), 400

    # 1. Saves readings to the database
    saved = save_flow_readings(exam_id, flow)

    if not saved:
        return jsonify({"error": "Failed to save readings to the database"}), 500

    # 2. Increments the block counter in the active session
    patient_id_str = str(patient_id)
    if patient_id_str in SESSION_STATE and SESSION_STATE[patient_id_str]['exam_id'] == exam_id:
        SESSION_STATE[patient_id_str]['blocks_received'] += 1

    return jsonify({"message": f"{len(flow)} flow readings successfully saved in exam {exam_id}"}), 200


@app.route('/api/check_progress/<int:patient_id>', methods=['GET'])  # Renamed endpoint
def check_progress(patient_id):
    """Endpoint for Streamlit to fetch the number of received blocks and status."""
    state = SESSION_STATE.get(str(patient_id), {'blocks_received': 0, 'status': 'AGUARDANDO'})

    # DEBUG: Print what Streamlit is receiving
    # print(f"DEBUG: Streamlit check. Returning: {state}")

    return jsonify({
        'blocks_received': state.get('blocks_received', 0),
        'status': state.get('status', 'AGUARDANDO')
    }), 200


@app.route('/api/set_status/<int:patient_id>/<string:new_status>', methods=['POST'])
def set_status(patient_id, new_status):
    """Endpoint para o ESP32 mudar o status da sessão (ex: TRIGGER_PENDENTE -> INICIAR)."""
    patient_id_str = str(patient_id)

    if patient_id_str in SESSION_STATE:
        if new_status == 'INICIAR' or new_status == 'FINALIZADO':
            SESSION_STATE[patient_id_str]['status'] = new_status
            return jsonify({"message": f"Status atualizado para {new_status}"}), 200
        else:
            return jsonify({"error": "Status inválido"}), 400

    return jsonify({"error": "Nenhuma sessão ativa"}), 404


@app.route('/api/esp_sync/<int:patient_id>', methods=['GET'])
def esp_sync(patient_id):
    """Endpoint for ESP32 to FETCH the status and load."""
    patient_id_str = str(patient_id)

    # Fetches the state
    state = SESSION_STATE.get(patient_id_str,
                              {'exam_id': 0, 'load': 0.0, 'status': 'AGUARDANDO', 'blocks_received': 0})

    # DEBUG CRÍTICO: Print what is being returned to the ESP32
    print(f"DEBUG: ESP32 requested sync. Returning: {state}")

    return jsonify(state), 200


@app.route('/api/finalize_session', methods=['POST'])
def finalize_session():
    """Endpoint for ESP32 or Streamlit to signal the end of the session."""
    data = request.get_json()
    patient_id = data.get('patient_id')

    if str(patient_id) in SESSION_STATE:
        exam_id = SESSION_STATE[str(patient_id)]['exam_id']

        # Sinaliza o fim para Streamlit/ESP32
        SESSION_STATE[str(patient_id)]['status'] = 'FINALIZADO'

        # CALCULA E SALVA AS MÉTRICAS
        metrics = calculate_spirometry_metrics(exam_id)
        if metrics:
            update_exam_metrics(exam_id, metrics)
            print(f"DEBUG: Métricas calculadas para Exame {exam_id}: {metrics}")
        else:
            print(f"DEBUG: Falha ao calcular métricas para Exame {exam_id}")

        return jsonify({"message": "Session marked as FINALIZED"}), 200

    return jsonify({"error": "No active session found"}), 404


# Salva o ID do paciente
@app.route('/api/set_patient_id/<int:patient_id>', methods=['POST'])
def set_patient_id(patient_id):
    """Endpoint chamado pelo Streamlit no login para registrar o Patient ID."""
    global LAST_LOGGED_PATIENT_ID
    LAST_LOGGED_PATIENT_ID = patient_id
    print(f"DEBUG: LAST_LOGGED_PATIENT_ID set to {patient_id}")
    return jsonify({"message": "Patient ID set"}), 200


# Busca o ID do paciente logado (usado pelo ESP32)
@app.route('/api/get_last_patient_id', methods=['GET'])
def get_last_patient_id():
    """Endpoint chamado pelo ESP32 para obter o ID do paciente atual."""
    # Retorna o último ID que o Streamlit enviou.
    return jsonify({"patient_id": LAST_LOGGED_PATIENT_ID}), 200


if __name__ == '__main__':
    # To run: python api.py
    app.run(host='0.0.0.0', port=5001, debug=True)
