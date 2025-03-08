import unittest
from translation_utils import TranslationManager

class TestTranslationManager(unittest.TestCase):
    def setUp(self):
        self.translator = TranslationManager()

    def test_split_at_sentence_end_empty(self):
        first, remainder = self.translator.split_at_sentence_end("")
        self.assertEqual(first, "")
        self.assertEqual(remainder, "")

    def test_split_at_sentence_end_single_sentence(self):
        text = "This is a single sentence."
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, text)
        self.assertEqual(remainder, "")

    def test_split_at_sentence_end_multiple_sentences(self):
        text = "First sentence. Second sentence. Third incomplete"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "First sentence. Second sentence.")
        self.assertEqual(remainder, "Third incomplete")

    def test_split_at_sentence_end_question_mark(self):
        text = "Is this the first? This is second. Still typing"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "Is this the first? This is second.")
        self.assertEqual(remainder, "Still typing")

    def test_split_at_sentence_end_exclamation(self):
        text = "Hello there! Nice day. Writing tests"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "Hello there! Nice day.")
        self.assertEqual(remainder, "Writing tests")

    def test_split_at_sentence_end_no_punctuation(self):
        text = "This is a test without punctuation"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "")
        self.assertEqual(remainder, text)

    def test_split_at_sentence_end_multiple_markers(self):
        text = "What is this?! Another sentence. Still going"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "What is this?! Another sentence.")
        self.assertEqual(remainder, "Still going")

    def test_split_at_sentence_end_international(self):
        text = "这是中文。This is English. Still typing"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "这是中文。This is English.")
        self.assertEqual(remainder, "Still typing")

    def test_split_at_sentence_end_multiple_spaces(self):
        text = "First sentence.    Second sentence.     Third incomplete"
        first, remainder = self.translator.split_at_sentence_end(text)
        self.assertEqual(first, "First sentence. Second sentence.")  # NLTK normalizes whitespace
        self.assertEqual(remainder, "Third incomplete")

    def test_manual_split_fallback(self):
        # Create translator with NLTK disabled
        translator_no_nltk = TranslationManager()
        translator_no_nltk.sent_tokenize = None  # Simulate NLTK not being available
        
        text = "First sentence. Second sentence. Third incomplete"
        first, remainder = translator_no_nltk.split_at_sentence_end(text)
        self.assertEqual(first, "First sentence. Second sentence.")
        self.assertEqual(remainder, "Third incomplete")

if __name__ == '__main__':
    unittest.main()