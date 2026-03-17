# 🤖 Life Planner Bot

> Telegram bot — har bir foydalanuvchiga shaxsiy haftalik tartib tuzib beradi.  
> Groq AI (bepul) + Pytesseract OCR + Pillow rasm generatsiyasi.

---

## ✨ Xususiyatlar

- 👥 **Ko'p foydalanuvchili** — har kim o'z ma'lumotlarini kiritadi, alohida tartib oladi
- 🧠 **AI tartib** — Groq LLaMA 3.3 70B asosida shaxsiy haftalik jadval tuzadi
- 📸 **Rasm OCR** — dars jadvalini rasm sifatida yuboring, bot o'qib oladi
- 🖼 **Kunlik rasm** — har kuni uyg'onishdan 5 daqiqa oldin chiroyli rasmda tartib yuboriladi
- 🛒 **Xarid ro'yxati** — byudjet va allergiyaga mos haftalik oziq-ovqat ro'yxati
- 💾 **JSON saqlash** — barcha ma'lumotlar `users.json` da saqlanadi
- 🔄 **Qayta sozlash** — istalgan vaqtda ma'lumotlarni yangilash mumkin

---

## 📱 Foydalanuvchi oqimi

```
/start
  └─ Bot haqida ma'lumot + "Boshlash" tugmasi
       └─ Holat: Ishlayman / O'qiyman / Ikkalasi
            └─ Dars jadvali (📷 rasm yoki ✏️ matn)
                 └─ Boy → Yosh → Vazn
                      └─ Maqsad (6 variant)
                           └─ Byudjet (4 variant)
                                └─ Allergiya
                                     └─ AI ~20 sek tartib tuzadi
                                          └─ Bugungi tartib rasmi yuboriladi
                                               └─ Har kuni eslatma
```

---

## 🚀 O'rnatish

### 1. Reponi klonlash

```bash
git clone https://github.com/username/student-life-planner-bot.git
cd student-life-planner-bot
```

### 2. Virtual muhit va kutubxonalar

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Tesseract OCR o'rnatish

**Windows:**
1. [Tesseract o'rnatuvchisini yuklab oling](https://github.com/UB-Mannheim/tesseract/wiki)
2. O'rnatishda **Uzbek**, **Russian**, **English** tillarini belgilang
3. `bot.py` ichidagi bu qatordan `#` ni olib tashlang:

```python
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr tesseract-ocr-uzb tesseract-ocr-rus -y
```

**macOS:**
```bash
brew install tesseract tesseract-lang
```

### 4. API kalitlarini olish

**Telegram Bot Token** (bepul):
1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing
2. `/newbot` → nom bering → token oling

**Hugging face(DeepSeek v2) ** 
1. [[console.groq.com](https://console.groq.com](https://huggingface.co/settings/tokens)) ga kiring
2. **API Keys** → **Create API Key** → nusxalang

### 5. Sozlash

`bot.py` faylini oching, quyidagi qatorlarni toping:

```python
BOT_TOKEN    = "YOUR_BOT_TOKEN_HERE"
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
```

### 6. Ishga tushirish

```bash
python bot.py
```

---

## 📁 Fayl tuzilmasi

```
student-life-planner-bot/
├── bot.py            # Asosiy bot kodi
├── requirements.txt  # Python kutubxonalari
├── README.md         # Shu fayl
└── users.json        # Foydalanuvchilar (avtomatik yaratiladi)
```

---

## 📦 Kutubxonalar

| Kutubxona | Versiya | Maqsad |
|-----------|---------|--------|
| python-telegram-bot | 21.6 | Telegram Bot API |
| httpx | 0.27.2 | Groq API so'rovlari |
| Pillow | 10.4.0 | Rasm generatsiyasi |
| APScheduler | 3.10.4 | Kunlik eslatmalar |
| pytesseract | 0.3.13 | OCR (rasm → matn) |

---

## ⚙️ Bot menyusi

| Tugma | Funksiya |
|-------|----------|
| 📅 Bugungi tartib | Bugungi kun uchun tartib rasmi |
| 🗓 Haftalik tartib | 7 kunlik qisqacha ko'rinish |
| 🛒 Xarid ro'yxati | Haftalik oziq-ovqat va narxlar |
| ℹ️ Mening ma'lumotim | Kiritilgan barcha ma'lumotlar |
| 🔄 Qayta sozlash | Hamma narsani o'chirib qayta boshlash |

---

## 🌍 Deploy

### Railway.app (bepul)

1. [railway.app](https://railway.app) ga kiring
2. **New Project** → **Deploy from GitHub repo**
3. Environment variables qo'shing:
   - `BOT_TOKEN` = tokeningiz
   - `GROQ_API_KEY` = Groq keyingiz
4. Start command: `python bot.py`

### VPS (Linux systemd)

```bash
sudo nano /etc/systemd/system/planner-bot.service
```

```ini
[Unit]
Description=Student Life Planner Bot
After=network.target

[Service]
WorkingDirectory=/home/user/student-life-planner-bot
ExecStart=/home/user/student-life-planner-bot/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable planner-bot
sudo systemctl start planner-bot
sudo systemctl status planner-bot
```

---

## ⚠️ Muhim eslatma

`users.json` faylini `.gitignore` ga qo'shing — unda foydalanuvchilar shaxsiy ma'lumotlari saqlanadi:

```
users.json
venv/
__pycache__/
*.pyc
.env
```

---

## 🤝 Hissa qo'shish


---

## 📄 Litsenziya

