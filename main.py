from flask import Flask, request, jsonify
import sqlite3
from database import criar_tabelas

app = Flask(__name__)
criar_tabelas()


# ----------------- ROTA PARA O ESP -----------------
@app.route("/api/dados", methods=["POST"])
def receber_dados():
    try:
        data = request.get_json()
        fluxo = data.get("fluxo", [])
        paciente_id = data.get("paciente_id")

        conn = sqlite3.connect("pulmonado.db")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exames (paciente_id, dados) VALUES (?, ?)",
            (paciente_id, str(fluxo))
        )
        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "msg": f"{len(fluxo)} leituras recebidas"})
    except Exception as e:
        return jsonify({"status": "erro", "msg": str(e)}), 400


# ----------------- ROTA PARA O STREAMLIT -----------------
@app.route("/api/exames/<int:paciente_id>", methods=["GET"])
def listar_exames(paciente_id):
    conn = sqlite3.connect("pulmonado.db")
    cur = conn.cursor()
    cur.execute("SELECT id, paciente_id, dados, data FROM exames WHERE paciente_id=?", (paciente_id,))
    exames = cur.fetchall()
    conn.close()

    exames_formatados = [
        {"id": e[0], "paciente_id": e[1], "dados": e[2], "data": e[3]}
        for e in exames
    ]

    return jsonify(exames_formatados)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)