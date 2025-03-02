import openai
from whisper_online_server import ServerProcessor

class TranslatedServerProcessor(ServerProcessor):
    def __init__(self, *args, target_language='en', **kwargs):
        super().__init__(*args, **kwargs)
        self.target_language = target_language

    def translate_text(self, text):
        response = openai.Completion.create(
            engine="gpt-4o-mini",
            prompt=f"This is a speech transcript: \"{text}\"\n\nTranslate this transcript to {self.target_language}. Output only the translated text without any explanations, notes, or additional content.",
            max_tokens=1000
        )
        return response.choices[0].text.strip()

    def send_result(self, result):
        translated_text = self.translate_text(result['text'])
        result['text'] = translated_text
        super().send_result(result)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Whisper Streaming Server with Translation')
    parser.add_argument('--target-language', type=str, default='en', help='Target language for translation')
    args = parser.parse_args()

    processor = TranslatedServerProcessor(target_language=args.target_language)
    processor.run()
