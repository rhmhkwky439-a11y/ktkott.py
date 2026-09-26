import time
import sqlite3
import telebot
from telebot import types

# --- الإعدادات الأساسية ---
TOKEN = "8718984244:AAGRBQY4q46UxtaVK8jWZAemGk10DyrpxHo"

# قائمة المالكين / المشرفين المعتمدين للبوت
ADMIN_IDS = [1722920559, 8348562918]

# القنوات أو المجموعات الإجبارية المطلوبة
REQUIRED_CHANNELS = ["@store_north1", "@ssrrrar"]

bot = telebot.TeleBot(TOKEN)

# قواعد البيانات المؤقتة للأوامر والعروض
offers_db = []
reward_links = {}
admin_state = {}


# --- إعداد قاعدة البيانات الدائمة (SQLite) ---
def init_db():
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            transfers_count INTEGER DEFAULT 0,
            bought_count INTEGER DEFAULT 0,
            last_gift_time REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invited_users (
            referrer_id INTEGER,
            invited_id INTEGER,
            PRIMARY KEY (referrer_id, invited_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()


def get_user_data(user_id: int):
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT points, referred_by, transfers_count, bought_count, last_gift_time, is_banned, username, first_name FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO users (user_id, points, referred_by, transfers_count, bought_count, last_gift_time, is_banned)
            VALUES (?, 0, NULL, 0, 0, 0.0, 0)
        """, (user_id,))
        conn.commit()
        user_data = {
            "points": 0,
            "referred_by": None,
            "invited_users": set(),
            "transfers_count": 0,
            "bought_count": 0,
            "last_gift_time": 0.0,
            "is_banned": 0,
            "username": None,
            "first_name": None
        }
    else:
        cursor.execute("SELECT invited_id FROM invited_users WHERE referrer_id = ?", (user_id,))
        invited = {r[0] for r in cursor.fetchall()}
        user_data = {
            "points": row[0],
            "referred_by": row[1],
            "transfers_count": row[2],
            "bought_count": row[3],
            "last_gift_time": row[4],
            "is_banned": row[5],
            "username": row[6],
            "first_name": row[7],
            "invited_users": invited
        }
    conn.close()
    return user_data


def update_user_data(user_id: int, points=None, referred_by=None, transfers_count=None, bought_count=None, last_gift_time=None, is_banned=None, username=None, first_name=None):
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, points, is_banned) VALUES (?, 0, 0)", (user_id,))

    if points is not None:
        cursor.execute("UPDATE users SET points = ? WHERE user_id = ?", (points, user_id))
    if referred_by is not None:
        cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referred_by, user_id))
    if transfers_count is not None:
        cursor.execute("UPDATE users SET transfers_count = ? WHERE user_id = ?", (transfers_count, user_id))
    if bought_count is not None:
        cursor.execute("UPDATE users SET bought_count = ? WHERE user_id = ?", (bought_count, user_id))
    if last_gift_time is not None:
        cursor.execute("UPDATE users SET last_gift_time = ? WHERE user_id = ?", (last_gift_time, user_id))
    if is_banned is not None:
        cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (is_banned, user_id))
    if username is not None:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    if first_name is not None:
        cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))

    conn.commit()
    conn.close()


def find_user_id_by_input(user_input: str):
    user_input = user_input.strip()
    if user_input.isdigit():
        return int(user_input)
    
    clean_username = user_input.replace('@', '')
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (clean_username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None


def add_invited_user(referrer_id: int, invited_id: int):
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO invited_users (referrer_id, invited_id) VALUES (?, ?)", (referrer_id, invited_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success


# --- دالة التحقق من الاشتراك الإجباري ---
def check_subscription(user_id: int):
    if user_id in ADMIN_IDS:
        return True

    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            print(f"Error checking subscription for {channel}: {e}")
            return False

    return True


def subscription_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for channel in REQUIRED_CHANNELS:
        clean_name = channel.replace('@', '')
        markup.add(
            types.InlineKeyboardButton(f"🔔 اشترك في {channel}", url=f"https://t.me/{clean_name}")
        )
    markup.add(
        types.InlineKeyboardButton("✨ تم الاشتراك في الكل، تحقق ✅", callback_data="check_sub")
    )
    return markup


def inline_main_keyboard(user_id: int):
    markup = types.InlineKeyboardMarkup(row_width=2)
    user_data = get_user_data(user_id)

    btn_offers = types.InlineKeyboardButton(
        "✨العروض التي يقدمها البوت✨", callback_data="bot_offers"
    )
    btn_balance = types.InlineKeyboardButton(
        f"رصيد حسابك : {user_data['points']} نقطه", callback_data="show_balance"
    )
    btn_collect = types.InlineKeyboardButton(
        "تجميع رصيد", callback_data="collect_points"
    )
    btn_info = types.InlineKeyboardButton(
        "معلومات حسابك", callback_data="account_info"
    )
    btn_transfer = types.InlineKeyboardButton(
        "تحويل اموال", callback_data="transfer_points"
    )
    btn_gift = types.InlineKeyboardButton(
        "🎁 الهدية اليومية", callback_data="daily_gift"
    )

    markup.add(btn_offers)
    markup.add(btn_collect, btn_balance)
    markup.add(btn_transfer, btn_info)
    markup.add(btn_gift)

    # زر أوامر المالك يظهر للمالكين فقط في القائمة الرئيسية
    if user_id in ADMIN_IDS:
        btn_admin_panel = types.InlineKeyboardButton(
            "🛡️ أوامر المالك", callback_data="admin_panel"
        )
        markup.add(btn_admin_panel)

    return markup


def back_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("• رجوع •", callback_data="main_menu")
    )
    return markup


def main_text(first_name: str):
    return (
        f"اهلا وسهلا بك يا {first_name} في بوت تعويضات الستارك Sr 🎁✨\n\n"
        "البوت الافضل والانسب اليك في مجتمع روبلوكس من حيث الثقة وسرعة التسليم وتوفر العروض اليومية ✔️\n\n"
        "تواصل هنا لاستلام طلبك: @yo_planet 👤\n"
        "قناه البوت : @store_north1🧸"
    )


@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    # تحديث بيانات المستخدم وتخزين اسمه ويوزره
    update_user_data(user_id, username=username, first_name=first_name)
    user_data = get_user_data(user_id)

    # التحقق من الحظر
    if user_data.get("is_banned", 0) == 1 and user_id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ عذراً، لقد تم حظرك من استخدام البوت.")
        return

    # إشعار المالك عند دخول شخص جديد (إذا لم يكن هو نفسه المالك)
    if user_id not in ADMIN_IDS:
        username_str = f"@{username}" if username else "بدون معرف"
        new_user_notif = (
            f"👤 دخول عضو جديد إلى البوت!\n\n"
            f"📛 الاسم: {first_name}\n"
            f"🆔 الأيدي: {user_id}\n"
            f"🔗 المعرف: {username_str}"
        )
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, new_user_notif)
            except Exception:
                pass

    if not check_subscription(user_id):
        channels_text = " و ".join(REQUIRED_CHANNELS)
        bot.send_message(
            message.chat.id,
            "❌ عذراً، يجب عليك الاشتراك في القنوات التالية أولاً لتتمكن من استخدام البوت:\n\n"
            f"يرجى الاشتراك في: {channels_text}\n\n"
            "ثم اضغط على زر (تم الاشتراك في الكل، تحقق ✅)",
            reply_markup=subscription_markup()
        )
        return

    try:
        bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=types.MenuButtonCommands("commands")
        )
        bot.set_my_commands([
            types.BotCommand("start", "تشغيل البوت وإظهار القائمة الرئيسية 🚀")
        ])
    except Exception:
        pass

    text_args = message.text.split()
    if len(text_args) > 1:
        param = text_args[1]

        if param.startswith("reward_"):
            code = param
            if code in reward_links:
                reward_data = reward_links[code]
                if user_id in reward_data["claimed_users"]:
                    bot.send_message(message.chat.id, "❌ لقد قمت باستخدام هذا الرابط مسبقاً ولا يمكنك استخدامه مرة أخرى.")
                else:
                    points_amount = reward_data["points"]
                    new_points = user_data["points"] + points_amount
                    update_user_data(user_id, points=new_points)
                    reward_data["claimed_users"].add(user_id)
                    bot.send_message(message.chat.id, f"🎉 مبروك! تم إضافة {points_amount} نقطة إلى رصيدك بنجاح عبر الرابط الخاص.")
            else:
                bot.send_message(message.chat.id, "❌ هذا الرابط غير صالح أو انتهت صلاحيته.")
        else:
            try:
                referrer_id = int(param)
                if referrer_id != user_id and user_data["referred_by"] is None:
                    ref_check = get_user_data(referrer_id)
                    if ref_check:
                        update_user_data(user_id, referred_by=referrer_id)

                        if add_invited_user(referrer_id, user_id):
                            new_ref_points = ref_check["points"] + 1
                            update_user_data(referrer_id, points=new_ref_points)
                            try:
                                bot.send_message(
                                    referrer_id,
                                    f"🎉 اشعار تجميع رصيد:\nدخل شخص جديد ({first_name}) عن طريق رابطك!\nتم إضافة 1 نقطة لرصيدك."
                                )
                            except Exception:
                                pass
            except ValueError:
                pass

    bot.send_message(
        message.chat.id,
        main_text(first_name),
        reply_markup=inline_main_keyboard(user_id)
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global offers_db
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    first_name = call.from_user.first_name
    username = call.from_user.username

    user_data = get_user_data(user_id)
    if user_data.get("is_banned", 0) == 1 and user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, text="❌ أنت محظور من استخدام البوت.", show_alert=True)
        return

    if call.data == "check_sub":
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, text="✅ شكراً لاشتراكك في القنوات! يمكنك استخدام البوت الآن.", show_alert=True)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=main_text(first_name),
                reply_markup=inline_main_keyboard(user_id),
            )
        else:
            bot.answer_callback_query(call.id, text="❌ أنت لم تقم بالاشتراك في جميع القنوات المطلوبة بعد!", show_alert=True)
        return

    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, text="❌ يجب عليك الاشتراك في القنوات أولاً لاستخدام البوت!", show_alert=True)
        return

    if call.data == "main_menu":
        if user_id in admin_state:
            del admin_state[user_id]
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=main_text(first_name),
            reply_markup=inline_main_keyboard(user_id),
        )

    # --- لوحة أوامر المالك ---
    elif call.data == "admin_panel" and user_id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points"),
            types.InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_sub_points")
        )
        markup.add(
            types.InlineKeyboardButton("🚫 حظر شخص", callback_data="admin_ban_user"),
            types.InlineKeyboardButton("✅ فك حظر شخص", callback_data="admin_unban_user")
        )
        markup.add(
            types.InlineKeyboardButton("🔗 روابط النقاط", callback_data="admin_reward_links"),
            types.InlineKeyboardButton("📢 إذاعة للكل", callback_data="admin_broadcast")
        )
        markup.add(
            types.InlineKeyboardButton("➕ إضافة عرض", callback_data="admin_add_offer"),
            types.InlineKeyboardButton("❌ مسح عرض", callback_data="admin_delete_offer")
        )
        markup.add(
            types.InlineKeyboardButton("• رجوع •", callback_data="main_menu")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="🛡️ **مرحباً بك في لوحة أوامر المالك:**\nاختر العملية التي تريد تنفيذها:",
            reply_markup=markup
        )

    elif call.data == "admin_add_points" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "admin_add_pts"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(chat_id, "➕ أرسل الآن (أيدي المستخدم أو يوزره) متبوعاً بعدد النقاط.\nمثال: `123456789 50` أو `@username 50`", reply_markup=markup)

    elif call.data == "admin_sub_points" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "admin_sub_pts"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(chat_id, "➖ أرسل الآن (أيدي المستخدم أو يوزره) متبوعاً بعدد النقاط المراد خصمها.\nمثال: `123456789 20` أو `@username 20`", reply_markup=markup)

    elif call.data == "admin_ban_user" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "admin_ban"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(chat_id, "🚫 أرسل الآن أيدي المستخدم أو يوزره لحظره من البوت:", reply_markup=markup)

    elif call.data == "admin_unban_user" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "admin_unban"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(chat_id, "✅ أرسل الآن أيدي المستخدم أو يوزره لفك الحظر عنه:", reply_markup=markup)

    elif call.data == "cancel_admin_action" and user_id in ADMIN_IDS:
        if user_id in admin_state:
            del admin_state[user_id]
        bot.answer_callback_query(call.id, text="✅ تم الإلغاء.", show_alert=True)
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="تم الإلغاء بنجاح.", reply_markup=back_keyboard())

    elif call.data == "bot_offers":
        markup = types.InlineKeyboardMarkup(row_width=3)

        if user_id in ADMIN_IDS:
            markup.add(
                types.InlineKeyboardButton(
                    "🛡️ لوحة المالك", callback_data="admin_panel"
                )
            )

        markup.add(
            types.InlineKeyboardButton("التوفر 🟢", callback_data="none"),
            types.InlineKeyboardButton("الاسم ℹ️", callback_data="none"),
            types.InlineKeyboardButton("السعر 💵", callback_data="none"),
        )

        for offer in offers_db:
            status_icon = "✅" if offer["available"] else "🚫"
            btn_status = types.InlineKeyboardButton(
                status_icon, callback_data=f"view_offer_{offer['id']}"
            )
            btn_name = types.InlineKeyboardButton(
                offer["name"], callback_data=f"view_offer_{offer['id']}"
            )
            btn_price = types.InlineKeyboardButton(
                f"{offer['price']} نقطه",
                callback_data=f"view_offer_{offer['id']}",
            )
            markup.add(btn_status, btn_name, btn_price)

        markup.add(
            types.InlineKeyboardButton("• رجوع •", callback_data="main_menu")
        )

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✨العروض التي يقدمها البوت✨",
            reply_markup=markup,
        )

    elif call.data.startswith("view_offer_"):
        offer_id = int(call.data.split("_")[2])
        offer = next((o for o in offers_db if o["id"] == offer_id), None)
        if offer:
            status_text = "1 (متوفر)" if offer["available"] else "🚫 غير متوفر"
            msg = (
                f"🎁 تفاصيل السلعة:\n\n"
                f"📌 اسم السلعة: {offer['name']}\n"
                f"📝 وصف السلعة: {offer['desc']}\n\n"
                f"💵 السعر الحالي: {offer['price']} نقطه\n"
                f"✅ حالة التوفر: {status_text}\n\n"
                "❓ - هل أنت متأكد من رغبتك في الشراء؟"
            )
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton(
                    "نعم ، 🔥", callback_data=f"buy_{offer['id']}"
                ),
                types.InlineKeyboardButton("لا 🚫", callback_data="bot_offers"),
            )
            markup.add(
                types.InlineKeyboardButton("• رجوع •", callback_data="bot_offers")
            )
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=msg,
                reply_markup=markup,
            )

    elif call.data.startswith("buy_"):
        offer_id = int(call.data.split("_")[1])
        offer = next((o for o in offers_db if o["id"] == offer_id), None)
        if offer:
            if not offer["available"]:
                bot.answer_callback_query(
                    call.id,
                    text="❌ - المحتوى نفذ انتظار الى ان يتم اضافته.",
                    show_alert=True,
                )
            elif user_data["points"] < offer["price"]:
                bot.answer_callback_query(
                    call.id,
                    text="❌ ليس لديك نقاط كافية لشراء هذه السلعة.",
                    show_alert=True,
                )
            else:
                new_points = user_data["points"] - offer["price"]
                new_bought = user_data["bought_count"] + 1
                update_user_data(user_id, points=new_points, bought_count=new_bought)
                
                bot.answer_callback_query(
                    call.id,
                    text="✅ تم الشراء بنجاح! تواصل هنا لاستلام طلبك @yo_planet",
                    show_alert=True,
                )

                # رسالة للمشتري ليذهب للمالك
                user_notif = (
                    f"🎉 تم الشراء بنجاح!\n\n"
                    f"📦 السلعة: {offer['name']}\n"
                    f"💰 السعر: {offer['price']} نقطة\n\n"
                    f"👉 لاستلام طلبك، تواصل فوراً مع المالك هنا: @yo_planet"
                )
                try:
                    bot.send_message(user_id, user_notif)
                except Exception:
                    pass

                # إشعار فوري لكل المالكين مع تفاصيل المشتري
                username_str = f"@{username}" if username else "بدون معرف"
                admin_notif = (
                    f"🚨 تم شراء سلعة جديدة!\n\n"
                    f"👤 اسم العميل: {first_name}\n"
                    f"🆔 أيدي العميل: {user_id}\n"
                    f"🔗 معرف العميل: {username_str}\n"
                    f"📦 السلعة: {offer['name']}\n"
                    f"💵 السعر: {offer['price']} نقطة"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(admin_id, admin_notif)
                    except Exception:
                        pass

    elif call.data == "collect_points":
        bot_username = bot.get_me().username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        msg = (
            "🔗 انسخ الرابط ثم قم بمشاركته مع اصدقائك 📥.\n\n"
            "• كل شخص يقوم بالدخول ستحصل على 1 نقطه\n\n"
            f"~ رابط الدعوة : {ref_link}\n\n"
            f"• مشاركتك للرابط : {len(user_data['invited_users'])}\n"
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=msg,
            reply_markup=back_keyboard(),
        )

    elif call.data == "show_balance":
        bot.answer_callback_query(
            call.id,
            text=f"💰 رصيدك الحالي هو: {user_data['points']} نقطه",
            show_alert=True,
        )

    elif call.data == "account_info":
        info = (
            f"🌐 مرحباً بك في قسم معلومات حسابك ببوت المتجر!\n\n"
            f"رصيد حسابك الحالي: {user_data['points']} نقطه\n\n"
            "إحصائيات حسابك:\n"
            f"- 🔄 عمليات التحويل: {user_data['transfers_count']}\n"
            f"- 🎁 الهدايا اليومية: 1\n"
            f"- 🛒 السلع التي اشتريتها: {user_data['bought_count']}\n"
            f"- 📦 مشاركاتك لرابط الدعوة: {len(user_data['invited_users'])}\n"
            f"- 💰 الرصيد الذي استخدمته: 0"
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=info,
            reply_markup=back_keyboard(),
        )

    elif call.data == "transfer_points":
        msg = (
            "🔄 يمكنك تحويل الاموال بكل سهولة! فقط قم بإرسال عدد الرصيد الذي تود تحويله وسنقوم بانشاء رابط خاص لتتمكن من إرساله للشخص المرغوب. 📩\n\n"
            f" لديك : {user_data['points']} نقطه\n"
            " رسوم التحويل: 1 نقطه"
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=msg,
            reply_markup=back_keyboard(),
        )

    elif call.data == "daily_gift":
        current_time = time.time()
        cooldown = 86400
        last_gift = user_data.get("last_gift_time", 0.0)

        if current_time - last_gift < cooldown:
            remaining = int(cooldown - (current_time - last_gift))
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            bot.answer_callback_query(
                call.id,
                text=f"❌ لقد استلمت هدفتك اليومية مسبقاً!\n⏳ يرجى الانتظار: {hours} ساعة و {minutes} دقيقة.",
                show_alert=True,
            )
        else:
            new_points = user_data["points"] + 1
            update_user_data(user_id, points=new_points, last_gift_time=current_time)
            bot.answer_callback_query(
                call.id,
                text="🎁 لقد حصلت على 1 نقطه هدية يومية بنجاح!",
                show_alert=True,
            )
            bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=inline_main_keyboard(user_id),
            )

    elif call.data == "admin_reward_links" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "get_reward_points"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(
            chat_id,
            "🔗 [إنشاء رابط نقاط جديد]\nأرسل الآن عدد النقاط التي سيحصل عليها من يضغط على الرابط (أرسل رقماً صحيحاً):",
            reply_markup=markup
        )

    elif call.data == "admin_add_offer" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "get_name"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(
            chat_id,
            "➕ [لوحة المالك]\nأرسل الآن اسم السلعة الجديدة:",
            reply_markup=markup
        )

    elif call.data == "admin_delete_offer" and user_id in ADMIN_IDS:
        if not offers_db:
            bot.answer_callback_query(call.id, text="❌ لا توجد عروض لحذفها.", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for offer in offers_db:
            markup.add(types.InlineKeyboardButton(
                f"حذف: {offer['name']} ({offer['price']} نقطة)",
                callback_data=f"del_offer_{offer['id']}"
            ))
        markup.add(types.InlineKeyboardButton("• رجوع •", callback_data="bot_offers"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="🗑️ اختر العرض الذي تريد مسحه:",
            reply_markup=markup
        )

    elif call.data.startswith("del_offer_") and user_id in ADMIN_IDS:
        offer_id = int(call.data.split("_")[2])
        offers_db = [o for o in offers_db if o["id"] != offer_id]
        bot.answer_callback_query(call.id, text="✅ تم مسح العرض بنجاح.", show_alert=True)
        call.data = "bot_offers"
        callback_query(call)

    elif call.data == "admin_broadcast" and user_id in ADMIN_IDS:
        admin_state[user_id] = {"step": "broadcast_message"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_admin_action"))
        bot.send_message(
            chat_id,
            "📢 **أكتب رسالتك لجميع الأعضاء الآن:**\n(يمكنك إرسال نص، صورة، أو أي محتوى وسيقوم البوت بنشره للكل)\n\nأو اضغط على زر الإلغاء أدناه:",
            reply_markup=markup
        )


@bot.message_handler(
    content_types=['text', 'photo', 'video', 'document', 'audio', 'animation'],
    func=lambda message: message.from_user.id in ADMIN_IDS
    and message.from_user.id in admin_state
)
def admin_inputs_process(message):
    global offers_db, reward_links
    user_id = message.from_user.id
    state = admin_state[user_id]
    step = state.get("step")

    if step == "admin_add_pts" or step == "admin_sub_pts":
        try:
            args = message.text.split()
            target_input = args[0]
            points_val = int(args[1])
            
            target_id = find_user_id_by_input(target_input)
            if not target_id:
                bot.reply_to(message, "❌ لم يتم العثور على المستخدم بهذا الأيدي أو اليوزر.")
                return

            target_data = get_user_data(target_id)
            if step == "admin_add_pts":
                new_pts = target_data["points"] + points_val
                update_user_data(target_id, points=new_pts)
                bot.reply_to(message, f"✅ تم إضافة {points_val} نقطة بنجاح للمستخدم `{target_id}`.\nرصيده الجديد: {new_pts}")
                try:
                    bot.send_message(target_id, f"🎁 تم إضافة {points_val} نقطة إلى رصيدك بواسطة الإدارة!")
                except Exception:
                    pass
            else:
                new_pts = max(0, target_data["points"] - points_val)
                update_user_data(target_id, points=new_pts)
                bot.reply_to(message, f"✅ تم خصم {points_val} نقطة بنجاح من المستخدم `{target_id}`.\nرصيده الجديد: {new_pts}")
                try:
                    bot.send_message(target_id, f"⚠️ تم خصم {points_val} نقطة من رصيدك بواسطة الإدارة.")
                except Exception:
                    pass

            del admin_state[user_id]
        except (IndexError, ValueError):
            bot.reply_to(message, "❌ صيغة خاطئة. اكتب هكذا:\n`ID_or_Username Points`\nمثال: `12345678 50` أو `@user 50`")
        return

    elif step == "admin_ban":
        target_id = find_user_id_by_input(message.text)
        if not target_id:
            bot.reply_to(message, "❌ لم يتم العثور على المستخدم.")
            return
        update_user_data(target_id, is_banned=1)
        del admin_state[user_id]
        bot.reply_to(message, f"🚫 تم حظر المستخدم `{target_id}` بنجاح من البوت.")
        return

    elif step == "admin_unban":
        target_id = find_user_id_by_input(message.text)
        if not target_id:
            bot.reply_to(message, "❌ لم يتم العثور على المستخدم.")
            return
        update_user_data(target_id, is_banned=0)
        del admin_state[user_id]
        bot.reply_to(message, f"✅ تم فك الحظر عن المستخدم `{target_id}` بنجاح.")
        return

    elif step == "broadcast_message":
        conn = sqlite3.connect("bot_database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        all_users = [row[0] for row in cursor.fetchall()]
        conn.close()

        del admin_state[user_id]
        
        sent_count = 0
        failed_count = 0

        status_msg = bot.reply_to(message, "⏳ جاري إرسال الإذاعة لجميع الأعضاء...")

        for uid in all_users:
            try:
                bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
                sent_count += 1
            except Exception:
                failed_count += 1

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=f"✅ **تمت الإذاعة بنجاح!**\n\n📤 تم الإرسال إلى: {sent_count} عضو\n❌ فشل الإرسال إلى: {failed_count} عضو (حظروا البوت)"
        )
        return

    elif step == "get_reward_points":
        try:
            points = int(message.text)
            if points <= 0:
                raise ValueError()

            import random
            code = f"reward_{random.randint(100000, 999999)}"
            reward_links[code] = {
                "points": points,
                "claimed_users": set()
            }

            bot_username = bot.get_me().username
            link = f"https://t.me/{bot_username}?start={code}"
            del admin_state[user_id]

            bot.reply_to(
                message,
                f"✅ تم إنشاء رابط النقاط بنجاح!\n\n"
                f"💰 النقاط المحددة: {points}\n"
                f"🔗 الرابط:\n{link}"
            )
        except ValueError:
            bot.reply_to(message, "❌ يرجى إرسال رقم صحيح أكبر من صفر.")

    elif step == "get_name":
        state["name"] = message.text
        state["step"] = "get_price"
        bot.reply_to(message, "💵 ممتاز. الآن أرسل سعر السلعة (برقم صحيح):")

    elif step == "get_price":
        try:
            price = int(message.text)
            state["price"] = price
            state["step"] = "get_status"
            bot.reply_to(
                message,
                "🟢 هل السلعة متوفرة؟ أرسل متوفر أو غير متوفر:",
            )
        except ValueError:
            bot.reply_to(message, "❌ يرجى إرسال السعر كأرقام صحيحة فقط.")

    elif step == "get_status":
        status_text = message.text.strip()
        is_available = True if "متوفر" in status_text else False

        new_offer = {
            "id": (offers_db[-1]["id"] + 1) if offers_db else 1,
            "name": state["name"],
            "price": state["price"],
            "available": is_available,
            "desc": "لا يوجد",
        }
        offers_db.append(new_offer)
        del admin_state[user_id]

        bot.reply_to(
            message,
            "✅ تم إضافة العرض بنجاح!",
            reply_markup=inline_main_keyboard(user_id),
        )


print("البوت يعمل بقاعدة بيانات دائمة ومؤمن بالكامل للمالكين...")
bot.infinity_polling()
