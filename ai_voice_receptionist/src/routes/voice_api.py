"""
Voice API Routes
Handles voice-related API endpoints for the AI receptionist
"""
import os
import io
import tempfile
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from src.services.speech_service import SpeechService
from src.services.dialogue_service import DialogueService
from src.models.call import Call, Appointment, BusinessConfig, db
from datetime import datetime

voice_bp = Blueprint('voice', __name__)

# Initialize services lazily
speech_service = None
dialogue_service = None

def get_speech_service():
    global speech_service
    if speech_service is None:
        speech_service = SpeechService()
    return speech_service

def get_dialogue_service():
    global dialogue_service
    if dialogue_service is None:
        dialogue_service = DialogueService()
    return dialogue_service

@voice_bp.route('/process-call', methods=['POST'])
def process_call():
    """
    Process a voice call - handles audio input and returns audio response
    """
    try:
        # Check if audio file is provided
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Get caller information
        caller_phone = request.form.get('caller_phone', 'Unknown')
        call_id = request.form.get('call_id')
        
        # Save the uploaded audio file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            audio_file.save(temp_file.name)
            
            try:
                # Convert speech to text
                user_text = get_speech_service().speech_to_text(temp_file.name)
                
                if not user_text:
                    return jsonify({'error': 'Could not process audio'}), 400
                
                # Get or create call record
                if call_id:
                    call = Call.query.get(call_id)
                    if not call:
                        call = Call(
                            caller_phone=caller_phone,
                            status='in_progress',
                            start_time=datetime.utcnow()
                        )
                        db.session.add(call)
                        db.session.commit()
                else:
                    call = Call(
                        caller_phone=caller_phone,
                        status='in_progress',
                        start_time=datetime.utcnow()
                    )
                    db.session.add(call)
                    db.session.commit()
                
                # Process the dialogue
                response_text = get_dialogue_service().process_message(user_text, call.id)
                
                # Convert response to speech
                audio_response = get_speech_service().text_to_speech(response_text)
                
                # Update call record
                call.transcript = (call.transcript or '') + f"\nUser: {user_text}\nAssistant: {response_text}"
                db.session.commit()
                
                # Return audio response
                return send_file(
                    io.BytesIO(audio_response),
                    mimetype='audio/wav',
                    as_attachment=True,
                    download_name='response.wav'
                )
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                    
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@voice_bp.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    """
    Convert text to speech
    """
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({'error': 'No text provided'}), 400
        
        text = data['text']
        voice = data.get('voice', 'alloy')  # Default voice
        
        # Convert text to speech
        audio_data = get_speech_service().text_to_speech(text, voice=voice)
        
        return send_file(
            io.BytesIO(audio_data),
            mimetype='audio/wav',
            as_attachment=True,
            download_name='speech.wav'
        )
        
    except Exception as e:
        return jsonify({'error': f'Text-to-speech failed: {str(e)}'}), 500

@voice_bp.route('/speech-to-text', methods=['POST'])
def speech_to_text():
    """
    Convert speech to text
    """
    try:
        # Check if audio file is provided
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Save the uploaded audio file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            audio_file.save(temp_file.name)
            
            try:
                # Convert speech to text
                text = get_speech_service().speech_to_text(temp_file.name)
                
                if not text:
                    return jsonify({'error': 'Could not process audio'}), 400
                
                return jsonify({'text': text})
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                    
    except Exception as e:
        return jsonify({'error': f'Speech-to-text failed: {str(e)}'}), 500

@voice_bp.route('/test', methods=['GET'])
def test_voice_api():
    """
    Test endpoint for voice API
    """
    return jsonify({
        'message': 'Voice API is working',
        'endpoints': [
            '/api/voice/process-call',
            '/api/voice/text-to-speech',
            '/api/voice/speech-to-text',
            '/api/voice/test'
        ]
    })
