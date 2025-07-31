"""
Dialogue Service
Handles conversation logic and AI responses for the receptionist
"""
import os
from datetime import datetime, timedelta
from openai import OpenAI
from src.models.call import Call, Appointment, BusinessConfig, db

class DialogueService:
    def __init__(self):
        self.client = None
        self._client_initialized = False
        self.conversation_history = {}
    
    def _ensure_client_initialized(self):
        """Ensure OpenAI client is initialized before use"""
        if not self._client_initialized:
            self._initialize_client()
            self._client_initialized = True
    
    def _initialize_client(self):
        """Initialize OpenAI client with API key"""
        try:
            # Try to get API key from business config first
            api_key = None
            try:
                config = BusinessConfig.query.filter_by(key='openai_api_key').first()
                api_key = config.value if config and config.value else None
            except:
                # Database might not be available yet, fall back to environment
                pass
            
            if not api_key:
                api_key = os.getenv('OPENAI_API_KEY')
            
            if api_key:
                self.client = OpenAI(api_key=api_key)
            else:
                print("Warning: No OpenAI API key found. Dialogue service will not work.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
    
    def _get_business_context(self):
        """Get business information from config"""
        context = {}
        config_keys = [
            'business_name', 'business_hours', 'business_address',
            'business_phone', 'business_email', 'services'
        ]
        
        for key in config_keys:
            config = BusinessConfig.query.filter_by(key=key).first()
            context[key] = config.value if config else f"[{key} not configured]"
        
        return context
    
    def _get_system_prompt(self):
        """Generate system prompt with business context"""
        context = self._get_business_context()
        
        return f"""You are an AI receptionist for {context['business_name']}. You are professional, helpful, and friendly.

Business Information:
- Business Name: {context['business_name']}
- Hours: {context['business_hours']}
- Address: {context['business_address']}
- Phone: {context['business_phone']}
- Email: {context['business_email']}
- Services: {context['services']}

Your responsibilities:
1. Greet callers professionally
2. Answer questions about the business
3. Help schedule appointments
4. Provide information about services
5. Take messages when needed
6. Transfer calls when appropriate

Guidelines:
- Keep responses conversational and natural
- Be helpful and patient
- If you don't know something, say so and offer to take a message
- For appointments, ask for preferred date/time, contact info, and reason for visit
- Always confirm important details back to the caller

Respond naturally as if you're speaking on the phone."""
    
    def process_message(self, user_message, call_id):
        """
        Process user message and generate appropriate response
        
        Args:
            user_message (str): User's message
            call_id (int): ID of the current call
            
        Returns:
            str: AI response
        """
        try:
            self._ensure_client_initialized()
            
            if not self.client:
                return "I apologize, but I'm having technical difficulties. Please call back later."
            
            # Get or initialize conversation history for this call
            if call_id not in self.conversation_history:
                self.conversation_history[call_id] = []
            
            # Add user message to history
            self.conversation_history[call_id].append({
                "role": "user",
                "content": user_message
            })
            
            # Prepare messages for OpenAI
            messages = [
                {"role": "system", "content": self._get_system_prompt()}
            ] + self.conversation_history[call_id]
            
            # Get AI response
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=200,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Add AI response to history
            self.conversation_history[call_id].append({
                "role": "assistant",
                "content": ai_response
            })
            
            # Check if this looks like an appointment request
            self._check_appointment_intent(user_message, ai_response, call_id)
            
            return ai_response
            
        except Exception as e:
            print(f"Dialogue processing error: {e}")
            return "I apologize, but I'm having trouble processing your request right now. Could you please repeat that?"
    
    def _check_appointment_intent(self, user_message, ai_response, call_id):
        """
        Check if the conversation indicates appointment scheduling intent
        """
        appointment_keywords = [
            'appointment', 'schedule', 'book', 'meeting', 'visit',
            'see the doctor', 'consultation', 'available'
        ]
        
        if any(keyword in user_message.lower() for keyword in appointment_keywords):
            # Update call status to indicate appointment interest
            call = Call.query.get(call_id)
            if call:
                call.intent = 'appointment_scheduling'
                db.session.commit()
    
    def create_appointment(self, call_id, appointment_data):
        """
        Create an appointment from call data
        
        Args:
            call_id (int): ID of the call
            appointment_data (dict): Appointment details
            
        Returns:
            bool: Success status
        """
        try:
            call = Call.query.get(call_id)
            if not call:
                return False
            
            appointment = Appointment(
                call_id=call_id,
                patient_name=appointment_data.get('patient_name'),
                patient_phone=call.caller_phone,
                patient_email=appointment_data.get('patient_email'),
                appointment_date=appointment_data.get('appointment_date'),
                appointment_time=appointment_data.get('appointment_time'),
                service_type=appointment_data.get('service_type'),
                notes=appointment_data.get('notes'),
                status='scheduled'
            )
            
            db.session.add(appointment)
            call.intent = 'appointment_scheduled'
            db.session.commit()
            
            return True
            
        except Exception as e:
            print(f"Appointment creation error: {e}")
            db.session.rollback()
            return False
    
    def end_conversation(self, call_id):
        """
        Clean up conversation when call ends
        
        Args:
            call_id (int): ID of the call
        """
        if call_id in self.conversation_history:
            del self.conversation_history[call_id]
        
        # Update call status
        call = Call.query.get(call_id)
        if call:
            call.status = 'completed'
            call.end_time = datetime.utcnow()
            db.session.commit()
