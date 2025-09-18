from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)


# inicia o banco de dados
def init_db():
    conn = sqlite3.connect("pulmonado.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS leituras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fluxo TEXT
                )''')
    conn.commit()
    conn.close()


# salva os dados do paciente no banco de dados
def save_data(data):
    conn = sqlite3.connect("pulmonado.db")
    c = conn.cursor()
    c.execute("INSERT INTO leituras (fluxo) VALUES (?)", (",".join(map(str, data)),))
    conn.commit()
    conn.close()


# Endpoint para receber os dados do ESP32
@app.route("/dados", methods=["POST"])
def get_data():
    try:
        data = request.get_json()
        fluxo = data.get("fluxo", [])
        save_data(fluxo)

        print(f"Recebido bloco com {len(fluxo)} leituras de fluxo")

        # Aqui você poderia armazenar ou processar os dados

        return jsonify({"status": "ok", "mensagem": f"{len(fluxo)} leituras recebidas"}), 200
    except Exception as e:
        print(f"Erro ao processar dados: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 400


# Endpoint para buscar leituras já armazenadas
@app.route("/historico", methods=["GET"])
def historico():
    conn = sqlite3.connect("pulmonado.db")
    c = conn.cursor()
    c.execute("SELECT timestamp, fluxo FROM leituras ORDER BY id DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
