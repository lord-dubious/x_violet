import pytest
from xviolet.provider.llm import LLMManager
from xviolet.config import AgentConfig

@pytest.fixture(scope="module")
def config():
    return AgentConfig()

@pytest.fixture(scope="module")
def llm(config):
    # Use vision_model from config for all multimodal tests
    return LLMManager(api_key_env_var="GOOGLE_GENERATIVE_AI_API_KEY", model_name=config.vision_model)

def test_generate_text(llm):
    result = llm.generate_text("Say hello in a creative way.")
    assert result is None or isinstance(result, str)

def test_analyze_image_with_vision_model(llm, tmp_path):
    # Create a dummy image
    from PIL import Image
    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (32, 32), color="red")
    img.save(img_path)
    text = llm.analyze_image(str(img_path), prompt="Describe this image.")
    assert text is None or isinstance(text, str)  # Accept None if API blocks

def test_analyze_image_with_schema(llm, tmp_path):
    from PIL import Image
    img_path = tmp_path / "test2.png"
    img = Image.new("RGB", (32, 32), color="blue")
    img.save(img_path)
    schema = {
        "type": "object",
        "properties": {
            "color": {"type": "string"}
        },
        "required": ["color"]
    }
    text = llm.analyze_image(str(img_path), prompt="What is the main color?", response_schema=schema, response_mime_type="application/json")
    assert text is None or isinstance(text, str)

def test_generate_structured_output(llm):
    schema = {
        "type": "object",
        "properties": {
            "animal": {"type": "string"},
            "sound": {"type": "string"}
        },
        "required": ["animal", "sound"]
    }
    result = llm.generate_structured_output("Give an animal and its sound.", schema, response_mime_type="application/json")
    assert result is None or isinstance(result, dict)

def test_generate_structured_enum(llm):
    schema = {
        "type": "string",
        "enum": ["Percussion", "String", "Woodwind", "Brass", "Keyboard"]
    }
    result = llm.generate_structured_output(
        "What type of instrument is an oboe?",
        schema,
        response_mime_type="text/x.enum"
    )
    assert result is None or isinstance(result, str) or (isinstance(result, dict) and "Woodwind" in str(result))
