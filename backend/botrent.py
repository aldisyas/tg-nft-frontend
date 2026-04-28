import telebot
import json

# --- KONFIGURASI ---
TOKEN = '8729372695:AAFtfR9x_r-w-SEkmdnwUfyqtix_pBc8jSY'
ADMIN_ID = 7668521623  # GANTI DENGAN ID TELEGRAM KAMU
URL_VERCEL = "https://tg-nft-frontend.vercel.app"

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.InlineKeyboardMarkup()
    # Tombol untuk membuka Mini App
    web_app = telebot.types.WebAppInfo(URL_VERCEL)
    btn = telebot.types.InlineKeyboardButton("🛒 Buka Marketplace", web_app=web_app)
    markup.add(btn)
    
    teks = (
        "👋 Selamat datang di FRAGGMENT Bot!\n\n"
        "Di sini kamu bisa menyewa Username atau Gift Telegram.\n"
        "Klik tombol di bawah untuk melihat katalog aset."
    )
    bot.send_message(message.chat.id, teks, reply_markup=markup)

# Fungsi untuk menangkap data dari Mini App (saat tombol Sewa diklik)
@bot.message_handler(content_types=['web_app_data'])
def handle_data(message):
    # Mengambil data JSON yang dikirim dari index.html
    data = json.loads(message.web_app_data.data)
    
    aset = data.get('nama_aset')
    durasi = data.get('durasi_sewa')
    pembeli = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    # 1. Pesanan Masuk ke Admin
    format_admin = (
        f"📩 **PESANAN RENTAL BARU**\n"
        f"--------------------------\n"
        f"📦 Aset: {aset}\n"
        f"⏱ Durasi: {durasi}\n"
        f"👤 Penyewa: {pembeli} (ID: `{message.from_user.id}`)\n"
        f"--------------------------\n"
        f"Silakan hubungi penyewa untuk proses pembayaran."
    )
    bot.send_message(ADMIN_ID, format_admin, parse_mode="Markdown")

    # 2. Konfirmasi ke Pembeli
    bot.send_message(message.chat.id, "✅ **Pesanan Terkirim!**\n\nFormat pesanan Anda sudah diteruskan ke Admin. Mohon tunggu Admin menghubungi Anda.")

print("Bot sedang berjalan...")
bot.polling()