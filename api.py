from flask import Flask, request, jsonify
from database import start_new_exam, save_flow_readings


app = Flask(__name__)

# Global state variable to store the ongoing exam data
# Structure: {'patient_id_str': {'exam_id': int, 'load': float, 'status': str, 'blocks_received': int}}
SESSION_STATE = {}


@app.route('/api/start_session', methods=['POST'])  # Renamed endpoint
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
        'status': 'INICIAR',  # Command for ESP32
        'blocks_received': 0
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


@app.route('/api/finalize_session', methods=['POST'])  # Renamed endpoint
def finalize_session():
    """Endpoint for ESP32 or Streamlit to signal the end of the session."""
    data = request.get_json()
    patient_id = data.get('patient_id')

    if str(patient_id) in SESSION_STATE:
        # Signals the end for Streamlit/ESP32
        SESSION_STATE[str(patient_id)]['status'] = 'FINALIZADO'

        # NOTE: We keep the entry for a short time for Streamlit's final GET check.
        # It's better to let a separate cleanup process (or app restart) clear this.

        return jsonify({"message": "Session marked as FINALIZED"}), 200

    return jsonify({"error": "No active session found"}), 404


if __name__ == '__main__':
    # To run: python api.py
    app.run(host='0.0.0.0', port=5001, debug=True)
