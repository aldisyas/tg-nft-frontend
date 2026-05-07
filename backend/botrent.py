import telebot
import json
import sqlite3
import os
from flask import Flask, jsonify
from flask_cors import CORS
import threading
from dotenv import load_dotenv

load_dotenv()

# --- 1. KONFIGURASI AWAL ---
TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID'))
URL_VERCEL = "https://tg-nft-frontend.vercel.app"

# Lokasi Database (Taruh di sini supaya bisa dibaca Flask & Bot)
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, 'database.db')

# --- 2. SETUP FLASK (WEB API) ---
app = Flask(__name__)
CORS(app)

@app.route('/api/assets', methods=['GET'])
def get_assets():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, price, icon, is_locked FROM assets")
        rows = cursor.fetchall()
        conn.close()
        
        assets = []
        for row in rows:
            assets.append({
                "name": row[0],
                "price": row[1],
                "icon": row[2],
                "is_locked": bool(row[3])
            })
        return jsonify(assets)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask():
    # Menjalankan server di port 5000
    app.run(port=5000, debug=False, use_reloader=False)

# --- 3. SETUP DATABASE ---
def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tabel Assets: Menambahkan kolom seller_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            icon TEXT DEFAULT '💎',
            is_locked INTEGER DEFAULT 0,
            seller_id INTEGER
        )
    ''')

    # Tabel Users: Menyimpan data semua orang yang pernah /start
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'user' -- 'owner', 'admin', 'seller', atau 'user'
        )
    ''')

    # Tabel Transactions: Untuk pencatatan riwayat (Owner/Admin bisa cek)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name TEXT,
            buyer_id INTEGER,
            buyer_username TEXT,
            seller_id INTEGER,
            duration TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database Multi-Role & Multi-Seller siap!")

init_db()

# --- 3.5 FUNGSI HELPER ROLE  ---
def get_user_role(user_id):
    if user_id == OWNER_ID: # <--- Ganti ADMIN_ID jadi OWNER_ID di sini
        return "owner"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- 4. SETUP BOT ---
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    # Simpan data user ke database
    uid = message.from_user.id
    uname = message.from_user.username
    fname = message.from_user.first_name
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # INSERT OR IGNORE supaya kalau dia /start lagi, data lamanya nggak error
    # UPDATE digunakan kalau kamu mau username-nya selalu update di database
    cursor.execute('''
        INSERT INTO users (user_id, username, full_name, role) 
        VALUES (?, ?, ?, 'user')
        ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name
    ''', (uid, uname, fname))
    conn.commit()
    conn.close()

    # Tampilan pesan selamat datang tetap sama seperti sebelumnya
    markup = telebot.types.InlineKeyboardMarkup()
    web_app = telebot.types.WebAppInfo(URL_VERCEL)
    btn = telebot.types.InlineKeyboardButton("🛒 Buka Marketplace", web_app=web_app)
    markup.add(btn)
    
    teks = f"👋 Halo {fname}!\nSelamat datang di FRAGGMENT Bot..."
    bot.send_message(message.chat.id, teks, reply_markup=markup)

@bot.message_handler(commands=['promote'])
def promote_user(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Hanya Owner yang bisa merubah role!")
        return

    try:
        args = message.text.split()
        target_id = int(args[1])
        new_role = args[2].lower() # 'admin', 'seller', atau 'user'

        if new_role not in ['admin', 'seller', 'user']:
            bot.reply_to(message, "❌ Role harus: admin, seller, atau user")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, target_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            bot.reply_to(message, f"✅ User {target_id} sekarang menjadi {new_role}")
            try:
                bot.send_message(target_id, f"🎉 Selamat! Kamu telah diangkat menjadi **{new_role}**.")
            except: pass
        else:
            bot.reply_to(message, "❌ User ID tidak ditemukan. Orang tersebut harus /start bot dulu!")
        conn.close()
    except Exception:
        bot.reply_to(message, "❌ Format salah! Contoh: `/promote 12345678 seller`")

@bot.message_handler(commands=['add'])
def add_asset_command(message):
    role = get_user_role(message.from_user.id)
    
    # Cek apakah user punya akses (Owner, Admin, atau Seller)
    if not role:
        bot.reply_to(message, "❌ Kamu tidak punya akses untuk menambah aset!")
        return

    try:
        content = message.text.split(' ', 1)[1]
        data = content.split('|')
        
        name = data[0].strip()
        price = data[1].strip()
        icon = data[2].strip() if len(data) > 2 else '💎'
        locked = int(data[3].strip()) if len(data) > 3 else 0
        
        # Logika Penentuan Seller ID
        if role in ['owner', 'admin']:
            # Jika Owner/Admin input ID Seller di akhir, pakai itu. Jika tidak, pakai ID diri sendiri.
            s_id = int(data[4].strip()) if len(data) > 4 else message.from_user.id
        else:
            # Seller biasa otomatis jadi pemilik aset yang dia input
            s_id = message.from_user.id

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO assets (name, price, icon, is_locked, seller_id) VALUES (?, ?, ?, ?, ?)", 
                       (name, price, icon, locked, s_id))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"✅ Berhasil Ditambah!\nNama: {name}\nHarga: {price}\nSeller ID: {s_id}")
    except Exception as e:
        bot.reply_to(message, "❌ Format salah! Contoh:\n/add @name|10 TON|⭐|0|[ID_Seller_Opsional]")

@bot.message_handler(commands=['delete'])
def delete_asset_command(message):
    role = get_user_role(message.from_user.id)
    
    if not role:
        bot.reply_to(message, "❌ Kamu tidak punya akses!")
        return

    try:
        # Format: /delete [NamaAset] -> Contoh: /delete @mayra
        asset_name = message.text.split(' ', 1)[1].strip()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Cek dulu asetnya ada atau nggak, dan siapa pemiliknya
        cursor.execute("SELECT seller_id FROM assets WHERE name = ?", (asset_name,))
        result = cursor.fetchone()

        if not result:
            bot.reply_to(message, f"❌ Aset {asset_name} tidak ditemukan.")
            conn.close()
            return

        target_seller_id = result[0]

        # 2. Logika Izin Hapus
        # Owner & Admin bisa hapus semuanya. Seller cuma bisa hapus miliknya sendiri.
        if role in ['owner', 'admin'] or message.from_user.id == target_seller_id:
            cursor.execute("DELETE FROM assets WHERE name = ?", (asset_name,))
            conn.commit()
            bot.reply_to(message, f"🗑️ Aset {asset_name} berhasil dihapus!")
        else:
            bot.reply_to(message, "❌ Kamu hanya bisa menghapus aset milikmu sendiri!")

        conn.close()
    except Exception:
        bot.reply_to(message, "❌ Format salah! Contoh: `/delete @username`")

@bot.message_handler(content_types=['web_app_data'])
def handle_data(message):
    try:
        data = json.loads(message.web_app_data.data)
        aset_name = data.get('nama_aset')
        durasi = data.get('durasi_sewa')
        buyer_uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        buyer_id = message.from_user.id

        # 1. Cari siapa Seller dari aset ini di database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT seller_id FROM assets WHERE name = ?", (aset_name,))
        result = cursor.fetchone()
        
        # Jika seller_id di aset kosong, notif lari ke Owner sebagai backup
        target_seller = result[0] if result and result[0] else OWNER_ID

        # 2. Catat ke Tabel Transactions (Arsip untuk Owner)
        cursor.execute('''
            INSERT INTO transactions (asset_name, buyer_id, buyer_username, seller_id, duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (aset_name, buyer_id, buyer_uname, target_seller, durasi))
        conn.commit()
        conn.close()

        # 3. Kirim Notif HANYA ke Seller yang bersangkutan
        format_notif = (
            f"📩 **PESANAN RENTAL BARU**\n"
            f"--------------------------\n"
            f"📦 Aset: {aset_name}\n"
            f"⏱ Durasi: {durasi}\n"
            f"👤 Penyewa: {buyer_uname} (ID: `{buyer_id}`)\n"
        )
        bot.send_message(target_seller, format_notif, parse_mode="Markdown")
        
        # 4. Konfirmasi ke Buyer (Penyewa)
        bot.send_message(message.chat.id, "✅ **Pesanan Terkirim!** Seller akan segera menghubungimu.")
        
    except Exception as e:
        print(f"Error handle_data: {e}")

# --- 5. RUN ALL ---
if __name__ == '__main__':
    print("🚀 Flask API berjalan di http://127.0.0.1:5000/api/assets")
    print("🤖 Bot sedang berjalan...")
    
    # Flask di thread terpisah
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Bot di thread utama
    bot.infinity_polling()