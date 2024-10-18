from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return "TKAutoRipper Web UI - Status Page Coming Soon!"

def start_web_ui():
    # Start the Flask web server
    app.run(debug=True, use_reloader=False, port=5000)
