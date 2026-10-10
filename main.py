import os
import asyncio
import aiohttp
from aiohttp import web
import google.generativeai as genai
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv

# .env fayldan o'zgaruvchilarni yuklash
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

# Python 3.10+ va Telethon uchun maxsus event loop yaratish
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Gemini AI ni sozlash
genai.configure(api_key=AI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Telegram mijozlari
SESSION_STRING = os.getenv("SESSION_STRING")
if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)
else:
    client = TelegramClient('shaxsiy_sessiya', API_ID, API_HASH, loop=loop)

bot = AsyncTeleBot(BOT_TOKEN)

# Xabarlarni saqlash uchin lug'at (Memory)
message_cache = {}
deleted_messages = []
replied_users = set()

# ================= USERBOT QISMI =================

@client.on(events.NewMessage)
async def handler_new_message(event):
    # Xabar kelgan zahoti yuboruvchi ismini aniqlab keshlash
    try:
        sender = await event.get_sender()
        if sender:
            sender_name = getattr(sender, 'first_name', getattr(sender, 'title', "Noma'lum"))
        else:
            sender_name = "Noma'lum"
    except:
        sender_name = "Noma'lum"

    message_cache[event.message.id] = {
        'text': event.message.text,
        'sender_name': sender_name
    }
    
    # Shaxsiy xabar (PM) kelsa va uni yozgan shaxs bot bo'lmasa
    if event.is_private:
        sender = await event.get_sender()
        if sender and not sender.bot:
            me = await client.get_me()
            # O'zimizning xabarlarimizga va oldin AI javob berganlarga javob bermaymiz
            if sender.id != me.id and sender.id not in replied_users:
                user_text = event.text
                if user_text:
                    prompt = (
                        f"Sen mening shaxsiy AI yordamchimsan. Kimgadir Telegramda qisqa javob qaytarishing kerak.\n"
                        f"Foydalanuvchi xabari: '{user_text}'.\n"
                        f"Unga o'zbek tilida, muloyim tarzda: xo'jayinim hozir band ekanligini, "
                        f"xabarini o'qib albatta javob berishini ayt. O'zing qanday yordam bera olishingni ham taklif qil."
                    )
                    try:
                        response = model.generate_content(prompt)
                        await event.reply(response.text)
                        replied_users.add(sender.id)
                        print(f"[{getattr(sender, 'first_name', 'Foydalanuvchi')}] ga AI avtomatik javob yubordi.")
                    except Exception as e:
                        print(f"AI javob berishda xatolik yuz berdi: {e}")

@client.on(events.MessageDeleted)
async def handler_deleted_message(event):
    for msg_id in event.deleted_ids:
        if msg_id in message_cache:
            cached_data = message_cache[msg_id]
            sender_name = cached_data['sender_name']
            msg_text = cached_data['text']
            
            text = f"🚨 O'CHIRILGAN XABAR:\nKimdan: {sender_name}\nMatn: {msg_text or 'Rasm/Video'}"
            deleted_messages.append({'sender': sender_name, 'text': msg_text or 'Rasm/Video'})
            
            # Saved Messages'ga yuborish
            await client.send_message('me', text)
            print("O'chirilgan xabar saqlandi.")

# ================= BOT QISMI (AI) =================

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    await bot.reply_to(message, "Salom! Men sizning shaxsiy AI agentingizman. Menga savol bering yoki o'chirilgan xabarlar haqida so'rang.")

@bot.message_handler(func=lambda message: True)
async def handle_ai_request(message):
    user_text = message.text
    
    context = "Yaqinda o'chirilgan xabarlar tarixi:\n"
    if not deleted_messages:
        context += "Hozircha hech qanday o'chirilgan xabar yo'q.\n"
    else:
        for msg in deleted_messages[-10:]:
            context += f"- {msg['sender']} yozdi: {msg['text']}\n"
            
    prompt = f"Sen mening shaxsiy Telegram yordamchimsan. Quyidagi ma'lumotlarga asoslanib savolga javob ber.\n\n{context}\n\nMening savolim/buyrug'im: {user_text}"
    
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
    except Exception as e:
        ai_reply = f"AI bilan ulanishda xatolik yuz berdi: {e}"
        
    await bot.reply_to(message, ai_reply)


# ================= WEB SERVER QISMI (RENDER UCHUN) =================
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def keep_alive_ping():
    app_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL")
    if not app_url:
        print("Ping qilish uchun URL topilmadi. O'zingiz UptimeRobot ga ulab qo'yishingiz mumkin.")
        return
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(app_url) as response:
                    print(f"Serverga ping yuborildi - Status: {response.status}")
        except Exception as e:
            print(f"Ping yuborishda xatolik: {e}")
        await asyncio.sleep(10 * 60) # Har 10 daqiqada ping yuborish

# ================= ASOSIY FUNKSIYA =================
async def main():
    print("Userbot va AI Bot ishga tushmoqda...")
    await client.start()
    print("Userbot muvaffaqiyatli ishga tushdi!")
    
    await asyncio.gather(
        web_server(),
        keep_alive_ping(),
        client.run_until_disconnected(),
        bot.polling(non_stop=True)
    )

if __name__ == '__main__':
    # asyncio.run() o'rniga biz o'zimiz yaratgan loop dan foydalanamiz:
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Dastur to'xtatildi.")
