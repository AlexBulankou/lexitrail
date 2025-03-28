import unittest
import tempfile
from unittest.mock import patch, MagicMock
from tests.utils import TestUtils
from app import db
from app.models import UserWord, Word
from app.routes.hint_generation import process_single_hint, generate_prompt, generate_image, get_placeholder_image
from PIL import Image
import base64
import os
import io

class HintGenerationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the test application and temporary database."""
        cls.client, cls.app, cls.temp_db_name = TestUtils.setup_test_app()

    @classmethod
    def tearDownClass(cls):
        """Tear down the temporary database after all tests."""
        TestUtils.teardown_test_db(cls.temp_db_name)

    def setUp(self):
        """Clean up the database before each test."""
        with self.app.app_context():
            TestUtils.clear_database(db)

    def save_image_from_base64(self, base64_str, word):
        """Save a base64 image to a temporary file and return the file path."""
        image_data = base64.b64decode(base64_str)
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{word}.jpg") as temp_file:
            temp_file.write(image_data)
            return temp_file.name

    @patch('app.routes.hint_generation.get_llm_model')
    @patch('app.routes.hint_generation.get_image_generation_model')
    def test_generate_prompt_logic(self, mock_image_model, mock_llm_model):
        """Test the logic of prompt generation with mocked LLM model."""
        mock_chat = MagicMock()
        mock_llm_model.return_value.start_chat.return_value = mock_chat
        mock_chat.send_message.return_value.candidates[0].content.parts[0].text = 'A subtle prompt for testing'
        
        prompt = generate_prompt("必须", "bìxū", "must")
        self.assertEqual(prompt, 'A subtle prompt for testing')

    @patch('app.routes.hint_generation.get_image_generation_model')
    def test_generate_image_logic(self, mock_image_model):
        """Test the image generation logic with mocked Image Generation model."""
        mock_image = MockImage()
        mock_image_model.return_value.generate_images.return_value = [mock_image]
        prompt = 'A subtle prompt for testing image generation'
        
        image, is_placeholder = generate_image(prompt)
        self.assertIsNotNone(image)
        self.assertEqual(image.size, (400, 300))
        self.assertFalse(is_placeholder)

    def test_process_single_hint_unmocked(self):
        """Test process_single_hint without mocks and save the output image."""
        with self.app.app_context():
            result = process_single_hint("必须", "bìxū", "must")
            self.assertIsInstance(result, dict)
            self.assertIn('hint_text', result)
            self.assertIn('hint_image', result)
            self.assertGreater(len(result['hint_image']), 0, "Generated image data should not be empty.")

            # Save the real image to disk and print file path for review
            image_path = self.save_image_from_base64(result['hint_image'], "必须")
            print(f"\nGenerated hint text: {result['hint_text']}")
            print(f"Generated image saved at: {image_path}")

    def test_generate_hint_no_existing_hints(self):
        """Test generating hints when no hints exist at word or userword level."""
        with self.app.app_context():
            user, wordset, word = TestUtils.create_test_word(db, user_email='test@example.com', word_name='Test Word')
            
            response = self.client.get(f'/hint/generate_hint?user_id={user.email}&word_id={word.word_id}')
            self.assertEqual(response.status_code, 200)
            response_data = response.get_json().get('data')
            
            # Verify word-level hints were generated
            updated_word = db.session.get(Word, word.word_id)
            self.assertIsNotNone(updated_word.hint_text)
            self.assertIsNotNone(updated_word.hint_img)
            
            # Verify response contains the generated hints
            self.assertIn('hint_text', response_data)
            self.assertIn('hint_image', response_data)
            self.assertEqual(response_data['hint_text'], updated_word.hint_text)
            self.assertEqual(response_data['hint_image'], 
                           base64.b64encode(updated_word.hint_img).decode('utf-8'))

    def test_generate_hint_existing_word_hints(self):
        """Test fetching hints when word-level hints exist but no userword."""
        with self.app.app_context():
            user, wordset, word = TestUtils.create_test_word(db, user_email='test@example.com', word_name='Test Word')
            # Set word-level hints
            word.hint_text = 'Existing word hint'
            word.hint_img = b'Existing word image'
            db.session.commit()

            response = self.client.get(f'/hint/generate_hint?user_id={user.email}&word_id={word.word_id}')
            self.assertEqual(response.status_code, 200)
            response_data = response.get_json().get('data')
            
            # Verify response uses word-level hints
            self.assertEqual(response_data['hint_text'], 'Existing word hint')
            self.assertEqual(response_data['hint_image'], 
                           base64.b64encode(b'Existing word image').decode('utf-8'))

    def test_generate_hint_force_regenerate_no_userword(self):
        """Test force regenerating hints when no userword exists."""
        with self.app.app_context():
            user, wordset, word = TestUtils.create_test_word(db, user_email='test@example.com', word_name='Test Word')
            word.hint_text = 'Existing word hint'
            word.hint_img = b'Existing word image'
            db.session.commit()

            # Mock the generate_prompt and generate_image functions
            with patch('app.routes.hint_generation.process_single_hint') as mock_process:
                # Configure mock to return successful generation
                mock_process.return_value = {
                    'hint_text': 'Test hint',
                    'hint_image': base64.b64encode(b'test image').decode('utf-8'),
                    'is_placeholder': False
                }

                response = self.client.get(
                    f'/hint/generate_hint?user_id={user.email}&word_id={word.word_id}&force_regenerate=true'
                )
                self.assertEqual(response.status_code, 200)
                response_data = response.get_json().get('data')

                # Verify new userword was created with new hints
                userword = UserWord.query.filter_by(user_id=user.email, word_id=word.word_id).first()
                self.assertIsNotNone(userword)
                self.assertIsNotNone(userword.hint_text)
                self.assertIsNotNone(userword.hint_img)

    def test_generate_hint_use_userword_hints(self):
        """Test that userword hints are used when they exist."""
        with self.app.app_context():
            user, wordset, word, userword = TestUtils.create_test_userword(db, user_email='test@example.com', word_name='Test Word')
            # Set different hints at word and userword level
            word.hint_text = 'Word hint'
            word.hint_img = b'Word image'
            userword.hint_text = 'Userword hint'
            userword.hint_img = b'Userword image'
            db.session.commit()

            response = self.client.get(f'/hint/generate_hint?user_id={user.email}&word_id={word.word_id}')
            self.assertEqual(response.status_code, 200)
            response_data = response.get_json().get('data')
            
            # Verify response uses userword hints
            self.assertEqual(response_data['hint_text'], 'Userword hint')
            self.assertEqual(response_data['hint_image'], 
                           base64.b64encode(b'Userword image').decode('utf-8'))

    def test_generate_hint_force_regenerate_with_placeholder(self):
        """Test force regenerating hints when generation fails."""
        with self.app.app_context():
            user, wordset, word = TestUtils.create_test_word(db, user_email='test@example.com', word_name='Test Word')
            word.hint_text = 'Existing word hint'
            word.hint_img = b'Existing word image'
            db.session.commit()

            # Mock the process_single_hint function
            with patch('app.routes.hint_generation.process_single_hint') as mock_process:
                # Configure mock to return placeholder
                mock_process.return_value = {
                    'hint_text': 'Placeholder hint',
                    'hint_image': base64.b64encode(b'placeholder image').decode('utf-8'),
                    'is_placeholder': True
                }

                response = self.client.get(
                    f'/hint/generate_hint?user_id={user.email}&word_id={word.word_id}&force_regenerate=true'
                )
                self.assertEqual(response.status_code, 200)
                response_data = response.get_json()
                
                # Verify response indicates placeholder
                self.assertTrue(response_data.get('is_placeholder', False))
                
                # Verify hints were cleared
                userword = UserWord.query.filter_by(user_id=user.email, word_id=word.word_id).first()
                self.assertIsNotNone(userword)
                self.assertIsNone(userword.hint_text)
                self.assertIsNone(userword.hint_img)

class MockImage:
    """Mock class for generated image objects."""
    def __init__(self):
        self._pil_image = Image.new('RGB', (400, 300))

    @property
    def pil_image(self):
        return self._pil_image
    
    def save(self, *args, **kwargs):
        """Mock save method to handle image_to_base64"""
        self._pil_image.save(*args, **kwargs)

    @property
    def size(self):
        return (400, 300)

def create_mock_pil_image():
    """Helper function to create a PIL Image for testing"""
    img = Image.new('RGB', (400, 300))
    return img

if __name__ == '__main__':
    unittest.main()
