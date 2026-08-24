import telebot
import requests
import json
import sqlite3
import random
import string
import time
import logging
import os
from datetime import datetime, timedelta
from flask import Flask, request

# ==================== CONFIGURATION ====================
# Railway par environment variable se token lo
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8001120680:AAEWhwliUYTIyb-VirkirYbUyiG195PvH7k')
ADMIN_IDS = [int(id.strip()) for id in os.environ.get('ADMIN_IDS', '7229517038').split(',')]

# API Configuration
API_URL = "https://adminpanels.shop/api/reseller_v1.php"
API_KEY = "e92cd3bfe0dc9ec696a0b4ebc22e18b3"
MASTER_KEY = "a7f3e8b2c9d1f4a6b8c2d5e9f1a3b6c8"

# Product prices (INR)
PRODUCT_PRICES = {
    "1 Day": 50,
    "3 Days": 120,
    "7 Days": 250,
    "30 Days": 800
}

# UPI Payment Details (Change karein)
UPI_ID = os.environ.get('UPI_ID', 'your-upi@upi')
BANK_DETAILS = os.environ.get('BANK_DETAILS', 'Bank: XYZ Bank, Account: 1234567890')

# ==================== FLASK APP ====================
app = Flask(__name__)

# ==================== TELEGRAM BOT ====================
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== DATABASE SETUP ====================
def init_database():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        join_date TEXT
    )''')
    
    # Orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        product_id TEXT,
        duration TEXT,
        android_id TEXT,
        amount REAL,
        payment_status TEXT DEFAULT 'pending',
        key_generated TEXT DEFAULT '0',
        key_value TEXT,
        order_date TEXT,
        expiry_date TEXT,
        payment_id TEXT
    )''')
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT UNIQUE,
        name TEXT,
        duration TEXT,
        price REAL
    )''')
    
    # Admin logs
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        user_id INTEGER,
        details TEXT,
        timestamp TEXT
    )''')
    
    conn.commit()
    conn.close()

# ==================== DATABASE FUNCTIONS ====================
def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, last_name, join_date) 
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, username or '', first_name or '', last_name or '', datetime.now().isoformat()))
    conn.commit()
    conn.close()

def save_order(order_id, user_id, product_id, duration, android_id, amount, payment_id=''):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # Calculate expiry
    days = int(duration.split()[0])
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    
    c.execute('''INSERT INTO orders 
                 (order_id, user_id, product_id, duration, android_id, amount, payment_id, order_date, expiry_date) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (order_id, user_id, product_id, duration, android_id, amount, payment_id, datetime.now().isoformat(), expiry))
    conn.commit()
    conn.close()

def update_order_with_key(order_id, key_value, status='completed'):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''UPDATE orders SET payment_status=?, key_generated='1', key_value=? WHERE order_id=?''',
              (status, key_value, order_id))
    conn.commit()
    conn.close()

def get_user_orders(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT order_id, product_id, duration, amount, payment_status, key_generated, order_date, key_value 
                 FROM orders WHERE user_id=? ORDER BY order_date DESC LIMIT 10''', (user_id,))
    orders = c.fetchall()
    conn.close()
    return orders

def get_order_by_id(order_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM orders WHERE order_id=?''', (order_id,))
    order = c.fetchone()
    conn.close()
    return order

def get_all_orders():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT order_id, user_id, product_id, duration, amount, payment_status, key_generated, order_date 
                 FROM orders ORDER BY order_date DESC''')
    orders = c.fetchall()
    conn.close()
    return orders

def get_dashboard_stats():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders")
    total_orders = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE payment_status='completed'")
    completed_orders = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM orders WHERE payment_status='completed'")
    total_revenue = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM orders WHERE payment_status='pending'")
    pending_orders = c.fetchone()[0]
    conn.close()
    return {
        'total_users': total_users,
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'pending_orders': pending_orders,
        'total_revenue': total_revenue
    }

# ==================== API FUNCTIONS ====================
def call_api(product_id, duration, android_id=None, action="buy"):
    data = {
        'api_key': API_KEY,
        'action': action,
        'product_id': product_id,
        'duration': duration,
    }
    if android_id:
        data['android_id'] = android_id
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'x-master-key': MASTER_KEY
    }
    
    try:
        response = requests.post(API_URL, data=data, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def generate_key():
    prefix = "VIP"
    timestamp = str(int(time.time()))[-6:]
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{timestamp}-{random_part}"

# ==================== BOT COMMANDS ====================
@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    add_user(user_id, username, first_name, last_name)
    
    welcome_text = f"""
🎉 *Welcome to Premium Store!* 🎉

Hello {first_name}! 👋

I provide premium product keys instantly after payment.

*Available Plans:*
💰 1 Day - ₹{PRODUCT_PRICES['1 Day']}
💰 3 Days - ₹{PRODUCT_PRICES['3 Days']}
💰 7 Days - ₹{PRODUCT_PRICES['7 Days']}
💰 30 Days - ₹{PRODUCT_PRICES['30 Days']}

*Commands:*
/buy - Purchase a product
/mykeys - View your keys
/price - Show prices
/status - Check bot status
/help - Help guide

*Payment:* UPI, Card, Net Banking
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['buy'])
def start_purchase(message):
    user_id = message.chat.id
    
    product_text = "📦 *Select Duration:*\n\n"
    for i, (duration, price) in enumerate(PRODUCT_PRICES.items(), 1):
        product_text += f"{i}. {duration} - ₹{price}\n"
    product_text += "\nReply with number (1-4) or duration name:"
    
    user_data[user_id] = {'step': 'select_product'}
    bot.reply_to(message, product_text, parse_mode='Markdown')

@bot.message_handler(commands=['mykeys'])
def show_keys(message):
    user_id = message.chat.id
    orders = get_user_orders(user_id)
    
    if not orders:
        bot.reply_to(message, "📭 You don't have any keys yet.\nUse /buy to purchase.")
        return
    
    text = "🔑 *Your Keys:*\n\n"
    has_keys = False
    
    for order in orders:
        order_id, product_id, duration, amount, status, key_gen, date, key_value = order
        if key_gen == '1' and key_value:
            has_keys = True
            text += f"✅ *{product_id}* ({duration})\n"
            text += f"🔐 `{key_value}`\n"
            text += f"📅 Valid until: {date[:10]}\n\n"
    
    if not has_keys:
        text = "📭 No active keys found. Purchase using /buy"
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['price'])
def show_prices(message):
    price_text = "💰 *Price List:*\n\n"
    for duration, price in PRODUCT_PRICES.items():
        price_text += f"• {duration}: ₹{price}\n"
    price_text += "\nUse /buy to purchase."
    bot.reply_to(message, price_text, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def check_status(message):
    try:
        # Check database
        stats = get_dashboard_stats()
        status_text = f"""
✅ *Bot Status: Online*

📊 *Statistics:*
👥 Users: {stats['total_users']}
📦 Orders: {stats['total_orders']}
⏳ Pending: {stats['pending_orders']}
💰 Revenue: ₹{stats['total_revenue']}

🕐 Uptime: 24/7
⚡ Response: {len(bot.get_updates())} updates

📍 *System Info:*
Python: 3.9+
Database: SQLite
Host: Railway
        """
        bot.reply_to(message, status_text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Status check failed: {str(e)}")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Access denied! You are not an admin.")
        return
    
    stats = get_dashboard_stats()
    
    admin_text = f"""
🔐 *Admin Panel*

📊 *Statistics:*
👥 Total Users: {stats['total_users']}
📦 Total Orders: {stats['total_orders']}
✅ Completed: {stats['completed_orders']}
⏳ Pending: {stats['pending_orders']}
💰 Revenue: ₹{stats['total_revenue']}

*Commands:*
/orders - View all orders
/orders_pending - View pending orders
/broadcast - Send message to all users
/export - Export data (CSV)
/clear - Clear pending orders
    """
    bot.reply_to(message, admin_text, parse_mode='Markdown')

@bot.message_handler(commands=['orders'])
def admin_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    orders = get_all_orders()
    
    if not orders:
        bot.reply_to(message, "📭 No orders found.")
        return
    
    text = "📋 *All Orders:*\n\n"
    for order in orders[:20]:
        order_id, user_id, product_id, duration, amount, status, key_gen, date = order
        status_emoji = "✅" if status == "completed" else "⏳"
        key_status = "🔑" if key_gen == '1' else "⏳"
        text += f"{status_emoji} `{order_id}` | User: {user_id}\n"
        text += f"   {product_id} ({duration}) | ₹{amount}\n"
        text += f"   {key_status} {date[:10]}\n\n"
    
    if len(orders) > 20:
        text += f"\n... and {len(orders) - 20} more orders"
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['orders_pending'])
def admin_pending_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT order_id, user_id, product_id, duration, amount, order_date 
                 FROM orders WHERE payment_status='pending' ORDER BY order_date ASC''')
    orders = c.fetchall()
    conn.close()
    
    if not orders:
        bot.reply_to(message, "✅ No pending orders!")
        return
    
    text = "⏳ *Pending Orders:*\n\n"
    for order in orders[:10]:
        order_id, user_id, product_id, duration, amount, date = order
        text += f"🕐 `{order_id}` | User: {user_id}\n"
        text += f"   {product_id} ({duration}) | ₹{amount}\n"
        text += f"   Date: {date[:10]}\n\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['broadcast'])
def broadcast_start(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    bot.reply_to(message, "📢 Send the message you want to broadcast to all users:")
    user_data[message.chat.id] = {'step': 'broadcast'}

@bot.message_handler(commands=['export'])
def export_data(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        import csv
        from io import StringIO
        
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM orders")
        data = c.fetchall()
        conn.close()
        
        if not data:
            bot.reply_to(message, "No data to export.")
            return
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Order ID', 'User ID', 'Product ID', 'Duration', 'Android ID', 'Amount', 'Status', 'Key Generated', 'Key Value', 'Order Date', 'Expiry Date'])
        writer.writerows(data)
        
        bot.send_document(message.chat.id, output.getvalue(), filename='orders_export.csv')
    except Exception as e:
        bot.reply_to(message, f"❌ Export failed: {str(e)}")

@bot.message_handler(commands=['clear'])
def clear_pending_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    bot.reply_to(message, "⚠️ Are you sure you want to clear all pending orders?\nType `CONFIRM` to proceed.", parse_mode='Markdown')
    user_data[message.chat.id] = {'step': 'clear_confirm'}

# ==================== USER DATA ====================
user_data = {}

# ==================== MESSAGE HANDLER ====================
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    # Handle broadcast
    if user_id in user_data and user_data[user_id].get('step') == 'broadcast':
        if message.from_user.id in ADMIN_IDS:
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()
            
            success = 0
            for user in users:
                try:
                    bot.send_message(user[0], f"📢 *Announcement*\n\n{text}", parse_mode='Markdown')
                    success += 1
                    time.sleep(0.1)
                except:
                    pass
            
            bot.reply_to(message, f"✅ Broadcast sent to {success} users.")
            del user_data[user_id]
        return
    
    # Handle clear confirmation
    if user_id in user_data and user_data[user_id].get('step') == 'clear_confirm':
        if message.from_user.id in ADMIN_IDS and text.upper() == 'CONFIRM':
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute("DELETE FROM orders WHERE payment_status='pending'")
            deleted = c.rowcount
            conn.commit()
            conn.close()
            bot.reply_to(message, f"✅ Cleared {deleted} pending orders.")
            del user_data[user_id]
        else:
            bot.reply_to(message, "❌ Clear cancelled.")
            del user_data[user_id]
        return
    
    # Handle purchase flow
    if user_id in user_data:
        step = user_data[user_id].get('step')
        
        if step == 'select_product':
            # Parse duration selection
            selected_duration = None
            if text.isdigit() and 1 <= int(text) <= len(PRODUCT_PRICES):
                durations = list(PRODUCT_PRICES.keys())
                selected_duration = durations[int(text) - 1]
            elif text in PRODUCT_PRICES:
                selected_duration = text
            
            if selected_duration:
                user_data[user_id]['duration'] = selected_duration
                user_data[user_id]['step'] = 'product_id'
                bot.reply_to(message, f"✅ Selected: {selected_duration}\n\nNow enter the *Product ID*:")
            else:
                bot.reply_to(message, "❌ Invalid selection. Please choose a number from 1-4.")
            
        elif step == 'product_id':
            user_data[user_id]['product_id'] = text
            user_data[user_id]['step'] = 'android_id'
            bot.reply_to(message, "📱 Enter *Android ID* (Type `skip` if not needed):", parse_mode='Markdown')
            
        elif step == 'android_id':
            android_id = None if text.lower() == 'skip' else text
            user_data[user_id]['android_id'] = android_id
            
            # Get order details
            product_id = user_data[user_id]['product_id']
            duration = user_data[user_id]['duration']
            amount = PRODUCT_PRICES[duration]
            
            # Generate order ID
            order_id = f"ORD{int(time.time())}{random.randint(10,99)}"
            
            # Save to database
            save_order(order_id, user_id, product_id, duration, android_id, amount)
            
            # Generate key
            key = generate_key()
            
            # Update order with key
            update_order_with_key(order_id, key)
            
            # Send payment instructions
            payment_text = f"""
💳 *Payment Required*

Order: `{order_id}`
Product: {product_id}
Duration: {duration}
Amount: ₹{amount}

📤 *Pay via UPI:*
UPI ID: `{UPI_ID}`
Reference: {order_id}

🏦 *Bank Transfer:*
{BANK_DETAILS}
Reference: {order_id}

📸 After payment, send screenshot or type: `paid`

🔑 *Your Key:* `{key}` (Will be activated after payment confirmation)
            """
            bot.reply_to(message, payment_text, parse_mode='Markdown')
            
            # Notify admin about new order
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(admin_id, f"🆕 New Order!\nOrder: {order_id}\nUser: {user_id}\nAmount: ₹{amount}")
                except:
                    pass
            
            del user_data[user_id]
            
        elif step == 'payment_confirmation':
            # Handle payment confirmation
            if text.lower() == 'paid':
                order_id = user_data[user_id].get('order_id')
                if order_id:
                    order = get_order_by_id(order_id)
                    if order and order[6] == 'pending':  # payment_status index 6
                        key = generate_key()
                        update_order_with_key(order_id, key)
                        
                        key_text = f"""
✅ *Payment Confirmed!* 🎉

🔑 *Your License Key:*
`{key}`

📦 *Product:* {order[2]} ({order[3]})
📅 *Valid until:* {order[8][:10]}

*How to use:*
1. Copy the key above
2. Open the app
3. Enter the key
4. Enjoy!

📋 Save this key safely.
                        """
                        bot.reply_to(message, key_text, parse_mode='Markdown')
                        
                        for admin_id in ADMIN_IDS:
                            try:
                                bot.send_message(admin_id, f"✅ Payment confirmed! Order: {order_id}")
                            except:
                                pass
                    else:
                        bot.reply_to(message, "❌ Order not found or already processed.")
                else:
                    bot.reply_to(message, "❌ No pending order found.")
                
                if user_id in user_data:
                    del user_data[user_id]
            else:
                bot.reply_to(message, "Type `paid` to confirm your payment.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❓ Unknown command. Use /help for available commands.")

@bot.message_handler(content_types=['photo'])
def handle_payment_screenshot(message):
    user_id = message.chat.id
    # Store order ID for confirmation
    orders = get_user_orders(user_id)
    if orders:
        latest_order = orders[0]
        user_data[user_id] = {'step': 'payment_confirmation', 'order_id': latest_order[0]}
    
    # Forward to admin
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, f"📸 Payment screenshot from user {user_id}")
            bot.forward_message(admin_id, user_id, message.message_id)
        except:
            pass
    
    bot.reply_to(message, "📸 Screenshot received! Type `paid` to confirm your payment.", parse_mode='Markdown')

# ==================== WEBHOOK ====================
@app.route('/', methods=['GET'])
def index():
    return "Bot is running!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ==================== MAIN ====================
if __name__ == '__main__':
    print("🤖 Initializing database...")
    init_database()
    print("✅ Database initialized!")
    
    print(f"🤖 Bot is running...")
    print(f"Bot: @{bot.get_me().username}")
    print(f"Admin IDs: {ADMIN_IDS}")
    
    # Set webhook on Railway
    port = int(os.environ.get('PORT', 5000))
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    
    if webhook_url:
        webhook_url = webhook_url.rstrip('/')
        bot.remove_webhook()
        bot.set_webhook(url=f'{webhook_url}/{BOT_TOKEN}')
        print(f"✅ Webhook set to: {webhook_url}/{BOT_TOKEN}")
    
    app.run(host='0.0.0.0', port=port)
