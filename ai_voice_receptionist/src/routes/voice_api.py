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

# Initialize services
speech_service = SpeechService()
dialogue_service = DialogueService()

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
        session_id = request.form.get('session_id')
        caller_phone = request.form.get('caller_phone')
        
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Save uploaded audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            audio_file.save(temp_audio.name)
            
            # Convert speech to text
            user_text = speech_service.speech_to_text(temp_audio.name)
            
            # Process the message through dialogue service
            dialogue_result = dialogue_service.process_message(user_text, session_id)
            
            # Convert response to speech
            response_audio_path = tempfile.mktemp(suffix='.wav')
            speech_service.text_to_speech(
                dialogue_result['response'], 
                voice='alloy',
                output_path=response_audio_path
            )
            
            # Update or create call record
            call = Call.query.filter_by(session_id=dialogue_result['session_id']).first()
            if not call:
                call = Call(
                    session_id=dialogue_result['session_id'],
                    caller_phone=caller_phone,
                    primary_intent=dialogue_result['intent']
                )
                db.session.add(call)
            
            # Update call with latest information
            call.primary_intent = dialogue_result['intent']
            call.updated_at = datetime.utcnow()
            
            # Handle specific actions
            if dialogue_result.get('requires_action'):
                action_type = dialogue_result.get('action_type')
                action_data = dialogue_result.get('action_data', {})
                
                if action_type == 'appointment_confirm':
                    # Create appointment record
                    appointment = Appointment(
                        call_id=call.id,
                        customer_name=action_data.get('name'),
                        customer_phone=action_data.get('phone'),
                        service_type=action_data.get('service'),
                        appointment_date=datetime.strptime(action_data.get('date'), '%Y-%m-%d').date(),
                        appointment_time=datetime.strptime(action_data.get('time'), '%H:%M').time()
                    )
                    db.session.add(appointment)
                    call.appointment_booked = True
            
            db.session.commit()
            
            # Clean up temporary input file
            os.unlink(temp_audio.name)
            
            # Return audio response
            return send_file(
                response_audio_path,
                as_attachment=True,
                download_name='response.wav',
                mimetype='audio/wav'
            )
    
    except Exception as e:
        return jsonify({'error': f'Error processing call: {str(e)}'}), 500

@voice_bp.route('/text-chat', methods=['POST'])
def text_chat():
    """
    Process text-based chat (for testing and web interface)
    """
    try:
        data = request.get_json()
        user_message = data.get('message')
        session_id = data.get('session_id')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Process the message through dialogue service
        result = dialogue_service.process_message(user_message, session_id)
        
        # Update or create call record for text chat
        call = Call.query.filter_by(session_id=result['session_id']).first()
        if not call:
            call = Call(
                session_id=result['session_id'],
                primary_intent=result['intent']
            )
            db.session.add(call)
        
        call.primary_intent = result['intent']
        call.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': f'Error processing message: {str(e)}'}), 500

@voice_bp.route('/speech-to-text', methods=['POST'])
def speech_to_text():
    """
    Convert speech to text
    """
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        language = request.form.get('language')
        
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Save uploaded audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            audio_file.save(temp_audio.name)
            
            # Convert speech to text
            text = speech_service.speech_to_text(temp_audio.name, language)
            
            # Clean up
            os.unlink(temp_audio.name)
            
            return jsonify({'text': text})
    
    except Exception as e:
        return jsonify({'error': f'Error converting speech to text: {str(e)}'}), 500

@voice_bp.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    """
    Convert text to speech
    """
    try:
        data = request.get_json()
        text = data.get('text')
        voice = data.get('voice', 'alloy')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Convert text to speech
        audio_path = tempfile.mktemp(suffix='.wav')
        speech_service.text_to_speech(text, voice, audio_path)
        
        return send_file(
            audio_path,
            as_attachment=True,
            download_name='speech.wav',
            mimetype='audio/wav'
        )
    
    except Exception as e:
        return jsonify({'error': f'Error converting text to speech: {str(e)}'}), 500

@voice_bp.route('/voices', methods=['GET'])
def get_voices():
    """
    Get available TTS voices
    """
    try:
        voices = speech_service.get_available_voices()
        return jsonify({'voices': voices})
    
    except Exception as e:
        return jsonify({'error': f'Error getting voices: {str(e)}'}), 500

@voice_bp.route('/session/<session_id>', methods=['GET'])
def get_session_info(session_id):
    """
    Get information about a conversation session
    """
    try:
        session_info = dialogue_service.get_session_info(session_id)
        if session_info:
            return jsonify(session_info)
        else:
            return jsonify({'error': 'Session not found'}), 404
    
    except Exception as e:
        return jsonify({'error': f'Error getting session info: {str(e)}'}), 500

@voice_bp.route('/calls', methods=['GET'])
def get_calls():
    """
    Get list of calls with optional filtering
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        intent = request.args.get('intent')
        
        query = Call.query
        
        if status:
            query = query.filter(Call.call_status == status)
        if intent:
            query = query.filter(Call.primary_intent == intent)
        
        calls = query.order_by(Call.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'calls': [call.to_dict() for call in calls.items],
            'total': calls.total,
            'pages': calls.pages,
            'current_page': page,
            'per_page': per_page
        })
    
    except Exception as e:
        return jsonify({'error': f'Error getting calls: {str(e)}'}), 500

@voice_bp.route('/calls/<int:call_id>', methods=['GET'])
def get_call(call_id):
    """
    Get detailed information about a specific call
    """
    try:
        call = Call.query.get_or_404(call_id)
        return jsonify(call.to_dict())
    
    except Exception as e:
        return jsonify({'error': f'Error getting call: {str(e)}'}), 500

@voice_bp.route('/appointments', methods=['GET'])
def get_appointments():
    """
    Get list of appointments
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        
        query = Appointment.query
        
        if status:
            query = query.filter(Appointment.status == status)
        
        appointments = query.order_by(Appointment.appointment_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'appointments': [appointment.to_dict() for appointment in appointments.items],
            'total': appointments.total,
            'pages': appointments.pages,
            'current_page': page,
            'per_page': per_page
        })
    
    except Exception as e:
        return jsonify({'error': f'Error getting appointments: {str(e)}'}), 500

@voice_bp.route('/appointments/<int:appointment_id>', methods=['PUT'])
def update_appointment(appointment_id):
    """
    Update appointment status or details
    """
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        data = request.get_json()
        
        # Update allowed fields
        if 'status' in data:
            appointment.status = data['status']
        if 'notes' in data:
            appointment.notes = data['notes']
        
        appointment.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(appointment.to_dict())
    
    except Exception as e:
        return jsonify({'error': f'Error updating appointment: {str(e)}'}), 500

@voice_bp.route('/config', methods=['GET'])
def get_business_config():
    """
    Get business configuration
    """
    try:
        configs = BusinessConfig.query.all()
        config_dict = {config.key: config.value for config in configs}
        return jsonify(config_dict)
    
    except Exception as e:
        return jsonify({'error': f'Error getting configuration: {str(e)}'}), 500

@voice_bp.route('/config', methods=['POST'])
def update_business_config():
    """
    Update business configuration
    """
    try:
        data = request.get_json()
        
        for key, value in data.items():
            BusinessConfig.set_config(key, str(value))
        
        return jsonify({'message': 'Configuration updated successfully'})
    
    except Exception as e:
        return jsonify({'error': f'Error updating configuration: {str(e)}'}), 500

