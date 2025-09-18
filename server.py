from flask import Flask, request, jsonify

app = Flask(__name__)


# Endpoint para receber os dados do ESP32
@app.route("/dados", methods=["POST"])
def get_data():
    try:
        data = request.get_json()
        fluxo = data.get("fluxo", [])

        print(f"Recebido bloco com {len(fluxo)} leituras de fluxo")

        # Aqui você poderia armazenar ou processar os dados

        return jsonify({"status": "ok", "mensagem": f"{len(fluxo)} leituras recebidas"}), 200
    except Exception as e:
        print(f"Erro ao processar dados: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
