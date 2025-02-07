# /app/routes/hint_generation.py

import time
import concurrent.futures
from flask import Blueprint, request
from ..config import Config
from ..utils import success_response, error_response
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from vertexai.preview.generative_models import GenerativeModel as PreviewGenerativeModel
from vertexai.generative_models import GenerativeModel, SafetySetting
from PIL import Image as PIL_Image, ImageDraw
import base64
from io import BytesIO
from app.auth import authenticate_user  # Import from auth.py
from google.cloud import aiplatform
from ..models import db, UserWord, Word
from ..utils import validate_user_access  # Import the shared validation function
from datetime import datetime
import logging

logger = logging.getLogger(__name__)



# Define the Blueprint
bp = Blueprint('hint_generation', __name__, url_prefix='/hint')

# Configuration for image generation
IMAGE_MODEL_TYPE = "imagen" #"stable_diffusion" 

# Configuration for prompt generation
generation_config = {
    "max_output_tokens": 8192,
    "temperature": 1,
    "top_p": 0.95,
}

# Safety settings for LLM prompt generation
safety_settings = [
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
]

# Lazy-loaded model instances
_llm_model = None
_imagen_model = None
_stable_diffusion_model = None

# Global variables at the top of the file with other configurations
_placeholder_image = None

# Configuration for hint generation
UPDATE_WORD_ON_FORCE = False  # New configuration variable

aiplatform.init(project=Config.PROJECT_ID, location=Config.LOCATION)
vertexai.init(project=Config.PROJECT_ID, location=Config.LOCATION)

def get_llm_model():
    global _llm_model
    if _llm_model is None:
        try:
            _llm_model = GenerativeModel("gemini-1.5-flash-002")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize LLM model: {str(e)}")
    return _llm_model

def get_image_generation_model():
    global _imagen_model, _stable_diffusion_model
    
    if IMAGE_MODEL_TYPE == "imagen":
        if _imagen_model is None:
            try:
                logger.info("Initializing Imagen model using Vision API")
                #_imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
                _imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Imagen model: {str(e)}")
        return _imagen_model
    elif IMAGE_MODEL_TYPE == "stable_diffusion":
        if _stable_diffusion_model is None:
            raise RuntimeError(f"Stable Diffusion is not supported in this version of the app")
        return _stable_diffusion_model
    else:
        raise ValueError(f"Unsupported image model type: {IMAGE_MODEL_TYPE}")

def get_placeholder_image():
    """Get or create a cached 400x300 placeholder image with a large question mark."""
    global _placeholder_image
    
    if _placeholder_image is None:
        # Create a new image with a light gray background
        img = PIL_Image.new('RGB', (400, 300), color='#f0f0f0')
        draw = ImageDraw.Draw(img)
        
        # Draw a border
        draw.rectangle([0, 0, 399, 299], outline='#cccccc', width=2)
        
        # Add large question mark
        question_mark = "?"
        font_size = 200  # Increased font size from 150 to 200
        
        # Get text size and center it horizontally, but position it higher vertically
        text_bbox = draw.textbbox((0, 0), question_mark, font_size=font_size)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (400 - text_width) / 2
        y = (300 - text_height) / 3  # Changed from /2 to /3 to move it higher
        
        draw.text((x, y), question_mark, fill='#666666', font_size=font_size)
        
        _placeholder_image = img
    
    return _placeholder_image.copy()

def generate_prompt(word, pinyin, translation):
    model = get_llm_model()
    chat = model.start_chat()
    
    # Add more creative direction and randomness to the prompt
    prompt = f"""
    Create a unique and creative image generation prompt for the Chinese word "{word}" (pinyin: "{pinyin}", meaning: "{translation}").

    Requirements:
    - The prompt should be subtle and not directly reveal the word's meaning
    - No text or characters should appear in the image
    - Use varied artistic styles (e.g., watercolor, digital art, photography, abstract)
    - Incorporate different perspectives, moods, or settings
    - Make it metaphorical or symbolic rather than literal
    - Each generation should be different from previous ones
    - Length should be 1-2 sentences maximum

    Generate a completely new and unique prompt that has never been used before.
    """

    response = chat.send_message(
        [prompt],
        generation_config={
            "max_output_tokens": 8192,
            "temperature": 1.0,      # Increased from default for more randomness
            "top_p": 0.99,          # Slightly increased for more variety
            "top_k": 40,            # Added to further control diversity
            "candidate_count": 1,    # We only need one result
        },
        safety_settings=safety_settings
    )
    
    generated_prompt = response.candidates[0].content.parts[0].text.strip()
    
    # Clean up the prompt if needed
    if generated_prompt.lower().startswith(('prompt:', 'image prompt:', 'generate:')):
        generated_prompt = generated_prompt.split(':', 1)[1].strip()
    
    logger.info("Generated prompt for word '%s': %s", word, generated_prompt)
    
    return generated_prompt

def generate_image(prompt):
    model = get_image_generation_model()
    
    if IMAGE_MODEL_TYPE == "imagen":
        logger.info("Generating image for %s with Imagen", prompt)
        try:
            images = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio="4:3",
                safety_filter_level="block_some"
            )
            
            try:
                return (images[0]._pil_image.resize((400, 300), PIL_Image.Resampling.LANCZOS), False)
            except (IndexError, AttributeError) as e:
                logger.warning("Failed to access generated image: %s", str(e))
                return (get_placeholder_image(), True)
                
        except Exception as e:
            logger.error("Failed to generate image: %s", str(e))
            return (get_placeholder_image(), True)
            
    elif IMAGE_MODEL_TYPE == "stable_diffusion":
        try:
            logger.info("Generating image with Stable Diffusion")
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.9,
                }
            )
            # Convert the response to PIL Image
            image_bytes = response.candidates[0].image.image_bytes
            image = PIL_Image.open(BytesIO(image_bytes))
            # Resize the image to match our desired dimensions
            return (image.resize((400, 300), PIL_Image.Resampling.LANCZOS), False)
        except Exception as e:
            logger.error("Failed to generate image with Stable Diffusion: %s", str(e))
            return (get_placeholder_image(), True)

def image_to_base64(image):
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def process_single_hint(word, pinyin, translation):
    try:
        # Start timing for text generation
        start_text = time.time()
        
        # Generate the prompt
        prompt = generate_prompt(word, pinyin, translation)
        text_time = time.time() - start_text  # Measure the time taken for text generation

        # Start timing for image generation
        start_image = time.time()
        
        # Generate the image from the prompt
        image, is_placeholder = generate_image(prompt)
        image_time = time.time() - start_image  # Measure the time taken for image generation

    except Exception as e:
        logger.error(f"Failed to generate hint: {str(e)}")
        # If either prompt or image generation fails, return placeholder
        image = get_placeholder_image()
        prompt = f"A visual representation of the word '{word}' ({pinyin}), meaning '{translation}'"
        is_placeholder = True
        text_time = 0
        image_time = 0

    # Convert the image to base64 format for return
    hint_image_base64 = image_to_base64(image)

    # Return the result with all relevant information
    return {
        'word': word,
        'hint_text': prompt,
        'hint_image': hint_image_base64,
        'text_generation_time': text_time,
        'image_generation_time': image_time,
        'is_placeholder': is_placeholder
    }


@bp.route('/generate', methods=['GET'])
@authenticate_user  # Protect this route
def generate_single_hint():
    try:
        word = request.args.get('word')
        pinyin = request.args.get('pinyin')
        translation = request.args.get('translation')

        if not word or not pinyin or not translation:
            return error_response('Missing required parameters: word, pinyin, translation', 400)

        start_total = time.time()
        result = process_single_hint(word, pinyin, translation)
        result['total_time'] = time.time() - start_total

        return success_response(result)

    except RuntimeError as e:
        logger.error(f"RuntimeError generate_single_hint: {e}", exc_info=True)
        return error_response(f"Initialization error: {str(e)}", 500)
    except Exception as e:
        logger.error(f"Error generate_single_hint: {e}", exc_info=True)
        return error_response(f"Error generating hint: {str(e)}", 500)

@bp.route('/generate_multiple', methods=['POST'])
@authenticate_user  # Protect this route
def generate_multiple_hints():
    try:
        data = request.json
        if not data or not isinstance(data, list):
            return error_response('Invalid input format', 400)

        start_total = time.time()
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=Config.PARALLELISM_LIMIT) as executor:
            future_to_word = {
                executor.submit(process_single_hint, entry['word'], entry['pinyin'], entry['translation']): entry['word']
                for entry in data
            }
            for future in concurrent.futures.as_completed(future_to_word):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Error generating images: {e}", exc_info=True)
                    return error_response(f"Error generating images: {str(e)}", 500)

        response_time = time.time() - start_total
        return success_response({
            'hints': results,
            'total_time': response_time
        })

    except RuntimeError as e:
        logger.error(f"RuntimeError generate_multiple_hints: {e}", exc_info=True)
        return error_response(f"Initialization error: {str(e)}", 500)
    except Exception as e:
        logger.error(f"Error generate_multiple_hints: {e}", exc_info=True)
        return error_response(f"Error generating hints: {str(e)}", 500)
    
@bp.route('/generate_hint', methods=['GET'])
@authenticate_user  # Protect this route
def generate_hint():
    try:
        logger.info("in generate_hint")
        user_id = request.args.get('user_id')
        word_id = request.args.get('word_id')
        force_regenerate = request.args.get('force_regenerate', 'false').lower() == 'true'

        logger.info("force_regenerate=%s", force_regenerate)

        if not user_id or not word_id:
            return error_response('Missing required parameters: user_id, word_id', 400)

        # Use the shared validation function to ensure the user is only accessing their own data
        validation_response = validate_user_access(user_id)
        if validation_response:
            return validation_response

        # Fetch the Word entry first
        word_entry = Word.query.filter_by(word_id=word_id).first()
        if not word_entry:
            return error_response('Word entry not found', 404)

        # Check for existing UserWord first
        userword = UserWord.query.filter_by(user_id=user_id, word_id=word_id).first()
        
        # If we have valid userword hints, use them without checking word-level hints
        if userword and userword.hint_text and userword.hint_img and not force_regenerate:
            logger.info("Using existing userword hints")
            return success_response(
                data={
                    'hint_text': userword.hint_text,
                    'hint_image': base64.b64encode(userword.hint_img).decode('utf-8')
                },
                is_placeholder=False,
                message="Hint retrieved successfully from userword"
            )

        # Generate word-level hints if they don't exist and we'll need them
        if (word_entry.hint_text is None or word_entry.hint_img is None) and not force_regenerate:
            logger.info("Generating word-level hints for word_id=%s", word_id)
            start_total = time.time()
            hint_result = process_single_hint(word_entry.word, word_entry.def1, word_entry.def2)
            
            # Only save if it's not a placeholder image
            if not hint_result.get('is_placeholder', False):
                word_entry.hint_text = hint_result['hint_text']
                word_entry.hint_img = base64.b64decode(hint_result['hint_image'])
                db.session.commit()
                logger.info("Generated and saved word-level hints in %s seconds", time.time() - start_total)
            else:
                logger.warning("Generated placeholder image, not saving to database")
        
        if force_regenerate:
            # Create UserWord if it doesn't exist
            if not userword:
                logger.info("Creating new UserWord for force_regenerate")
                userword = UserWord(
                    user_id=user_id,
                    word_id=word_id,
                    is_included=True,
                    recall_state=0,
                    is_included_change_time=datetime.utcnow()
                )
                db.session.add(userword)
                db.session.commit()
                
            # Generate new personalized hints
            logger.info("Force regenerating hints for userword")
            start_total = time.time()
            hint_result = process_single_hint(word_entry.word, word_entry.def1, word_entry.def2)
            
            if not hint_result.get('is_placeholder', False):
                # Save successful generation
                userword.hint_text = hint_result['hint_text']
                userword.hint_img = base64.b64decode(hint_result['hint_image'])
                
                # Optionally update word-level hints as well
                if UPDATE_WORD_ON_FORCE:
                    logger.info("Also updating word-level hints due to force_regenerate")
                    word_entry.hint_text = hint_result['hint_text']
                    word_entry.hint_img = base64.b64decode(hint_result['hint_image'])
                
                db.session.commit()
                logger.info("Generated and saved hints in %s seconds", time.time() - start_total)
            else:
                # Clear hints when we get a placeholder
                logger.warning("Generated placeholder image, clearing existing hints")
                userword.hint_text = None
                userword.hint_img = None
                
                if UPDATE_WORD_ON_FORCE:
                    logger.info("Also clearing word-level hints due to force_regenerate")
                    word_entry.hint_text = None
                    word_entry.hint_img = None
                
                db.session.commit()
            
            return success_response(
                data={
                    'hint_text': hint_result['hint_text'],
                    'hint_image': hint_result['hint_image']
                },
                is_placeholder=hint_result.get('is_placeholder', False),
                message="Hint generation completed" if not hint_result.get('is_placeholder', False) else "Generation failed, hints cleared"
            )
        
        # Use word-level hints if they exist
        if word_entry.hint_text and word_entry.hint_img:
            logger.info("Using word-level hints")
            return success_response(
                data={
                    'hint_text': word_entry.hint_text,
                    'hint_image': base64.b64encode(word_entry.hint_img).decode('utf-8')
                },
                is_placeholder=False,
                message="Hint retrieved successfully from word"
            )
        
        # If we get here, we need to generate a placeholder
        logger.info("Using placeholder image")
        placeholder_result = process_single_hint(word_entry.word, word_entry.def1, word_entry.def2)
        return success_response(
            data={
                'hint_text': placeholder_result['hint_text'],
                'hint_image': placeholder_result['hint_image']
            },
            is_placeholder=True,
            message="Using placeholder hint"
        )

    except Exception as e:
        logger.error(f"Error generate_hint: {e}", exc_info=True)
        return error_response(f"Error generating hint: {str(e)}", 500)
