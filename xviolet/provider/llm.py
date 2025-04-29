"""
LLM Provider Integration (Google Gemini)

Handles interactions with the configured LLM (Gemini) for decision making,
content generation, etc., incorporating persona context.
"""

import logging
import os
from dotenv import load_dotenv
from ..config import config
from ..persona import Persona
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
from .proxy import proxy_manager

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration --- #
DEFAULT_API_KEY_ENV_VAR = "GOOGLE_API_KEY"
# Default model - consider making this configurable via persona or env var later
DEFAULT_MODEL_NAME = "gemini-1.5-flash-latest" # Or "gemini-pro", etc.

# Safety settings - adjust as needed


class LLMManager:
    def __init__(self,
                 api_key: str = None,
                 api_key_env_var: str = None,
                 model_name: str = None,
                 persona: Persona = None):
        """
        Initializes the LLMManager, configuring the Gemini client.
        Args:
            api_key: Gemini API key (defaults to config.gemini_api_key)
            api_key_env_var: Environment variable name for the API key (optional)
            model_name: The specific Gemini model to use (defaults to config.small_model)
            persona: An instance of the Persona class to provide context.
        """
        # If an environment var name is provided, load API key from it
        if api_key_env_var:
            api_key = os.getenv(api_key_env_var)
        self.api_key = api_key or config.gemini_api_key
        self.model_name = model_name or config.small_model
        self.vision_model = config.vision_model
        self.persona = persona
        self.client = None
        self.model = None

        if not self.api_key or self.api_key == "YOUR_GEMINI_API_KEY":
            logger.error("Google API key not found or not set in config. LLM disabled.")
            return # Allow instantiation but client/model will be None

        # Route all Gemini API requests through proxy if configured
        proxy_url = proxy_manager.get_proxy_url()
        if proxy_url:
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url
            logger.info(f"Routing Gemini API traffic via proxy: {proxy_url}")

        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Google Generative AI client configured successfully for model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI client: {e}")
            self.client = None

    @property
    def is_enabled(self) -> bool:
        """Returns True if the LLM client is configured and ready."""
        return self.client is not None

    def generate_text(self, prompt: str, context_type: str = "chat", **generation_kwargs) -> str | None:
        """
        Generates text using the configured Gemini model, prepending persona context.
        """
        from xviolet.config import config
        if config.dry_run:
            logger.info(f"[DRY RUN] generate_text: returning prompt fallback for '{prompt}'")
            return f"[DRY_RUN] {prompt}"
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot generate text.")
            return None

        full_prompt = prompt
        if self.persona:
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt = f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{prompt}"
            logger.debug(f"Generating text with full prompt (persona context type: {context_type}):\n{full_prompt[:500]}...")
        else:
            logger.debug("Generating text with prompt (no persona):\n%s...", prompt[:500])

        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
        }
        generation_config.update(generation_kwargs)
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            if hasattr(response, 'text') and response.text:
                logger.info(f"LLM generated text successfully (length: {len(response.text)}).")
                return response.text.strip()
            else:
                logger.warning("LLM returned empty or blocked response.")
                return None
        except Exception as e:
            logger.error(f"Error during LLM text generation: {e}")
            return None

    def analyze_image(self, image_path: str, prompt: str = None, context_type: str = "post", response_schema=None, response_mime_type=None, vision_model=None, **generation_kwargs):
        """
        Uses Gemini's multimodal API to analyze an image and return a persona-driven summary or tweet suggestion.
        """
        from xviolet.config import config
        if config.dry_run:
            logger.info(f"[DRY RUN] analyze_image: returning placeholder for '{image_path}'")
            return f"[DRY_RUN] Image at {image_path}"
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot analyze image.")
            return None
        full_prompt = prompt or "Describe the image."
        if self.persona:
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt = f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{full_prompt}"
        model_name = vision_model or self.model_name
        generation_config = {}
        generation_config.update(generation_kwargs)
        try:
            model = genai.GenerativeModel(model_name)
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            image_part = genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            response = model.generate_content(
                [image_part, full_prompt],
                generation_config=generation_config
            )
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.error(f"Error during image analysis: {e}")
            return None

    def analyze_video(self, video_path: str, prompt: str = None, context_type: str = "post", response_schema=None, response_mime_type=None, vision_model=None, **generation_kwargs):
        """
        Uses Gemini's video understanding API to analyze a video and return persona-driven output.
        """
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot analyze video.")
            return None
        full_prompt = prompt or "Describe the video."
        if self.persona:
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt = f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{full_prompt}"
        model_name = vision_model or self.model_name
        generation_config = {}
        if response_mime_type:
            generation_config['response_mime_type'] = response_mime_type
        generation_config.update(generation_kwargs)
        try:
            model = genai.GenerativeModel(model_name)
            with open(video_path, "rb") as f:
                video_bytes = f.read()
            video_part = genai.types.Part(
                inline_data=genai.types.Blob(data=video_bytes, mime_type='video/mp4')
            )
            response = model.generate_content(
                [video_part, full_prompt],
                generation_config=generation_config
            )
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.error(f"Error during video analysis: {e}")
            return None

    def generate_structured_output(self, prompt: str, schema: dict, context_type: str = "chat", response_mime_type=None, model_name=None, **generation_kwargs) -> dict | None:
        """
        Uses Gemini's structured output API to generate structured data from text/timeline.
        """
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot generate structured output.")
            return None
        full_prompt = prompt
        if self.persona:
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt = f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{prompt}"
        model_name = model_name or self.model_name
        generation_config = {}
        if response_mime_type:
            generation_config['response_mime_type'] = response_mime_type
        if schema:
            generation_config['response_schema'] = schema
        generation_config.update(generation_kwargs)
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            import json
            text = response.text.strip() if response and response.text else ""
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                json_str = text[start:end+1]
                return json.loads(json_str)
            logger.warning("Could not parse structured output as JSON.")
            return None
        except Exception as e:
            logger.error(f"Error during structured output generation: {e}")
            return None

    def embed_text(self, text: str, model_name: str = None, dimensions: int = None) -> list | None:
        """
        Uses Gemini's embedding API to embed a text string.
        """
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot embed text.")
            return None
        model_name = model_name or self.model_name
        dimensions = dimensions or int(os.getenv("GEMINI_EMBED_DIM", 768))
        try:
            model = genai.GenerativeModel(model_name)
            response = model.embed_content(
                content=text,
                task_type="RETRIEVAL_QUERY",
                title="tweet",
                dimensions=dimensions
            )
            if hasattr(response, 'embedding'):
                return response.embedding
            logger.warning("No embedding returned.")
            return None
        except Exception as e:
            logger.error(f"Error during text embedding: {e}")
            return None

    def embed_image(self, image_path: str, model_name: str = None, dimensions: int = None) -> list | None:
        """
        Uses Gemini's embedding API to embed an image.
        """
        if not self.is_enabled:
            logger.error("LLM client is not enabled. Cannot embed image.")
            return None
        model_name = model_name or self.model_name
        dimensions = dimensions or int(os.getenv("GEMINI_EMBED_DIM", 768))
        try:
            model = genai.GenerativeModel(model_name)
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            image_part = genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            response = model.embed_content(
                content=image_part,
                task_type="RETRIEVAL_DOCUMENT",
                title="image",
                dimensions=dimensions
            )
            if hasattr(response, 'embedding'):
                return response.embedding
            logger.warning("No embedding returned for image.")
            return None
        except Exception as e:
            logger.error(f"Error during image embedding: {e}")
            return None
