import socket
import struct
import numpy as np
import whisper
import requests
import json

def send_to_ollama(text):
    """Відправка тексту в локальну Ollama для структурування конспекту"""
    url = "http://localhost:11434/api/generate"
    prompt = f"Ти асистент для студентів. Зроби грамотний, структурований конспект з цього шматка транскрипції лекції. Використовуй списки та жирний шрифт де треба: {text}"
    
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.json().get('response', '')
    except Exception as e:
        return f"[Помилка Ollama: {e}]"

def main():
    HOST = '0.0.0.0' # Слухаємо всю мережу
    PORT = 8080
    PACKET_SIZE = 4096 
    SAMPLE_RATE = 44100
    
    # Завантажуємо модель розпізнавання мовлення (base або tiny для швидкості)
    print("⏳ Завантаження моделі Whisper...")
    model = whisper.load_model("base")
    print("✅ Модель Whisper готова до роботи!")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)

    print(f"📡 Сервер чекає на звук від ноутбука на порту {PORT}...")
    conn, addr = server_socket.accept()
    print(f"🤝 Ноутбук підключився: {addr}")

    audio_buffer = []
    # Скільки фреймів накопичувати перед відправкою в ШІ (наприклад, ~5 секунд звуку)
    CHUNKS_TO_PROCESS = (SAMPLE_RATE * 5) // 1024 
    chunk_counter = 0

    try:
        while True:
            data = conn.recv(PACKET_SIZE)
            if not data:
                break

            floats_count = len(data) // 4
            if floats_count == 0: continue

            pure_data = data[:floats_count * 4]
            samples = struct.unpack(f"{floats_count}f", pure_data)
            
            # Додаємо отримані float-значення в наш великий буфер
            audio_buffer.extend(samples)
            chunk_counter += 1

            # Кожні 5 секунд аналізуємо накопичений звук
            if chunk_counter >= CHUNKS_TO_PROCESS:
                # Перетворюємо в numpy array (формат, який розуміє Whisper)
                audio_np = np.array(audio_buffer, dtype=np.float32)
                
                print("\n🎙️ [Whisper] Розпізнаю мовлення...")
                # Транскрибація (можна вказати language="uk", якщо лекція українською)
                result = model.transcribe(audio_np, fp16=False, language="uk")
                raw_text = result["text"].strip()
                
                if raw_text:
                    print(f"📝 Розпізнано: {raw_text}")
                    print("🤖 [Ollama] Формую конспект...")
                    formatted_notes = send_to_ollama(raw_text)
                    
                    print("\n--- ПОТОЧНИЙ КОНСПЕКТ ---")
                    print(formatted_notes)
                    print("-------------------------\n")
                else:
                    print("...тиша або нерозбірливо...")

                # Очищаємо буфер для наступних 5 секунд
                audio_buffer = []
                chunk_counter = 0

    except KeyboardInterrupt:
        print("\nЗупинка сервера.")
    finally:
        conn.close()
        server_socket.close()

if __name__ == "__main__":
    main()