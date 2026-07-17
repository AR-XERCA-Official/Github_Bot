# ==========================================
# 🛠️ المكتبات الأساسية والبيئة والويب
# ==========================================
import os
import sys
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from github import Github, GithubException

# تحميل متغيرات البيئة محلياً (إذا كنت تجرّب الكود على جهازك أولاً)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# ⚙️ إعداد السجلات والتحقق من المتغيرات البيئية
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# جلب القيم الحساسة من البيئة بأمان
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")

try:
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
except (ValueError, TypeError):
    ADMIN_TELEGRAM_ID = 0

if not TELEGRAM_BOT_TOKEN or not GITHUB_ACCESS_TOKEN:
    logger.critical("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN أو GITHUB_ACCESS_TOKEN في متغيرات البيئة!")
    sys.exit("توقف التشغيل: يرجى إعداد متغيرات البيئة أولاً.")

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
# 💾 إدارة الجلسات وقاعدة البيانات المؤقتة
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
# ⌨️ تصميم لوحات المفاتيح والأزرار التفاعلية
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
# 🛠️ معالجات ووظائف البوت الأساسية
# ==========================================

# أمر البدء (Start Command)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("⛔ عذراً، هذا البوت خاص بمسؤول النظام فقط ولا يمكن استخدام لوحة التحكم الخاصة به.")
        return
    
    clear_session_action(user_id)
    await update.message.reply_text(
        "مرحبا بك في لوحة تحكم Github المتطورة 🚀\nيمكنك الآن إدارة مستودعاتك بالكامل عبر الأزرار التفاعلية أدناه:",
        reply_markup=main_menu_keyboard()
    )

# استعراض قائمة المستودعات
async def list_repositories_action(query, context: ContextTypes.DEFAULT_TYPE):
    try:
        await query.edit_message_text("🔄 جاري سحب قائمة مستودعاتك من جيت هاب...")
        repos = github_user.get_repos()
        
        keyboard = []
        text = "📂 **مستودعاتك العامة والخاصة:**\n\nاختر مستودعاً لإدارته والتحكم به مباشرة:"
        
        for repo in repos:
            keyboard.append([InlineKeyboardButton(f"📁 {repo.name}", callback_data=f"repo_manage_{repo.name}")])
            
        keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب المستودعات: `{str(e)}`", reply_markup=back_to_main_keyboard())

# عرض لوحة التحكم للمستودع المختار
async def show_repo_control_panel(query, context: ContextTypes.DEFAULT_TYPE, repo_name: str):
    user_id = query.from_user.id
    session = get_session(user_id)
    session["current_repo"] = repo_name
    
    try:
        repo = github_user.get_repo(repo_name)
        desc = repo.description if repo.description else "لا يوجد وصف حالياً."
        info = (
            f"🛠️ **لوحة التحكم بالمستودع: `{repo_name}`**\n\n"
            f"📝 الوصف: {desc}\n"
            f"🌟 النجوم: {repo.stargazers_count} | 🍴 التفرعات: {repo.forks_count}\n"
            f"🔗 [رابط المستودع على GitHub]({repo.html_url})"
        )
        await query.edit_message_text(info, reply_markup=repo_management_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل الوصول للمستودع: `{str(e)}`", reply_markup=back_to_main_keyboard())

# تفعيل GitHub Pages
async def enable_github_pages_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
        await query.edit_message_text("❌ انتهت الجلسة أو لم يتم تحديد المستودع الحالي.")
        return
        
    custom_url = f"https://{github_user.login}.github.io/{repo_name}/"
    reply_markup = back_to_repo_keyboard(repo_name)

    try:
        await query.edit_message_text(f"🔄 جاري محاولة تفعيل استضافة الويب لـ `{repo_name}`...")
        repo = github_user.get_repo(repo_name)
        
        repo.create_pages(source={"branch": "main", "path": "/"})
        
        success_text = (
            f"🚀 **تم تفعيل الاستضافة بنجاح!**\n\n"
            f"🔗 **رابط موقعك المباشر:**\n{custom_url}\n\n"
            f"💡 _ملاحظة: انتظر دقيقة واحدة ثم افتح الرابط ليعمل موقعك الخاص!_"
        )
        await query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except GithubException as e:
        error_msg = e.data.get('message', '')
        if "already exists" in error_msg or "already" in error_msg:
            await query.edit_message_text(f"ℹ️ **الاستضافة مفعلة بالفعل لهذا المستودع!**\n\n🔗 **رابط موقعك الحي:**\n{custom_url}", reply_markup=reply_markup, parse_mode="Markdown")
        else:
            bypass_text = (
                f"🚀 الموقع جاهز للعمل برمجياً!\n\n"
                f"🔗 **الرابط المخصص لك سيكون:**\n{custom_url}\n\n"
                f"⚠️ **ملاحظة مهمة:** إذا لم يفتح الرابط معك خلال دقائق، توجه إلى حسابك على المتصفح وافتح إعدادات المستودع (Settings) ثم قسم (Pages) وتأكد من اختيار فرع `main` يدوياً لمرة واحدة لتفعيله."
            )
            await query.edit_message_text(bypass_text, reply_markup=reply_markup, parse_mode="Markdown")
            
    except Exception as e:
        await query.edit_message_text(f"🔗 رابط موقعك المتوقع هو:\n{custom_url}\n\n(تأكد من إتمام رفع ملف `index.html` أولاً)", reply_markup=reply_markup)

# استعراض ملفات المستودع
async def list_repo_files_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
        await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
        return
        
    try:
        await query.edit_message_text(f"🔄 جاري قراءة الملفات من مستودع `{repo_name}`...")
        repo = github_user.get_repo(repo_name)
        contents = repo.get_contents("")
        
        files_text = f"📋 **الملفات الموجودة في مستودع `{repo_name}`:**\n\n"
        count = 0
        for content_file in contents:
            count += 1
            icon = "📄" if content_file.type == "file" else "📁"
            files_text += f"{count}. {icon} `{content_file.name}`\n"
            
        if count == 0:
            files_text = f"📭 المستودع `{repo_name}` فارغ تماماً حالياً!"
            
        await query.edit_message_text(files_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب الملفات: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# استعراض الفروع (Branches)
async def list_repo_branches_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
        await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
        return
        
    try:
        await query.edit_message_text(f"🔄 جاري سحب قائمة الفروع لـ `{repo_name}`...")
        repo = github_user.get_repo(repo_name)
        branches = repo.get_branches()
        
        branches_text = f"🌿 **الفروع (Branches) في مستودع `{repo_name}`:**\n\n"
        count = 0
        for b in branches:
            count += 1
            is_default = " ⭐ (الرئيسي)" if b.name == repo.default_branch else ""
            branches_text += f"{count}. 🔹 `{b.name}`{is_default}\n"
            
        await query.edit_message_text(branches_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب الفروع: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# استعراض المشاكل والتقارير (Issues)
async def list_repo_issues_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
        await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
        return
        
    try:
        await query.edit_message_text(f"🔄 جاري قراءة التقارير لـ `{repo_name}`...")
        repo = github_user.get_repo(repo_name)
        issues = repo.get_issues(state='open')
        
        issues_text = f"🐛 **التقارير والمشاكل المفتوحة في `{repo_name}`:**\n\n"
        count = 0
        for i in issues:
            count += 1
            issues_text += f"{count}. ⚠️ `#{i.number}` - {i.title}\n"
            
        if count == 0:
            issues_text = f"🎉 لا توجد أي مشاكل أو تقارير مفتوحة في مستودع `{repo_name}`، كل شيء ممتاز!"
            
        await query.edit_message_text(issues_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل جلب التقارير: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# استعراض المساهمين
async def list_repo_collaborators_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
         await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
         return
    
    try:
         await query.edit_message_text(f"🔄 جاري جلب قائمة المساهمين لـ `{repo_name}`...")
         repo = github_user.get_repo(repo_name)
         collaborators = repo.get_collaborators()
         
         text = f"👥 **المساهمون في `{repo_name}`:**\n\n"
         count = 0
         for collab in collaborators:
              count += 1
              text += f"{count}. 👤 `{collab.login}`\n"
              
         await query.edit_message_text(text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
         await query.edit_message_text(f"❌ فشل جلب المساهمين: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# عرض الإعدادات
async def show_repo_settings_action(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    repo_name = get_session(user_id).get("current_repo")
    
    if not repo_name:
         await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
         return
         
    try:
         repo = github_user.get_repo(repo_name)
         settings_text = (
              f"⚙️ **إعدادات مستودع `{repo_name}`:**\n\n"
              f"🔒 حالة الخصوصية: {'خاص 🔒' if repo.private else 'عام 🌐'}\n"
              f"🌿 الفرع الرئيسي الافتراضي: `{repo.default_branch}`\n"
              f"📦 لغة البرمجة الأساسية: `{repo.language}`\n"
         )
         await query.edit_message_text(settings_text, reply_markup=back_to_repo_keyboard(repo_name), parse_mode="Markdown")
    except Exception as e:
         await query.edit_message_text(f"❌ فشل جلب الإعدادات: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# ==========================================
# 🎛️ معالج أزرار لوحة التحكم التفاعلية
# ==========================================
async def global_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await query.answer("⛔ غير مصرح لك باستخدام هذه اللوحة.", show_alert=True)
        return
        
    await query.answer()
    data = query.data
    session = get_session(user_id)

    if data == "main_list_repos":
        clear_session_action(user_id)
        await list_repositories_action(query, context)
        
    elif data == "main_prompt_create":
        session["action"] = "awaiting_repo_name_create"
        await query.edit_message_text("✍️ من فضلك أرسل الآن **اسم المستودع الجديد** الذي تريد إنشائه (باللغة الإنجليزية وبدون مسافات):", parse_mode="Markdown")
        
    elif data == "main_account_info":
        clear_session_action(user_id)
        info = f"👤 **معلومات الحساب المربوط:**\n\n• الاسم: `{github_user.name}`\n• اليوزر: `{github_user.login}`\n• المستودعات العامة: {github_user.public_repos}"
        await query.edit_message_text(info, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
        
    elif data == "back_to_main":
        clear_session_action(user_id)
        await query.edit_message_text("مرحبا بك في لوحة تحكم Github المتطورة", reply_markup=main_menu_keyboard())

    elif data.startswith("repo_manage_"):
        repo_name = data.replace("repo_manage_", "")
        clear_session_action(user_id)
        await show_repo_control_panel(query, context, repo_name)

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
        repo_name = session.get("current_repo")
        session["action"] = "awaiting_file_content_only"
        instruct = (
            f"📝 **إضافة/تعديل ملف في المستودع `{repo_name}`**\n\n"
            f"من فضلك أرسل الرسالة بالصيغة التالية تماماً:\n"
            f"**السطر الأول:** اكتب اسم الملف كاملاً (مثل: `index.html`)\n"
            f"**السطر الثاني وما بعده:** اكتب محتوى الكود مباشرة.\n\n"
            f"📥 البوت بانتظار كود الملف الآن..."
        )
        await query.edit_message_text(instruct, parse_mode="Markdown")
        
    elif data == "repo_prompt_delete":
        repo_name = session.get("current_repo")
        if not repo_name:
            await query.edit_message_text("❌ لم يتم تحديد مستودع نشط.")
            return
            
        try:
            await query.edit_message_text(f"🔄 جاري حذف المستودع `{repo_name}` نهائياً...")
            
            repo = github_user.get_repo(repo_name)
            repo.delete()
            
            clear_session_action(user_id)
            await query.edit_message_text(f"✅ تم حذف المستودع `{repo_name}` بنجاح ونهائياً!", reply_markup=back_to_main_keyboard())
            
        except Exception as e:
            await query.edit_message_text(f"❌ فشل الحذف المستودع.\nتأكد من تفعيل صلاحية (delete_repo) في التوكن الخاص بك.\nالخطأ: `{str(e)}`", reply_markup=back_to_repo_keyboard(repo_name))

# ==========================================
# 📥 معالج الرسائل النصية المباشرة
# ==========================================
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_TELEGRAM_ID: 
        return

    text = update.message.text.strip()
    session = get_session(user_id)
    action = session.get("action")

    if action == "awaiting_repo_name_create":
        clear_session_action(user_id)
        try:
            msg = await update.message.reply_text("🔄 جاري إنشاء مستودع عام جديد...")
            repo = github_user.create_repo(text, private=False, auto_init=True)
            session["current_repo"] = repo.name
            
            keyboard = [[InlineKeyboardButton("⚙️ فتح لوحة تحكم المستودع", callback_data=f"repo_manage_{repo.name}")]]
            await msg.edit_text(f"✅ **تم إنشاء المستودع العام بنجاح!**\n\n📁 الاسم: `{repo.name}`\n🔗 [رابطه على جيت هاب]({repo.html_url})", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ فشل الإنشاء: `{str(e)}`")

    elif action == "awaiting_file_content_only":
        repo_name = session.get("current_repo")
        lines = text.split("\n", 1)
        if len(lines) < 2:
            await update.message.reply_text("⚠️ صيغة خاطئة! يرجى كتابة اسم الملف في السطر الأول، ثم محتواه في السطور التالية.")
            return

        file_name = lines[0].strip()
        file_content = lines[1].strip()
        clear_session_action(user_id)
        
        try:
            msg = await update.message.reply_text(f"🔄 جاري رفع وتحديث الملف `{file_name}`...")
            repo = github_user.get_repo(repo_name)
            
            try:
                contents = repo.get_contents(file_name)
                repo.update_file(file_name, f"Update {file_name} via bot", file_content, contents.sha)
                await msg.edit_text(f"✅ تم تحديث الملف `{file_name}` بنجاح!", reply_markup=back_to_repo_keyboard(repo_name))
            except Exception:
                repo.create_file(file_name, f"Create {file_name} via bot", file_content)
                await msg.edit_text(f"✅ تم إنشاء ورفع ملف `{file_name}` الجديد بنجاح!", reply_markup=back_to_repo_keyboard(repo_name))
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ أثناء الرفع: `{str(e)}`")

# ==========================================
# 🌐 خادم الويب (Flask Server) لمتطلبات الاستضافة
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    # صفحة هبوط بسيطة تؤكد للاستضافة أن خادم الويب يعمل بصحة جيدة
    return "🚀 Bot Server is Active and Running!", 200

def run_flask():
    # منفذ البورت لربطه بالاستضافة، الافتراضي هو 8080
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ==========================================
# 🚀 نقطة التشغيل الرئيسية (Main)
# ==========================================
def main():
    # 1. بدء تشغيل خادم Flask في خيط مستقل بالخلفية
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("🌐 خادم ويب Flask يعمل الآن بالخلفية لتجنب الـ Port Timeout.")

    # 2. بدء البوت
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(global_button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))

    print("=" * 60)
    print("🚀 تم تجميع البوت ودمجه بنجاح مع Flask!")
    print("🌍 البوت جاهز تماماً للاستخدام.")
    print("=" * 60)
    
    application.run_polling()

if __name__ == '__main__':
    main()
