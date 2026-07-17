# ==========================================
# 🛠️ مكتبات النظام الأساسية والبيئة
# ==========================================
import os
import sys
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from github import Github, GithubException

# تحميل متغيرات البيئة من ملف .env (للتشغيل المحلي إن وجد)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # في الاستضافة سيتم قراءة المتغيرات مباشرة من البيئة دون الحاجة لـ dotenv

# ==========================================
# ⚙️ الإعدادات وجلب متغيرات البيئة (Environment Variables)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")

# تحويل المعرف الرقمي إلى عدد صحيح (int) للتحقق منه بأمان
try:
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
except ValueError:
    ADMIN_TELEGRAM_ID = 0

# إعداد السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(name)

# التحقق من وجود المتغيرات الهامة قبل البدء لضمان تشغيل آمن
if not TELEGRAM_BOT_TOKEN or not GITHUB_ACCESS_TOKEN:
    logger.critical("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN أو GITHUB_ACCESS_TOKEN في متغيرات البيئة!")
    sys.exit("خطأ في تشغيل البوت: يرجى ضبط متغيرات البيئة أولاً.")

# ==========================================
# 🔌 الاتصال بـ GitHub API
# ==========================================
github_client = None
github_user = None

try:
    github_client = Github(GITHUB_ACCESS_TOKEN)
    github_user = github_client.get_user()
    logger.info(f"✅ تم الاتصال بحساب GitHub بنجاح: {github_user.login}")
except Exception as e:
    logger.error(f"❌ فشل الاتصال الأولي بـ GitHub API: {e}")

# ==========================================
# 💾 قاعدة البيانات المؤقتة وجلسات المستخدمين
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
# ⌨️ لوحات المفاتيح وتنسيق الأزرار (Keyboards)
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