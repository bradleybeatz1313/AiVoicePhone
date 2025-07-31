"""
Speech Service
Handles speech-to-text and text-to-speech operations
"""
import os
import io
import openai
from openai import OpenAI
from src.models.call import BusinessConfig

class SpeechService:
    def __init__(self):
        # Get OpenAI API key from business config or environment
        self.client = None
        self._client_initialized = False
    
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
                print("Warning: No OpenAI API key found. Speech services will not work.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
    
    def speech_to_text(self, audio_file_path):
        """
        Convert speech to text using OpenAI Whisper
        
        Args:
            audio_file_path (str): Path to the audio file
            
        Returns:
            str: Transcribed text or None if failed
        """
        try:
            self._ensure_client_initialized()
            
            if not self.client:
                raise Exception("OpenAI client not initialized")
            
            with open(audio_file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
                return transcript.text
                
        except Exception as e:
            print(f"Speech-to-text error: {e}")
            return None
    
    def text_to_speech(self, text, voice="alloy"):
        """
        Convert text to speech using OpenAI TTS
        
        Args:
            text (str): Text to convert to speech
            voice (str): Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            
        Returns:
            bytes: Audio data or None if failed
        """
        try:
            self._ensure_client_initialized()
            
            if not self.client:
                raise Exception("OpenAI client not initialized")
            
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            
            return response.content
            
        except Exception as e:
            print(f"Text-to-speech error: {e}")
            return None
    
    def get_available_voices(self):
        """
        Get list of available TTS voices
        
        Returns:
            list: Available voice names
        """
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
