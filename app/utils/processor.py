import time

def process_audio_file(input_path: str, output_path: str):
    time.sleep(3)
    return {
        "original_transcript": "Привет меня зовут Иван Иванов, мой телефон 89991234567",
        "redacted_transcript": "Привет меня зовут [ИМЯ] [ФАМИЛИЯ], мой телефон [ТЕЛЕФОН]",
        "entities": [
            {
                "type": "PERSON",
                "text": "Иван Иванов",
                "start_char": 20,
                "end_char": 31,
                "start_sec": 1.2,
                "end_sec": 2.4
            },
            {
                "type": "PHONE",
                "text": "89991234567",
                "start_char": 45,
                "end_char": 56,
                "start_sec": 3.1,
                "end_sec": 4.0
            }
        ],
        "redacted_audio_path": output_path + "/redacted.mp3",
        "log": [
            {"type": "PERSON", "text": "Иван Иванов", "replaced_with": "[ИМЯ] [ФАМИЛИЯ]"},
            {"type": "PHONE", "text": "89991234567", "replaced_with": "[ТЕЛЕФОН]"}
        ]
    }