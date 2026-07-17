# ==========================================
# 🛠️ مكتبات النظام والبيئة والويب
# ==========================================
import os
import sys
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from github import Github, GithubException

# تحميل متغيرات البيئة من ملف .env (للتشغيل المحلي إن وجد)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# ⚙️ الإعدادات وجلب متغيرات البيئة
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")

try:
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
except ValueError:
    ADMIN_TELEGRAM_ID = 0

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TELEGRAM_BOT_TOKEN or not GITHUB_ACCESS_TOKEN:
    logger.critical("❌ خطأ: لم يتم العثور على المتغيرات الأساسية في البيئة!")
    sys.exit("خطأ في تشغيل البوت.")

# ==========================================
# 🔌 الاتصال بـ GitHub API
# ==========================================
github_client = None
github_user = None

try:
    github_client = Github(GITHUB_ACCESS_TOKEN)
    github_user = github_client.get_user()
    logger.info(f"✅ تم الاتصال بجاك هاب بنجاح: {github_user.login}")
except Exception as e:
    logger.error(f"❌ فشل الاتصال الأولي بـ GitHub API: {e}")

# ==========================================
# 💾 قاعدة البيانات وجلسات المستخدمين
# ==========================================
user_sessions = {}

def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "action": None,
            "current_repo": None,
            "delete_code": None,
            "repo_to_delete": None
        }
    return user_sessions[user_id]

def clear_session_action(user_id):
    session = get_session(user_id)
    session["action"] = None

# ==========================================
# ⌨️ لوحات المفاتيح (Keyboards)
# ==========================================
def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📂 استعراض المستودعات", callback_data="main_list_repos"),
            InlineKeyboardButton("➕ إنشاء مستودع جديد (عام)", callback_data="main_prompt_create")
        ],
        [
            InlineKeyboardButton("ℹ️ معلومات الحساب الشخصي", callback_data="main_account_info")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def repo_management_keyboard(repo_name):
    keyboard = [
        [
            InlineKeyboardButton("🌐 تفعيل ويب (GitHub Pages)", callback_data="repo_enable_pages"),
            InlineKeyboardButton("📝 إضافة / تعديل ملف", callback_data="repo_prompt_edit_file")
        ],
        [
            InlineKeyboardButton("📋 استعراض الملفات", callback_data="repo_list_files"),
            InlineKeyboardButton("🌿 الفروع (Branches)", callback_data="repo_list_branches")
        ],
        [
            InlineKeyboardButton("⚠️ المشاكل (Issues)", callback_data="repo_list_issues"),
            InlineKeyboardButton("👥 المساهمين", callback_data="repo_list_collabs")
        ],
        [
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="repo_settings"),
            InlineKeyboardButton("🗑️ حذف المستودع", callback_data="repo_prompt_delete")
        ],
        [
            InlineKeyboardButton("🔙 العودة لقائمة المستودعات", callback_data="main_list_repos")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_main_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(keyboard)

def back_to_repo_keyboard(repo_name):
    keyboard = [[InlineKeyboardButton("🔙 العودة للمستودع", callback_data=f"repo_manage_{repo_name}")]]
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# 🛠️ معالجات البوت (Handlers)
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("⛔ عذراً، هذا البوت خاص بمسؤول النظام فقط.")
        return
    
    clear_session_action(user_id)
    await update.message.reply_text(
        "مرحبا بك في لوحة تحكم Github المتطورة 🚀",
        reply_markup=main_menu_keyboard()
    )

async def list_repositories_action(query, context: ContextTypes.DEFAULT_TYPE):
    try:
        await query.edit_message_text("🔄 جاري سحب قائمة مستودعاتك...")
        repos = github_user.get_repos()
        keyboard = []
        for repo in repos:
            keyboard.append([InlineKeyboardButton(f"📁 {repo.name}", callback_data=f"repo_manage_{repo.name}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")])
        await query.edit_message_text("📂 اختر مستودعاً لإدارته:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب المستودعات: `{str(e)}`", reply_markup=back_to_main_keyboard())

async def show_repo_control_panel(query, context: ContextTypes.DEFAULT_TYPE, repo_name: str):
    user_id = query.from_user.id
    session = get_session(user_id)
    session["current_repo"] = repo_name
    try:
        repo = github_user.get_repo(repo_name)
        desc = repo.description if repo.description else "لا يوجد وصف حالياً."
        info = f"🛠️ **لوحة التحكم بالمستودع: `{repo_name}`**\n\n📝 الوصف: {desc}\n🔗 [رابط المستودع]({repo.html_url})"
        await query.edit_message_text(info, reply_markup=repo_management_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل الوصول للمستودع: `{str(e)}`", reply_markup=back_to_main_keyboard())

async def enable_github_pages_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    custom_url = f"https://{github_user.login}.github.io/{repo_name}/"
    try:
        repo = github_user.get_repo(repo_name)
        repo.create_pages(source={"branch": "main", "path": "/"})
        await query.edit_message_text(f"🚀 **تم تفعيل الاستضافة بنجاح!**\n\n🔗 {custom_url}", reply_markup=back_to_repo_keyboard(repo_name))
    except Exception as e:
        await query.edit_message_text(f"🔗 رابط موقعك المتوقع هو:\n{custom_url}", reply_markup=back_to_repo_keyboard(repo_name))

async def list_repo_files_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    try:
        repo = github_user.get_repo(repo_name)
        contents = repo.get_contents("")
        files_text = f"📋 **الملفات الموجودة في `{repo_name}`:**\n\n"
        for content_file in contents:
            icon = "📄" if content_file.type == "file" else "📁"
            files_text += f"{icon} `{content_file.name}`\n"
        await query.edit_message_text(files_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب الملفات: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def list_repo_branches_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    try:
        repo = github_user.get_repo(repo_name)
        branches = repo.get_branches()
        branches_text = f"🌿 **الفروع في `{repo_name}`:**\n\n"
        for b in branches:
            branches_text += f"🔹 `{b.name}`\n"
        await query.edit_message_text(branches_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب الفروع: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def list_repo_issues_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    try:
        repo = github_user.get_repo(repo_name)
        issues = repo.get_issues(state='open')
        issues_text = f"🐛 **المشاكل المفتوحة في `{repo_name}`:**\n\n"
        count = 0
        for i in issues:
            count += 1
            issues_text += f"{count}. ⚠️ `#{i.number}` - {i.title}\n"
        if count == 0:
            issues_text = "🎉 لا توجد مشاكل مفتوحة!"
        await query.edit_message_text(issues_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب المشاكل: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def list_repo_collaborators_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    try:
        repo = github_user.get_repo(repo_name)
        collaborators = repo.get_collaborators()
        text = f"👥 **المساهمون في `{repo_name}`:**\n\n"
        for collab in collaborators:
            text += f"👤 `{collab.login}`\n"
        await query.edit_message_text(text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب المساهمين: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def show_repo_settings_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    try:
        repo = github_user.get_repo(repo_name)
        settings_text = (
            f"⚙️ **إعدادات مستودع `{repo_name}`:**\n\n"
            f"🔒 حالة الخصوصية: {'خاص 🔒' if repo.private else 'عام 🌐'}\n"
            f"🌿 الفرع الرئيسي: `{repo.default_branch}`\n"
        )
        await query.edit_message_text(settings_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب الإعدادات: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def global_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_TELEGRAM_ID:
        await query.answer("⛔ غير مصرح لك.", show_alert=True)
        return
    await query.answer()
    data = query.data
    session = get_session(user_id)

    if data == "main_list_repos":
        await list_repositories_action(query, context)
    elif data == "main_prompt_create":
        session["action"] = "awaiting_repo_name_create"
        await query.edit_message_text("✍️ أرسل اسم المستودع الجديد بالإنجليزية:")
    elif data == "main_account_info":
        await query.edit_message_text(f"👤 حسابك: `{github_user.login}`", reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
    elif data == "back_to_main":
        await query.edit_message_text("لوحة التحكم الرئيسية", reply_markup=main_menu_keyboard())
    elif data.startswith("repo_manage_"):
        await show_repo_control_panel(query, context, data.replace("repo_manage_", ""))
    elif data == "repo_enable_pages":
        await enable_github_pages_action(query, context)
    elif data == "repo_list_files":
        await list_repo_files_action(query, context)
    elif data == "repo_list_branches":
        await list_repo_branches_action(query, context)
    elif data == "repo_list_issues":
        await list_repo_issues_action(query, context)
    elif data == "repo_list_collabs":
        await list_repo_collaborators_action(query, context)
    elif data == "repo_settings":
        await show_repo_settings_action(query, context)
    elif data == "repo_prompt_edit_file":
        session["action"] = "awaiting_file_content_only"
        await query.edit_message_text("📝 أرسل الملف: السطر الأول الاسم، والسطور التالية المحتوى.")
    elif data == "repo_prompt_delete":
        repo_name = session.get("current_repo")
        try:
            repo = github_user.get_repo(repo_name)
            repo.delete()
            await query.edit_message_text(f"✅ تم حذف المستودع `{repo_name}`!", reply_markup=back_to_main_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ فشل الحذف: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_TELEGRAM_ID: return
    text = update.message.text.strip()
    session = get_session(user_id)
    action = session.get("action")

    if action == "awaiting_repo_name_create":
        clear_session_action(user_id)
        try:
            repo = github_user.create_repo(text, private=False, auto_init=True)
            await update.message.reply_text(f"✅ تم إنشاء `{repo.name}`!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ لوحة التحكم", callback_data=f"repo_manage_{repo.name}")]]))
        except Exception as e:
            await update.message.reply_text(f"❌ فشل الإنشاء: `{str(e)}`")

    elif action == "awaiting_file_content_only":
        repo_name = session.get("current_repo")
        lines = text.split("\n", 1)
        if len(lines) < 2:
            await update.message.reply_text("⚠️ صيغة خاطئة!")
            return
        file_name, file_content = lines[0].strip(), lines[1].strip()
        clear_session_action(user_id)
        try:
            repo = github_user.get_repo(repo_name)
            try:
                contents = repo.get_contents(file_name)
                repo.update_file(file_name, "Update via bot", file_content, contents.sha)
            except Exception:
                repo.create_file(file_name, "Create via bot", file_content)
            await update.message.reply_text("✅ تم الرفع بنجاح!", reply_markup=back_to_repo_keyboard(repo_name))
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: `{str(e)}`")

# ==========================================
# 🌐 خادم الويب المصغر (Flask Server)
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    # صفحة بسيطة تؤكد للاستضافة أن المشروع يعمل وصحي تماماً
    return "🚀 Telegram Bot is running and healthy!", 200

def run_flask():
    # قراءة منفذ الاستضافة بشكل ديناميكي (افتراضياً 8080)
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ==========================================
# 🚀 نقطة تشغيل البوت الأساسية (Main)
# ==========================================
def main():
    # 1. تشغيل خادم Flask في خيط معالجة مستقل (Background Thread)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("🌐 تم بدء خادم Flask في الخلفية لمتطلبات الاستضافة.")

    # 2. تشغيل البوت الأساسي
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(global_button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))

    print("=" * 60)
    print("🚀 البوت يعمل بالتوازي مع Flask بنجاح!")
    print("=" * 60)
    
    application.run_polling()

if __name__ == '__main__':
    main()
