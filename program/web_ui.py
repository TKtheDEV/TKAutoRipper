from flask import Flask, render_template, Blueprint
from flask_socketio import SocketIO, emit

# Create a blueprint
bp = Blueprint('web_ui', __name__)

# Initialize SocketIO with the main app not yet assigned
socketio = SocketIO()

@bp.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def on_connect():
    emit('status', {'data': 'Connected'})
