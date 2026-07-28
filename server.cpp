// Клієнт захоплення звуку для AI-конспектора.
//
// Що змінилось порівняно з першою версією і чому:
//
// 1. Аудіо-callback PortAudio — це realtime-контекст. Блокуючий send() і
//    std::cout всередині нього означають, що коли Python затупить, TCP-буфер
//    заповниться, callback заблокується і звук почне глітчити. Тут callback лише
//    пише у lock-free ring buffer; мережа і вивід — в окремих потоках.
//
// 2. send() має право віддати менше байтів, ніж просили. Раніше результат
//    ігнорувався, тож потік тихо зсувався на непарну кількість байтів і далі
//    йшла каша замість звуку. Тепер повний цикл дозапису.
//
// 3. Номер пристрою валідується — інакше Pa_GetDeviceInfo(99) віддає nullptr
//    і програма падає.
//
// 4. Потік завжди 16 кГц mono int16: Whisper однаково ресемплить у 16 кГц, а
//    44.1 кГц — це 2.75x зайвого трафіку й часу завантаження. Якщо пристрій не
//    вміє 16 кГц, ресемплимо тут (з антиаліасинговим фільтром).
//
// Збірка:  ./build.sh     (або: g++ -O2 -std=c++17 server.cpp -lportaudio -lpthread -o audio_capture)

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <portaudio.h>

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace {

constexpr int   TARGET_RATE = 16000;   // те, що очікує сервер
constexpr int   FRAMES_PER_BUFFER = 512;
constexpr char  SERVER_HOST[] = "127.0.0.1";
constexpr int   SERVER_PORT = 8085;
constexpr double ANTIALIAS_HZ = 7000.0;  // < 16000/2, з запасом

std::atomic<bool> g_running{true};
std::atomic<float> g_level{0.0f};
std::atomic<uint64_t> g_dropped{0};

// ---------------------------------------------------------------- ring buffer

// SPSC: пише лише аудіо-callback, читає лише sender-потік. Монотонні індекси
// без модуля прибирають класичну неоднозначність "повний vs порожній".
class RingBuffer {
public:
    explicit RingBuffer(size_t capacity) : buf_(capacity), cap_(capacity) {}

    // producer (аудіо-callback): нічого не блокує, нічого не виділяє
    bool write(const int16_t* src, size_t n) {
        const uint64_t head = head_.load(std::memory_order_relaxed);
        const uint64_t tail = tail_.load(std::memory_order_acquire);
        if ((head - tail) + n > cap_) {
            g_dropped.fetch_add(n, std::memory_order_relaxed);
            return false;  // краще втратити кадр, ніж заблокувати realtime-потік
        }
        for (size_t i = 0; i < n; ++i) {
            buf_[(head + i) % cap_] = src[i];
        }
        head_.store(head + n, std::memory_order_release);
        return true;
    }

    // consumer (sender-потік)
    size_t read(int16_t* dst, size_t want) {
        const uint64_t head = head_.load(std::memory_order_acquire);
        const uint64_t tail = tail_.load(std::memory_order_relaxed);
        const size_t available = static_cast<size_t>(head - tail);
        const size_t n = std::min(available, want);
        for (size_t i = 0; i < n; ++i) {
            dst[i] = buf_[(tail + i) % cap_];
        }
        tail_.store(tail + n, std::memory_order_release);
        return n;
    }

private:
    std::vector<int16_t> buf_;
    size_t cap_;
    std::atomic<uint64_t> head_{0};
    std::atomic<uint64_t> tail_{0};
};

// ------------------------------------------------------------ DSP: фільтр + ресемпл

// Biquad low-pass (RBJ cookbook). Потрібен перед прорідженням: без нього
// частоти вище 8 кГц завертаються у чутний діапазон і псують розпізнавання.
struct Biquad {
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;

    void designLowpass(double fs, double fc, double q = 0.707) {
        const double w0 = 2.0 * M_PI * fc / fs;
        const double cs = std::cos(w0);
        const double alpha = std::sin(w0) / (2.0 * q);
        const double a0 = 1.0 + alpha;
        b0 = ((1.0 - cs) / 2.0) / a0;
        b1 = (1.0 - cs) / a0;
        b2 = ((1.0 - cs) / 2.0) / a0;
        a1 = (-2.0 * cs) / a0;
        a2 = (1.0 - alpha) / a0;
    }

    double process(double x) {
        const double y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1; x1 = x;
        y2 = y1; y1 = y;
        return y;
    }
};

// Лінійна інтерполяція з переносом дробової позиції між блоками —
// інакше на межі блоків з'являються клацання.
struct Resampler {
    double ratio = 1.0;  // in_rate / out_rate
    double pos = 0.0;
    int16_t prev = 0;
    bool primed = false;

    void process(const int16_t* in, size_t n, std::vector<int16_t>& out) {
        if (n == 0) return;
        if (!primed) { prev = in[0]; primed = true; }

        while (true) {
            const long idx = static_cast<long>(std::floor(pos));
            if (idx + 1 >= static_cast<long>(n)) break;
            const double frac = pos - static_cast<double>(idx);
            const double a = (idx < 0) ? static_cast<double>(prev)
                                       : static_cast<double>(in[idx]);
            const double b = static_cast<double>(in[idx + 1]);
            const double v = a + (b - a) * frac;
            out.push_back(static_cast<int16_t>(
                std::lround(std::clamp(v, -32768.0, 32767.0))));
            pos += ratio;
        }
        pos -= static_cast<double>(n);
        prev = in[n - 1];
    }
};

// ------------------------------------------------------------------- мережа

int connectToServer(bool verbose) {
    int sock = ::socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return -1;

    int one = 1;
    ::setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(SERVER_PORT);
    ::inet_pton(AF_INET, SERVER_HOST, &addr.sin_addr);

    while (g_running.load()) {
        if (::connect(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0) {
            return sock;
        }
        if (verbose) {
            std::cout << "\rОчікую Python-сервер на " << SERVER_HOST << ":" << SERVER_PORT
                      << "…            " << std::flush;
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    ::close(sock);
    return -1;
}

// Повний запис: send() може віддати менше, ніж просили.
bool sendAll(int sock, const void* data, size_t len) {
    const auto* p = static_cast<const uint8_t*>(data);
    size_t sent = 0;
    while (sent < len) {
        // MSG_NOSIGNAL: без нього обрив з'єднання вбиває процес через SIGPIPE.
        const ssize_t n = ::send(sock, p + sent, len - sent, MSG_NOSIGNAL);
        if (n > 0) {
            sent += static_cast<size_t>(n);
            continue;
        }
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) {
            continue;
        }
        return false;
    }
    return true;
}

bool sendHandshake(int sock) {
    uint8_t header[8] = {'C', 'N', 'S', 'P', 0, 0, 0, 0};
    const uint32_t rate = TARGET_RATE;  // little-endian, як читає Python
    std::memcpy(header + 4, &rate, sizeof(rate));
    return sendAll(sock, header, sizeof(header));
}

// --------------------------------------------------------------- callback

struct CallbackContext {
    RingBuffer* ring;
};

int audioCallback(const void* inputBuffer, void* /*outputBuffer*/,
                  unsigned long framesPerBuffer,
                  const PaStreamCallbackTimeInfo* /*timeInfo*/,
                  PaStreamCallbackFlags /*statusFlags*/,
                  void* userData) {
    auto* ctx = static_cast<CallbackContext*>(userData);
    const auto* in = static_cast<const int16_t*>(inputBuffer);
    if (in == nullptr) return paContinue;

    ctx->ring->write(in, framesPerBuffer);

    // Індикатор рівня: лише атомарний store, жодного I/O в realtime-контексті.
    double sum = 0.0;
    for (unsigned long i = 0; i < framesPerBuffer; ++i) {
        const double v = in[i] / 32768.0;
        sum += v * v;
    }
    g_level.store(static_cast<float>(std::sqrt(sum / framesPerBuffer)),
                  std::memory_order_relaxed);

    return paContinue;
}

// ----------------------------------------------------------------- потоки

void senderThread(RingBuffer* ring, int deviceRate) {
    const bool needsResample = (deviceRate != TARGET_RATE);

    Biquad filter;
    Resampler resampler;
    if (needsResample) {
        filter.designLowpass(static_cast<double>(deviceRate), ANTIALIAS_HZ);
        resampler.ratio = static_cast<double>(deviceRate) / static_cast<double>(TARGET_RATE);
        std::cout << "Пристрій дає " << deviceRate << " Hz — ресемплю до "
                  << TARGET_RATE << " Hz.\n";
    }

    int sock = connectToServer(true);
    if (sock < 0) return;
    if (!sendHandshake(sock)) {
        ::close(sock);
        return;
    }
    std::cout << "Підключено до Python-сервера.\n";

    std::vector<int16_t> chunk(4096);
    std::vector<int16_t> filtered;
    std::vector<int16_t> out;

    while (g_running.load()) {
        const size_t n = ring->read(chunk.data(), chunk.size());
        if (n == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        const int16_t* payload = chunk.data();
        size_t payloadCount = n;

        if (needsResample) {
            filtered.clear();
            filtered.reserve(n);
            for (size_t i = 0; i < n; ++i) {
                const double y = filter.process(static_cast<double>(chunk[i]));
                filtered.push_back(static_cast<int16_t>(
                    std::lround(std::clamp(y, -32768.0, 32767.0))));
            }
            out.clear();
            resampler.process(filtered.data(), filtered.size(), out);
            if (out.empty()) continue;
            payload = out.data();
            payloadCount = out.size();
        }

        if (!sendAll(sock, payload, payloadCount * sizeof(int16_t))) {
            std::cout << "\nЗ'єднання втрачено — перепідключаюсь…\n";
            ::close(sock);
            sock = connectToServer(false);
            if (sock < 0) return;
            if (!sendHandshake(sock)) { ::close(sock); return; }
            std::cout << "Перепідключено.\n";
        }
    }

    ::close(sock);
}

void meterThread() {
    while (g_running.load()) {
        const float rms = g_level.load(std::memory_order_relaxed);
        int bars = static_cast<int>(rms * 150.0f);
        bars = std::clamp(bars, 0, 40);

        std::string line = "\rСтримінг [";
        line.append(bars, '#');
        line.append(40 - bars, ' ');
        line += "] ";

        const uint64_t dropped = g_dropped.load(std::memory_order_relaxed);
        if (dropped > 0) {
            line += "втрачено семплів: " + std::to_string(dropped) + " ";
        }
        std::cout << line << std::flush;
        std::this_thread::sleep_for(std::chrono::milliseconds(80));
    }
}

// ------------------------------------------------------------ вибір пристрою

int pickDevice() {
    const int deviceCount = Pa_GetDeviceCount();
    if (deviceCount < 0) {
        std::cerr << "Pa_GetDeviceCount: " << Pa_GetErrorText(deviceCount) << "\n";
        return -1;
    }

    std::vector<int> inputs;
    std::cout << "=== Доступні пристрої запису ===\n";
    for (int i = 0; i < deviceCount; ++i) {
        const PaDeviceInfo* info = Pa_GetDeviceInfo(i);
        if (info != nullptr && info->maxInputChannels > 0) {
            std::cout << "[" << i << "] " << info->name << "\n";
            inputs.push_back(i);
        }
    }
    if (inputs.empty()) {
        std::cerr << "Не знайдено жодного пристрою запису.\n";
        return -1;
    }

    // Валідація: раніше довільне число доходило до Pa_GetDeviceInfo і давало segfault.
    while (true) {
        std::cout << "\nНомер пристрою (Enter — за замовчуванням " << inputs.front() << "): ";
        std::string line;
        if (!std::getline(std::cin, line)) return inputs.front();
        if (line.empty()) return inputs.front();

        try {
            const int choice = std::stoi(line);
            if (std::find(inputs.begin(), inputs.end(), choice) != inputs.end()) {
                return choice;
            }
        } catch (const std::exception&) {
            // впаде в повідомлення нижче
        }
        std::cout << "Немає такого пристрою запису. Спробуй ще раз.\n";
    }
}

int pickSampleRate(const PaStreamParameters& params, const PaDeviceInfo* info) {
    // Найдешевше — попросити 16 кГц одразу; далі типові варіанти.
    const double candidates[] = {
        static_cast<double>(TARGET_RATE), info->defaultSampleRate, 48000, 44100, 32000,
    };
    for (double rate : candidates) {
        if (rate <= 0) continue;
        if (Pa_IsFormatSupported(&params, nullptr, rate) == paFormatIsSupported) {
            return static_cast<int>(rate);
        }
    }
    return 0;
}

}  // namespace

int main() {
    PaError err = Pa_Initialize();
    if (err != paNoError) {
        std::cerr << "Pa_Initialize: " << Pa_GetErrorText(err) << "\n";
        return 1;
    }

    const int device = pickDevice();
    if (device < 0) {
        Pa_Terminate();
        return 1;
    }

    const PaDeviceInfo* info = Pa_GetDeviceInfo(device);
    if (info == nullptr) {
        std::cerr << "Не вдалося отримати інформацію про пристрій.\n";
        Pa_Terminate();
        return 1;
    }

    PaStreamParameters params{};
    params.device = device;
    params.channelCount = 1;
    params.sampleFormat = paInt16;
    params.suggestedLatency = info->defaultLowInputLatency;
    params.hostApiSpecificStreamInfo = nullptr;

    const int rate = pickSampleRate(params, info);
    if (rate == 0) {
        std::cerr << "Пристрій не підтримує жодну зі стандартних частот.\n";
        Pa_Terminate();
        return 1;
    }

    // Запас на 30 секунд — щоб пауза в мережі не з'їдала звук одразу.
    RingBuffer ring(static_cast<size_t>(rate) * 30);
    CallbackContext ctx{&ring};

    PaStream* stream = nullptr;
    err = Pa_OpenStream(&stream, &params, nullptr, static_cast<double>(rate),
                        FRAMES_PER_BUFFER, paClipOff, audioCallback, &ctx);
    if (err != paNoError) {
        std::cerr << "Pa_OpenStream: " << Pa_GetErrorText(err) << "\n";
        Pa_Terminate();
        return 1;
    }

    err = Pa_StartStream(stream);
    if (err != paNoError) {
        std::cerr << "Pa_StartStream: " << Pa_GetErrorText(err) << "\n";
        Pa_CloseStream(stream);
        Pa_Terminate();
        return 1;
    }

    std::thread sender(senderThread, &ring, rate);
    std::thread meter(meterThread);

    std::cout << "\nЗапис активний (" << rate << " Hz). Натисни Enter, щоб зупинити.\n";
    std::string dummy;
    std::getline(std::cin, dummy);

    g_running.store(false);
    if (sender.joinable()) sender.join();
    if (meter.joinable()) meter.join();

    Pa_StopStream(stream);
    Pa_CloseStream(stream);
    Pa_Terminate();

    const uint64_t dropped = g_dropped.load();
    std::cout << "\nЗавершено.";
    if (dropped > 0) {
        std::cout << " Втрачено семплів через переповнення буфера: " << dropped
                  << " (сервер не встигав).";
    }
    std::cout << "\n";
    return 0;
}
