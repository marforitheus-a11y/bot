# bot.py
# Adicione a importação do painel
import ocr  # <--- Adicione isso lá em cima junto com os imports
import admin_panel
from telegram.ext import TypeHandler # Adicione isso nos imports

# ⚠️ DEFINA SEU ID DE TELEGRAM AQUI 
# (Mande uma msg pro bot e dê print(update.effective_user.id) se não souber, ou use o userinfobot)
ADMIN_ID = 8510230479  # <--- TROQUE PELO SEU ID REAL
from datetime import datetime
import payment_service
import logging
import io
import random
import string
import asyncio
from PIL import Image, ImageFilter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaDocument
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Local imports
from config import BOT_TOKEN, BLUR_RADIUS, DRIVE_FOLDER_ID
import db
import sync_service
from drive_service import download_file_bytes
from ocr_service import extract_text_from_bytes

# Logging Setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- CONFIGURATION ---
COUNTRIES = [
    ("ARGENTINA", "🇦🇷"), ("AUSTRALIA", "🇦🇺"), ("AUSTRIA", "🇦🇹"), ("BELGIUM", "🇧🇪"),
    ("BOLIVIA", "🇧🇴"), ("BRAZIL", "🇧🇷"), ("BULGARIA", "🇧🇬"), ("CAMEROON", "🇨🇲"),
    ("CANADA", "🇨🇦"), ("CHILE", "🇨🇱"), ("CHINA", "🇨🇳"), ("COLOMBIA", "🇨🇴"),
    ("COSTA RICA", "🇨🇷"), ("CUBA", "🇨🇺"), ("CZECH REPUBLIC", "🇨🇿"), ("DANMARK", "🇩🇰"),
    ("EGYPT", "🇪🇬"), ("ESTONIA", "🇪🇪"), ("FINLAND", "🇫🇮"), ("FRANCE", "🇫🇷"),
    ("GEORGIA", "🇬🇪"), ("GERMANY", "🇩🇪"), ("GREECE", "🇬🇷"), ("HUNGARY", "🇭🇺"),
    ("INDIA", "🇮🇳"), ("INDONESIA", "🇮🇩"), ("IRELAND", "🇮🇪"), ("ISLAND", "🇮🇸"), 
    ("ISRAEL", "🇮🇱"), ("ITALY", "🇮🇹"), ("JAPAN", "🇯🇵"), ("KAZAKHSTAN", "🇰🇿"),
    ("KUWAIT", "🇰🇼"), ("LATVIA", "🇱🇻"), ("LITHUANIA", "🇱🇹"), ("MALAYSIA", "🇲🇾"),
    ("MEXICO", "🇲🇽"), ("MOLDOVA", "🇲🇩"), ("MYANMAR", "🇲🇲"), ("NETHERLANDS", "🇳🇱"),
    ("NEW ZEALAND", "🇳🇿"), ("NIGERIA", "🇳🇬"), ("NORWAY", "🇳🇴"), ("PHILIPPINES", "🇵🇭"),
    ("POLAND", "🇵🇱"), ("PORTUGAL", "🇵🇹"), ("REPUBLIC OF KOSOVO", "XK"), ("ROMANIA", "🇷🇴"),
    ("RUSSIA", "🇷🇺"), ("SINGAPORE", "🇸🇬"), ("SLOVENSKA", "🇸🇰"), ("SOUTH AFRICA", "🇿🇦"),
    ("SOUTH KOREA", "🇰🇷"), ("SPAIN", "🇪🇸"), ("SWEDEN", "🇸🇪"), ("SWITZERLAND", "🇨🇭"),
    ("SYRIA", "🇸🇾"), ("THAILAND", "🇹🇭"), ("TURKEY", "🇹🇷"), ("UKRAINE", "🇺🇦"),
    ("UNITED KINGDOM", "🇬🇧"), ("UNITED STATES", "🇺🇸"), ("VIETNAM", "🇻🇳")
]

user_sessions = {}

# --- UTILS ---
def apply_blur(image_bytes):
    """Aplica blur e converte RGBA para RGB para evitar erro no JPEG."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # --- CORREÇÃO DE ERRO RGBA ---
        # Se a imagem tiver transparência (RGBA) ou paleta (P), converte para RGB (fundo branco/preto)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        # -----------------------------

        img = img.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
        
        output = io.BytesIO()
        img.save(output, format='JPEG')
        output.seek(0)
        return output
    except Exception as e:
        print(f"Erro ao aplicar blur: {e}")
        return None
        
        # --- SISTEMA DE DEPÓSITO (INTEGRADO COM payment_service.py) ---

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Tenta pegar o valor digitado: /deposit 10
    try:
        amount = float(context.args[0])
        if amount < 2: # O Oxapay tem minimo, geralmente uns 2 USD
            await update.message.reply_text("⚠️ Mínimo para depósito é $2.00")
            return
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Use: `/deposit 10` (para adicionar $10)", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("⏳ **Gerando Fatura OxaPay...**", parse_mode="Markdown")

    # Chama o SEU arquivo payment_service.py
    result = await payment_service.create_payment(user_id, amount)
    
    if result:
        pay_link = result['pay_link']
        track_id = result['track_id']
        
        # Salva na sessão temporária para checar depois
        session = user_sessions.get(user_id, {})
        session['payment_track_id'] = track_id
        session['payment_amount'] = amount
        user_sessions[user_id] = session # Atualiza sessão

        # Botão para verificar
        keyboard = [
            [InlineKeyboardButton("🔗 Pagar Agora", url=pay_link)],
            [InlineKeyboardButton("✅ Já Fiz o Pagamento", callback_data="check_deposit")]
        ]
        
        await msg.edit_text(
            f"💳 **Fatura Gerada!**\n\n"
            f"💰 Valor: **${amount:.2f}**\n"
            f"🆔 ID: `{track_id}`\n\n"
            f"1. Clique no link e pague.\n"
            f"2. Aguarde confirmação na blockchain.\n"
            f"3. Clique no botão abaixo para liberar o saldo.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await msg.edit_text("❌ Erro ao conectar com OxaPay. Tente novamente mais tarde.")
#PAYMENT LOGIC
async def check_deposit_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Recupera dados da sessão
    session = user_sessions.get(user_id)
    if not session or 'payment_track_id' not in session:
        await query.answer("❌ Nenhuma fatura pendente encontrada nesta sessão.", show_alert=True)
        return

    track_id = session['payment_track_id']
    amount = session['payment_amount']
    
    await query.answer("🔄 Verificando na Blockchain...")
    
    # Chama o SEU arquivo payment_service.py
    status = await payment_service.check_payment_status(track_id)
    
    if status == 'Paid':
        # 1. Adiciona o Saldo no Banco de Dados
        db.update_balance(user_id, amount)
        
        # 2. Limpa a sessão para não receber 2x
        del session['payment_track_id']
        del session['payment_amount']
        
        current_balance = db.get_balance(user_id)
        
        await query.edit_message_text(
            f"✅ **Pagamento Confirmado!**\n\n"
            f"➕ Creditado: ${amount:.2f}\n"
            f"💰 Saldo Atual: ${current_balance:.2f}"
        )
        
    elif status == 'Waiting' or status == 'Confirming':
        await query.answer("⏳ Pagamento ainda não confirmado. Aguarde alguns minutos e tente de novo.", show_alert=True)
        
    elif status == 'Expired':
        await query.edit_message_text("❌ **Fatura Expirada.** Gere uma nova com /deposit.")
        del session['payment_track_id']
        
    else:
        await query.answer(f"Status Atual: {status}", show_alert=True)
        
# --- BOT LOGIC ---

# No bot.py, substitua a função start por esta:

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Verifica Status VIP
    is_vip, vip_date = db.check_vip_status(user.id)
    vip_status_text = f"👑 VIP Active (Expires: {vip_date})" if is_vip else "👤 Free User"
    
    # Grade de Países
    keyboard = []
    row = []
    for country_name, flag_icon in COUNTRIES:
        btn = InlineKeyboardButton(f"{flag_icon} {country_name.title()}", callback_data=f"country:{country_name}")
        row.append(btn)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    # Botões de Ação (Planos e Saldo)
    keyboard.append([InlineKeyboardButton("👑 Buy VIP Subscription (Unlimited)", callback_data="plans_menu")])
    keyboard.append([InlineKeyboardButton("💳 Add Balance / Deposit", callback_data="deposit_menu")])

    if update.callback_query:
        await update.callback_query.answer()
        try: await update.callback_query.message.delete()
        except: pass
    else:
        db.add_balance(user.id, 0)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"👋 Welcome, {user.first_name}.\n\n"
             f"💎 Balance: ${db.get_balance(user.id):.2f}\n"
             f"🔰 Status: {vip_status_text}\n\n"
             "Select a region or manage your account:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
# --- STEP 2: FIND COUNTRY FOLDER (CACHE) ---
async def handle_country_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    country_name = query.data.split(":")[1]
    
    country_folder = db.get_cached_folder_by_name(DRIVE_FOLDER_ID, country_name)
    
    if not country_folder:
        await query.answer("⚠️ Database Error: Region not found. (Try /sync)", show_alert=True)
        return

    types_folders = db.get_cached_children(country_folder['id'], filter_type='folder')
    
    if not types_folders:
        await query.edit_message_text(f"❌ No categories found for {country_name}. (System Update Required: /sync)")
        return

    keyboard = []
    for t_folder in types_folders:
        is_usa = "1" if country_name == "UNITED STATES" else "0"
        # TEXTO PREMIUM 2: Botões de Categoria
        btn = InlineKeyboardButton(f"📂 {t_folder['name']}", callback_data=f"type:{t_folder['id']}:{is_usa}")
        keyboard.append([btn])
    
    keyboard.append([InlineKeyboardButton("🔙 Return to Main Menu", callback_data="main_menu")])

    flag = next((f for c, f in COUNTRIES if c == country_name), "🏳️")
    
    # TEXTO PREMIUM 3: Seleção de Tipo
    await query.edit_message_text(
        f"{flag} Region: {country_name}\n\n"
        "Select a document category to proceed:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- STEP 3: TYPE SELECTION (CACHE) ---
async def handle_type_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # query.data vem como: "type:ID_DA_PASTA"
    type_folder_id = query.data.split(":")[1]
    
    # Precisamos descobrir o NOME da pasta e o PAÍS atual para buscar o preço
    # 1. Recupera o nome desta pasta
    # (Como não temos o nome fácil aqui, vamos pegar do cache pelo ID)
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT name, parent_id FROM drive_cache WHERE id=?", (type_folder_id,))
    res_type = c.fetchone()
    
    if not res_type:
        await query.answer("⚠️ Error: Folder not found in cache. Sync again.")
        conn.close()
        return

    folder_name_raw = res_type[0]  # Ex: "Passport + ID"
    parent_id = res_type[1]        # ID da pasta do Brasil
    
    # 2. Recupera o nome do País (Pasta Pai)
    c.execute("SELECT name FROM drive_cache WHERE id=?", (parent_id,))
    res_country = c.fetchone()
    country_name_raw = res_country[0] if res_country else "Unknown"
    conn.close()
    
    # 3. VERIFICA PREÇO PERSONALIZADO
    custom_price = db.get_custom_price(country_name_raw, folder_name_raw)
    
    # Se achou preço no banco, usa ele. Se não, usa 10 (padrão)
    final_price = custom_price if custom_price is not None else 10.0
    
    # Feedback visual (Toast notification)
    await query.answer(f"Selected: {folder_name_raw} (${final_price:.2f})")
    
    # Passa o preço correto para o carregador de kits
    await load_kits_standard(query, type_folder_id, price=final_price)
# --- USA LOGIC (CACHE) ---
async def handle_usa_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    option = parts[1]
    type_folder_id = parts[2]

    if option == "any":
        await load_kits_usa_recursive(query, type_folder_id)
        
    elif option == "pick":
        states = db.get_cached_children(type_folder_id, filter_type='folder')
        
        if not states:
            await query.answer("❌ No states available in cache.", show_alert=True)
            return

        keyboard = []
        row = []
        for state in states:
            btn = InlineKeyboardButton(state['name'], callback_data=f"usa_state:{state['id']}")
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 Go Back", callback_data="main_menu")])

        await query.edit_message_text(
            "🇺🇸 Select Jurisdiction\n"
            "Price per kit: $7.00",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def handle_usa_state_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    state_folder_id = query.data.split(":")[1]
    await load_kits_standard(query, state_folder_id, price=12)

# --- KIT LOADING (CACHE) ---



async def load_kits_standard(query, type_folder_id, price):
    # 1. Pega o que tem dentro da pasta selecionada (ex: Os Estados ou Kits diretos)
    first_level_items = db.get_cached_children(type_folder_id, filter_type='folder')
    
    if not first_level_items:
        await query.edit_message_text("🚫Empty Category.\nNo folders found here.")
        return

    all_kits = []
    
    # 2. Lógica Inteligente: Verifica se é Kit ou Estado
    for item in first_level_items:
        # Verifica se dentro dessa pasta tem OUTRAS pastas (se tiver, é um Estado)
        sub_folders = db.get_cached_children(item['id'], filter_type='folder')
        
        if sub_folders:
            # É UM ESTADO! (Ex: California)
            # Adiciona todas as pastas de clientes que estão lá dentro
            all_kits.extend(sub_folders)
        else:
            # É UM KIT DIRETO! (Não tem subpastas, só arquivos)
            all_kits.append(item)
    
    # Se depois de varrer tudo não achou nada
    if not all_kits:
        await query.edit_message_text("🚫 No Valid Kits Found.\nStructure seems empty.")
        return

    # 3. Embaralha para não vir sempre o mesmo estado
    random.shuffle(all_kits)
    
    # Salva na sessão e mostra o primeiro
    await process_kit_list(query, all_kits, price)


async def process_kit_list(query, all_kits, price):
    bought_ids = db.get_bought_kits(query.from_user.id)
    new_kits = [k for k in all_kits if k['id'] not in bought_ids]
    
    if not new_kits:
        await query.edit_message_text("🚫 No Available Kits.\n\nYou have purchased all available files in this category.")
        return

    random.shuffle(new_kits)
    
    user_sessions[query.from_user.id] = {
        'kits': new_kits, 
        'index': 0,
        'price': price
    }
    
    await show_kit_preview(query, None)

# --- PREVIEW (CACHE + DOWNLOAD) ---
# In bot.py - Update show_kit_preview

async def show_kit_preview(query, context):
    bot = context.bot if context else query.message.get_bot()
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    if not session or not session['kits']:
        try: await query.message.reply_text("⚠️ Session Timeout. Please type /start to restart.")
        except: pass
        return

    # Safety check: Ensure index is within bounds
    if session['index'] >= len(session['kits']):
        session['index'] = 0

    kit = session['kits'][session['index']]
    price = session['price']
    
    files_in_kit = db.get_cached_children(kit['id'], filter_type='file')
    
    # --- FIX RECURSION: If empty, remove bad kit and try again (max 3 times) ---
    attempts = 0
    while not files_in_kit and attempts < 5:
        # Remove empty kit from session
        session['kits'].pop(session['index'])
        if not session['kits']:
            await query.edit_message_text("🚫 No Valid Kits Available.\nAll remaining folders are empty.")
            return
        
        # Adjust index
        if session['index'] >= len(session['kits']):
            session['index'] = 0
            
        kit = session['kits'][session['index']]
        files_in_kit = db.get_cached_children(kit['id'], filter_type='file')
        attempts += 1
        
    if not files_in_kit:
         await query.edit_message_text("⚠️ System Error: Selected region contains empty folders.")
         return
    # --------------------------------------------------------------------------

    preview_file = files_in_kit[0]
    raw_bytes = download_file_bytes(preview_file['id'])
    
    if not raw_bytes:
        await query.answer("⚠️ Connection Error. Skipping...")
        return

    blurred_io = apply_blur(raw_bytes)
    
    # ... (rest of the code: buttons, keyboard, sending photo) ...
    # Ensure you keep the rest of your button definition logic here!
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Prev", callback_data="nav:prev"), InlineKeyboardButton("Next ➡️", callback_data="nav:next")],
        [InlineKeyboardButton("🔍 Scan Text (OCR)", callback_data=f"ocr:{preview_file['id']}")],
        [InlineKeyboardButton(f"🛒 Purchase Kit (${price})", callback_data=f"buy:{kit['id']}")],
        [InlineKeyboardButton("🔙 Return to Main Menu", callback_data="main_menu")]
    ]
    
    try: await query.message.delete()
    except: pass
    
    await bot.send_photo(
        chat_id=user_id,
        photo=blurred_io,
        caption=f"📦 Secure Kit Preview\n\n"
                f"🆔 ID: `{kit['name']}`\n"
                f"📂 Contents: {len(files_in_kit)} Files included\n"
                f"🔒 Status: Protected Preview\n\n"
                f"💎 Price: ${price}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- NAVIGATION ---
# Coloque no bot.py (antes do main)

async def handle_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":")[1] # 'prev' ou 'next'
    user_id = query.from_user.id
    
    session = user_sessions.get(user_id)
    
    # Se a sessão expirou (o bot reiniciou ou passou muito tempo)
    if not session or not session['kits']:
        await query.answer("⚠️ Session Expired. Type /start.")
        return

    current_len = len(session['kits'])
    
    # --- LÓGICA DO CARROSSEL (LOOP) ---
    if action == "next":
        # Se chegou no último, volta para o PRIMEIRO (0)
        if session['index'] >= current_len - 1:
            session['index'] = 0 
        else:
            session['index'] += 1
            
    elif action == "prev":
        # Se está no primeiro, vai para o ÚLTIMO
        if session['index'] <= 0:
            session['index'] = current_len - 1
        else:
            session['index'] -= 1

    # Atualiza a mensagem com a nova foto
    await show_kit_preview(query, context)

# --- OCR ---
# No bot.py - Adicione ou substitua esta função

# No bot.py - Substitua a handle_ocr por esta versão "Smart Scan"

# No bot.py - Substitua a função handle_ocr antiga por esta simples

async def handle_ocr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # 1. Feedback visual rápido (Toast)
    await query.answer("⚠️ Feature under construction")
    
    # 2. Envia a mensagem de aviso
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "🚧 Maintenance Alert 🚧\n\n"
            "OCR Server will be implemented soon.\n"
            "_We are upgrading our OCR servers to provide 100% accuracy on all 67 countries._"
        ),
        parse_mode="Markdown"
    )

# Coloque isso no bot.py, antes do handle_buy

def collect_files_recursive(items_list):
    """
    Recebe uma lista de itens. 
    Se for arquivo, mantém. 
    Se for pasta, entra nela e pega os arquivos (Recursivo).
    """
    real_files = []
    
    for item in items_list:
        # Se for pasta, busca os filhos dela no banco e repete o processo
        if item.get('type') == 'folder':
            children = db.get_cached_children(item['id'])
            # Chama a si mesma para cavar mais fundo (Recursão)
            real_files.extend(collect_files_recursive(children))
        else:
            # Se for arquivo, adiciona na lista final
            real_files.append(item)
            
    return real_files


# No bot.py - Substitua a função handle_buy

# No bot.py - Substitua a função handle_buy INTEIRA

from telegram.constants import ParseMode # Adicione isso no topo se der erro


async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. Segurança: Só VOCÊ pode usar (troque pelo seu ID numérico real)
    if user_id != ADMIN_ID:  
        return

    try:
        # Formato: /add 123456789 10
        target_user_id = int(context.args[0])
        amount = float(context.args[1])
        
        # Usa a função que já criamos no DB
        db.update_balance(target_user_id, amount)
        
        await update.message.reply_text(f"✅ **Balance Updated!**\nUser: {target_user_id}\nAdded: ${amount:.2f}")
        
        # Tenta avisar o usuário que o saldo caiu
        try:
            await context.bot.send_message(target_user_id, f"💰 **Payment Received!**\nYour balance has been credited: +${amount:.2f}")
        except:
            pass # Se o usuário bloqueou o bot, ignora
            
    except:
        await update.message.reply_text("⚠️ Use: `/add <user_id> <amount>`")

async def handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # 1. Recupera sessão
    session = user_sessions.get(user_id)
    if not session or not session['kits']:
        await query.answer("⚠️ Session Expired.", show_alert=True)
        return

    price = session.get('price', 10.0)
    current_balance = db.get_balance(user_id) 
    
    if current_balance < price:
        await query.answer("❌ Insufficient Funds", show_alert=True)
        # MUDANÇA 1: HTML aqui
        await context.bot.send_message(user_id, f"❌ Insufficient Balance. Need: <b>${price}</b>", parse_mode="HTML")
        return

    await query.answer("💳 Processing...")
    
    # MUDANÇA 2: HTML aqui (<b> para negrito, <i> para itálico)
    status_msg = await context.bot.send_message(
        user_id, 
        "⏳ <b>Preparing Files...</b>\n<i>Collecting documents...</i>", 
        parse_mode="HTML"
    )

    try:
        current_index = session.get('index', 0)
        target_kit = session['kits'][current_index]
        
        files_to_send = collect_files_recursive([target_kit])
        
        if not files_to_send:
            raise Exception("This folder appears to be empty.")

        # 2. Debita e Registra
        db.update_balance(user_id, -price)
        db.record_sale(user_id, files_to_send[0]['id'], price)
        
        # 3. Envia Fatiado
        chunk_size = 10
        total_files = len(files_to_send)
        
        for i in range(0, total_files, chunk_size):
            batch = files_to_send[i : i + chunk_size]
            
            # MUDANÇA 3: HTML no Status
            await status_msg.edit_text(
                f"🚀 <b>Sending Batch {i//10 + 1}...</b>\n<i>Uploading files {i+1} to {min(i+chunk_size, total_files)}...</i>",
                parse_mode="HTML"
            )
            
            media_group = []
            
            for file_info in batch:
                file_bytes = download_file_bytes(file_info['id'])
                if file_bytes:
                    if hasattr(file_bytes, 'getvalue'): data = file_bytes.getvalue()
                    else: data = file_bytes
                    
                    media_group.append(InputMediaDocument(
                        media=data, 
                        filename=file_info['name'], 
                        # MUDANÇA 4: HTML na legenda do arquivo
                        caption=f"📂 <b>{file_info['name']}</b>",
                        parse_mode="HTML" 
                    ))
            
            if media_group:
                await context.bot.send_media_group(chat_id=user_id, media=media_group)

        # 4. Finalização
        new_bal = current_balance - price
        # MUDANÇA 5: HTML final
        await status_msg.edit_text(
            f"✅ <b>Delivery Complete!</b>\n📦 Sent {total_files} files.\n💰 Balance: <b>${new_bal:.2f}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        print(f"ERROR: {e}")
        db.update_balance(user_id, +price)
        await status_msg.edit_text(f"❌ Error: {str(e)}\n💰 Refunded.")
async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 🔒 SEGURANÇA: Apenas o Admin pode sincronizar
    if user_id != ADMIN_ID:
        # Opcional: Responder que não tem permissão
        await update.message.reply_text("⛔ You are not authorized.")
        return 

    status_msg = await update.message.reply_text("🔄 Syncing Drive with Database...\n_This may take a few seconds._", parse_mode="Markdown")
    
    try:
        # Função de callback para atualizar o progresso (opcional)
        def progress_callback(msg):
            print(f"Sync Log: {msg}")
            
        # Chama o serviço de sync
        await sync_service.sync_drive_to_db(progress_callback)
        
        await status_msg.edit_text("✅ Sync Complete!\nDatabase is up to date with Google Drive.")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Sync Failed:\n`{str(e)}`", parse_mode="Markdown")
# Substitua a função add_saldo_command no bot.py

async def add_saldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 🔒 TRAVA DE SEGURANÇA: Só o Admin passa daqui
    # Certifique-se de ter definido ADMIN_ID = SEU_ID no topo do arquivo
    if user_id != ADMIN_ID:
        # Opcional: Avisar que não tem permissão ou apenas ignorar
        return 

    try:
        # Cenário 1: Você quer dar saldo para um cliente
        # Uso: /add 123456789 50  (Dá $50 para o usuário 123456789)
        if len(context.args) == 2:
            target_id = int(context.args[0])
            amount = float(context.args[1])
            
            db.add_balance(target_id, amount)
            
            new_balance = db.get_balance(target_id)
            await update.message.reply_text(
                f"✅ Admin Action Confirmed\n\n"
                f"👤 Target User: `{target_id}`\n"
                f"➕ Added: ${amount:.2f}\n"
                f"💰 Their New Balance: ${new_balance:.2f}"
            )
            
            # Tenta avisar o usuário que ele ganhou saldo (opcional)
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"🎁 Gift Received!\n\nAdmin added ${amount:.2f} to your wallet."
                )
            except: pass

        # Cenário 2: Você quer dar saldo para si mesmo (Teste)
        # Uso: /add 100
        elif len(context.args) == 1:
            amount = float(context.args[0])
            db.add_balance(user_id, amount)
            
            await update.message.reply_text(
                f"✅ Admin Self-Topup\n"
                f"➕ Added: ${amount:.2f}\n"
                f"💰 Your Balance: ${db.get_balance(user_id):.2f}"
            )
            
        else:
            await update.message.reply_text("⚠️ Admin Usage:\n`/add [amount]` (for self)\n`/add [user_id] [amount]` (for others)", parse_mode="Markdown")

    except ValueError:
        await update.message.reply_text("❌ Error: IDs and Amounts must be numbers.")
    except Exception as e:
        await update.message.reply_text(f"❌ System Error: {e}")

async def reset_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.reset_history(update.effective_user.id)
    await update.message.reply_text("🔄 Account History Reset.")

    # --- SISTEMA DE PLANOS (SUBSCRIPTION) ---

async def plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o menu de assinaturas VIP."""
    user_id = update.effective_user.id
    
    # CONFIGURAÇÃO DE PREÇOS (Edite aqui se quiser)
    PRICES = {
        "daily": 10,   # $10 por 1 dia
        "weekly": 20,  # $20 por 7 dias
        "monthly": 50 # $50 por 30 dias
    }
    
    keyboard = [
        [InlineKeyboardButton(f"📅 Daily Access (${PRICES['daily']})", callback_data=f"buy_plan:daily:{PRICES['daily']}")],
        [InlineKeyboardButton(f"🗓 Weekly Access (${PRICES['weekly']})", callback_data=f"buy_plan:weekly:{PRICES['weekly']}")],
        [InlineKeyboardButton(f"📆 Monthly Pro (${PRICES['monthly']})", callback_data=f"buy_plan:monthly:{PRICES['monthly']}")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    
    msg_text = (
        "👑 VIP Premium Access\n\n"
        "Become a VIP member and get UNLIMITED ACCESS to all kits and documents without paying per file.\n\n"
        f"💰 Your Wallet Balance: ${db.get_balance(user_id):.2f}\n"
        "⚠️ _Make sure you have enough balance before selecting a plan._"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_plan_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, plan_type, price_str = query.data.split(":")
    price = float(price_str)
    user_id = query.from_user.id
    
    # 1. Verifica saldo
    if db.get_balance(user_id) < price:
        await query.answer("❌ Insufficient Funds. Please deposit first.", show_alert=True)
        return

    # 2. Define dias baseados no plano
    days_map = {"daily": 1, "weekly": 7, "monthly": 30}
    days = days_map.get(plan_type, 0)
    
    # 3. Desconta saldo e Ativa VIP
    db.add_balance(user_id, -price)
    new_expiry = db.set_subscription(user_id, days)
    
    date_str = new_expiry.strftime("%d/%m/%Y")
    
    await query.edit_message_text(
        f"🎉 Congratulations! You are now VIP.\n\n"
        f"✅ Plan Activated: {plan_type.title()}\n"
        f"⏳ Expires on: {date_str}\n\n"
        "You can now download ANY kit for free.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Start Downloading", callback_data="main_menu")]])
    )

# --- SISTEMA DE PAGAMENTO (VISUAL E UNIFICADO) ---

# 1. Menu de Escolha de Valores
async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o menu visual com botões de valores."""
    user_id = update.effective_user.id
    
    # Se veio pelo comando /deposit, usa update.message.
    # Se veio pelo botão, usa update.callback_query.message.
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message

    # Opções de recarga (Botões)
    keyboard = [
        [InlineKeyboardButton("💎 $1", callback_data="topup:1"), InlineKeyboardButton("💎 $5", callback_data="topup:5")],
        [InlineKeyboardButton("💎 $10", callback_data="topup:10"), InlineKeyboardButton("💎 $20", callback_data="topup:20")],
        [InlineKeyboardButton("💎 $50", callback_data="topup:50"), InlineKeyboardButton("💎 $100", callback_data="topup:100")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    
    current_balance = db.get_balance(user_id)
    msg_text = (
        f"💳 **Wallet Top-up**\n\n"
        f"💰 Current Balance: **${current_balance:.2f}**\n\n"
        "Select an amount to deposit via Crypto (USDT, BTC, LTC, etc):"
    )
    
    # Envia ou Edita a mensagem
    if update.callback_query:
        await message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# 2. Processa a escolha do valor e gera o Link

    
    await query.edit_message_text(
        f"🧾 **Invoice Created**\n"
        f"💵 Amount: **${amount:.2f}**\n\n"
        "1. Click the link below to pay.\n"
        "2. Payment is automatic (USDT, BTC, etc).\n"
        "3. Wait for blockchain confirmation.\n"
        "4. Click **'I Have Paid'** to update your balance.\n\n"
        "⏳ _Link expires in 30 minutes._",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# 3. Verifica o Status do Pagamento


async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Segurança: Só você pode ver isso
    if user_id != ADMIN_ID:
        return # Ignora curiosos
        
    status_msg = await update.message.reply_text("🔄 Generating Analytics...")
    
    # 1. Gera o Gráfico
    graph_bytes = admin_panel.generate_sales_graph(days=7)
    
    # 2. Gera o Texto
    report_text = admin_panel.get_admin_summary()
    
    # 3. Teclado de Manutenção
    keyboard = [
        [InlineKeyboardButton("🔄 Force Sync Drive", callback_data="admin_sync")],
        [InlineKeyboardButton("💾 Backup Database", callback_data="admin_backup")]
    ]
    
    if graph_bytes:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=graph_bytes,
            caption=report_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=report_text + "\n\n_(Not enough data for graph)_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    await status_msg.delete()

async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID: return

    if query.data == "admin_sync":
        await query.answer("🔄 Starting Sync...")
        await sync_service.sync_drive_to_db(lambda x: print(x))
        await context.bot.send_message(chat_id=user_id, text="✅ Sync Completed Successfully.")
        
    elif query.data == "admin_backup":
        await query.answer("💾 Uploading DB...")
        with open("users.db", "rb") as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=f"backup_users_{datetime.now().strftime('%Y%m%d')}.db",
                caption="🔒 Secure Database Backup"
            )

async def activity_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra qualquer movimento do usuário."""
    if update.effective_user:
        db.update_last_seen(update.effective_user.id)
    # Não paramos o código aqui, deixamos ele continuar para os outros comandos

# No bot.py - Substitua a função set_price_command

async def set_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. Segurança: Só Admin
    if user_id != ADMIN_ID:
        return

    # Esperado: /set [country/global] [nome da pasta] [preço]
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ Price Settings\n\n"
            "To set a price for a specific country:\n"
            "`/set brazil passport 15`\n\n"
            "To set a GLOBAL price (all countries):\n"
            "`/set global passport 20`\n"
            "_(Specific country prices override global)_", 
            parse_mode="Markdown"
        )
        return

    try:
        target = args[0].lower()   # Pode ser 'brazil', 'usa' ou 'global'
        price = float(args[-1])    # Último argumento é o preço
        
        # O nome da pasta é tudo que sobrou no meio
        folder_name = " ".join(args[1:-1]) 
        
        # Salva no banco
        db.set_custom_price(target, folder_name, price)
        
        if target == 'global':
            msg = (f"🌍 GLOBAL Price Updated!\n\n"
                   f"📂 Type: {folder_name.title()}\n"
                   f"💲 New Price: ${price:.2f} (All Countries)")
        else:
            msg = (f"✅ Specific Price Updated!\n\n"
                   f"🏳️ Country: {target.title()}\n"
                   f"📂 Type: {folder_name.title()}\n"
                   f"💲 New Price: ${price:.2f}")
            
        await update.message.reply_text(msg)
        
    except ValueError:
        await update.message.reply_text("❌ Error: The last argument must be a number (price).")
    except Exception as e:
        await update.message.reply_text(f"❌ System Error: {e}")

# --- Adicione no bot.py ---
import asyncio # Importante para o broadcast não travar

# 1. COMANDO DE BROADCAST (Mensagem Global)
# No bot.py - Substitua a função broadcast_command

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    # Verifica se é uma resposta a uma mídia (Foto, Video, Arquivo)
    reply = update.message.reply_to_message
    
    # Verifica se tem texto digitado
    text_args = " ".join(context.args)

    # Se não for resposta e não tiver texto, ensina como usar
    if not reply and not text_args:
        await update.message.reply_text(
            "⚠️ <b>How to use Broadcast:</b>\n\n"
            "1️⃣ <b>Text Only:</b>\n"
            "<code>/broadcast Hello everyone!</code>\n\n"
            "2️⃣ <b>Media (Photo/File):</b>\n"
            "Send the photo to the bot first, then <b>reply</b> to it with <code>/broadcast</code>.",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text("⏳ <b>Starting Broadcast...</b>\n<i>Do not turn off the bot.</i>", parse_mode="HTML")
    
    all_users = db.get_all_user_ids()
    sent_count = 0
    blocked_count = 0

    for uid in all_users:
        try:
            if reply:
                # MÁGICA: copy_message envia qualquer tipo de mídia (foto, vídeo, arquivo)
                # exatamente como ela é (incluindo a legenda original da foto)
                await context.bot.copy_message(
                    chat_id=uid, 
                    from_chat_id=user_id, 
                    message_id=reply.message_id
                )
            else:
                # Se for só texto, envia com formatação HTML
                await context.bot.send_message(
                    chat_id=uid, 
                    text=f"📢 <b>Announcement</b>\n\n{text_args}", 
                    parse_mode="HTML"
                )
            
            sent_count += 1
            await asyncio.sleep(0.05) # Pausa anti-spam
            
        except Exception:
            blocked_count += 1 # Usuário bloqueou o bot

    await update.message.reply_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"📨 Sent: <b>{sent_count}</b>\n"
        f"🚫 Failed: <b>{blocked_count}</b>",
        parse_mode="HTML"
    )
async def survey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    # Formato: /survey Pergunta | Opcao 1 | Opcao 2
    full_text = " ".join(context.args)
    parts = full_text.split("|")
    
    if len(parts) < 2:
        await update.message.reply_text("⚠️ Use: `/survey Question | Option 1 | Option 2`")
        return

    question = parts[0].strip()
    options = [o.strip() for o in parts[1:]]

    # Cria botões
    keyboard = []
    row = []
    for opt in options:
        # Callback: vote:OpcaoEscolhida
        row.append(InlineKeyboardButton(opt, callback_data=f"vote:{opt[:15]}"))
        if len(row) == 2: # 2 botões por linha
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("⏳ Sending Survey...")
    
    all_users = db.get_all_user_ids()
    for uid in all_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📊 Poll:\n\n{question}", reply_markup=reply_markup)
            await asyncio.sleep(0.05)
        except: pass

    await update.message.reply_text("✅ Survey Sent!")

# Handler para registrar o voto (Adicione no main)
async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    vote = query.data.split(":")[1]
    user_name = query.from_user.first_name
    
    # 1. Avisa o usuário que o voto foi computado
    await query.answer("✅ Vote registered!")
    await query.edit_message_text(f"✅ You voted: {vote}\n_Thank you for your feedback!_", parse_mode="Markdown")
    
    # 2. Avisa o ADMIN (Só você vê isso)
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🗳️ New Vote!\nUser: {user_name}\nChoice: {vote}"
    )

# 3. COMANDO PARA SETAR PREÇO DOS PLANOS
async def set_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    # Ex: /setplan 30 15 (30 dias = $15)
    try:
        days = int(context.args[0])
        price = float(context.args[1])
        
        db.set_plan_price(days, price)
        
        await update.message.reply_text(f"✅ Plan Updated!\n🗓️ Duration: {days} days\n💎 New Price: ${price:.2f}")
    except:
        await update.message.reply_text("⚠️ Use: `/setplan <days> <price>`\nExample: `/setplan 30 19.90`")

# 4. FUNÇÃO AUXILIAR PARA O MENU VIP (Substitua a sua antiga se quiser usar os preços novos)
async def show_vip_plans(update, context):
    # Pega os planos do banco
    plans = db.get_all_plans()
    
    keyboard = []
    for days, price in plans:
        # Cria botão dinâmico
        keyboard.append([InlineKeyboardButton(f"🗓️ {days} Days - ${price:.2f}", callback_data=f"buy_plan:{days}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envia (ou edita) mensagem
    if update.callback_query:
        await update.callback_query.message.reply_text("💎 Choose a VIP Plan:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("💎 Choose a VIP Plan:", reply_markup=reply_markup)

# --- CORRECT PAYMENT SYSTEM (DATABASE INTEGRATED) ---
async def handle_topup_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    amount = float(query.data.split(":")[1])
    user_id = query.from_user.id
    
    await query.answer("🔄 Connecting to OxaPay...")
    
    # 1. Create Invoice
    payment_data = await payment_service.create_payment(user_id, amount)
    
    if not payment_data:
        await query.edit_message_text("❌ Error connecting to payment provider.")
        return
        
    pay_link = payment_data['pay_link']
    track_id = payment_data['track_id']
    
    # 2. Save to Database
    db.save_payment(track_id, user_id, amount)
    
    keyboard = [
        [InlineKeyboardButton("🔗 Click to Pay (Crypto)", url=pay_link)],
        # HERE IS THE FIX: We attach the track_id to the button
        [InlineKeyboardButton("✅ I Have Paid", callback_data=f"check_pay:{track_id}")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="deposit_menu")]
    ]
    
    await query.edit_message_text(
        f"🧾 **Invoice Created**\n"
        f"💵 Amount: **${amount:.2f}**\n\n"
        "1. Click the link below to pay.\n"
        "2. Wait for confirmation (approx 1-5 mins).\n"
        "3. Click **'I Have Paid'** button below.\n\n"
        "⏳ _Link expires in 30 minutes._",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # 1. Get Track ID
    try:
        # Format expected: check_pay:123456
        track_id = query.data.split(":")[1]
    except IndexError:
        await query.answer("⚠️ Error: Old button format. Create a new invoice.", show_alert=True)
        return

    await query.answer("🔄 Checking Blockchain...") # Toast notification

    try:
        # 2. Retrieve from DB
        # If this line fails, it means db.get_payment_by_track_id is missing or broken
        payment_info = db.get_payment_by_track_id(track_id)
        
        if not payment_info:
            await query.answer("❌ Invoice not found in database.", show_alert=True)
            # Debugging help:
            print(f"DEBUG: Track ID {track_id} not found for User {user_id}")
            return
            
        # Security Check
        if payment_info['user_id'] != user_id:
            await query.answer("⛔ Access Denied: Not your invoice.", show_alert=True)
            return

        # Double Payment Check
        if payment_info['status'] == 'Completed':
            await query.edit_message_text(f"✅ Payment {track_id} already credited.")
            return

        # 3. Check OxaPay
        status = await payment_service.check_payment_status(track_id)
        amount = payment_info['amount']

        # --- LOGIC HANDLER ---
        if status == 'Paid' or status == 'Confirming':
            # SUCCESS
            db.add_balance(user_id, amount)
            db.mark_payment_completed(track_id)
            new_bal = db.get_balance(user_id)
            
            await query.edit_message_text(
                f"✅ **Payment Confirmed!**\n\n"
                f"➕ Credit: **${amount:.2f}**\n"
                f"💰 New Balance: **${new_bal:.2f}**\n\n"
                "Thank you!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            )

        elif status == 'Waiting':
            # FIX: Update the message so you KNOW it checked
            keyboard = [
                [InlineKeyboardButton("🔗 Pay Link", url=f"https://oxapay.com/pay/{track_id}")], # Optional: Rebuild link if possible or just remove
                [InlineKeyboardButton("🔄 Refresh Status", callback_data=f"check_pay:{track_id}")]
            ]
            
            await query.edit_message_text(
                f"⏳ **Payment Status: Waiting**\n"
                f"🆔 Invoice: `{track_id}`\n"
                f"💵 Amount: ${amount:.2f}\n\n"
                f"_The blockchain has not confirmed it yet. This usually takes 5-15 minutes for Crypto._\n\n"
                f"🕒 Checked at: {datetime.now().strftime('%H:%M:%S')}\n"
                f"Please wait and click **Refresh** below.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

        elif status == 'Expired':
            await query.edit_message_text("❌ Invoice Expired. Please create a new deposit.")

        else:
            # Handle "Error" or unknown statuses
            await query.edit_message_text(f"⚠️ OxaPay Status: {status}\nTry again in a moment.")

    except AttributeError as e:
        # This catches the most likely error (Missing function in db.py)
        error_msg = f"❌ CRASH: Function missing in db.py?\nError: {e}"
        await context.bot.send_message(chat_id=user_id, text=error_msg)
        print(error_msg)
        
    except Exception as e:
        # Catches any other crash
        error_msg = f"❌ SYSTEM ERROR: {str(e)}"
        await context.bot.send_message(chat_id=user_id, text=error_msg)
        print(error_msg)

def main():
    # Inicializa o Banco de Dados (Cria tabelas se não existirem)
    db.init_db()
    
    # Constrói o App
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Rastreador de Atividade (Roda em tudo para saber quem está online)
    app.add_handler(TypeHandler(Update, activity_tracker), group=-1)

    # --- 1. COMANDOS BÁSICOS ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_history_command))
    
    # --- 2. COMANDOS DE ADMINISTRAÇÃO ---
    app.add_handler(CommandHandler("admin", admin_dashboard))       # Painel Admin
    app.add_handler(CommandHandler("sync", sync_command))           # Sincronizar Google Drive
    app.add_handler(CommandHandler("add", add_balance_command))     # Adicionar Saldo Manualmente
    app.add_handler(CommandHandler("broadcast", broadcast_command)) # Enviar msg para todos
    app.add_handler(CommandHandler("survey", survey_command))       # Criar Enquete
    app.add_handler(CommandHandler("setplan", set_plan_command))    # Mudar preço VIP
    app.add_handler(CommandHandler("set", set_price_command))       # Mudar preço de Pastas

    # --- 3. COMANDOS DE PAGAMENTO (UNIFICADO) ---
    # Tanto digitar /deposit quanto clicar no botão levam ao Menu Visual
    app.add_handler(CommandHandler("deposit", deposit_menu))

    # --- 4. HANDLERS DE BOTÕES (CALLBACKS) ---

    # Navegação Geral
    app.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(deposit_menu, pattern="^deposit_menu$"))
    app.add_handler(CallbackQueryHandler(plans_menu, pattern="^plans_menu$"))

    # Fluxo de Compra (País -> Tipo -> Estado -> Compra)
    app.add_handler(CallbackQueryHandler(handle_country_select, pattern="^country:"))
    app.add_handler(CallbackQueryHandler(handle_type_select, pattern="^type:"))
    app.add_handler(CallbackQueryHandler(handle_usa_option, pattern="^usa_opt:"))
    app.add_handler(CallbackQueryHandler(handle_usa_state_select, pattern="^usa_state:"))
    
    # Ações do Item (Preview, OCR, Buy)
    app.add_handler(CallbackQueryHandler(handle_navigation, pattern="^nav:"))
    app.add_handler(CallbackQueryHandler(handle_buy, pattern="^buy:"))
    app.add_handler(CallbackQueryHandler(handle_ocr, pattern="^ocr:"))

    # Sistema de Pagamento (Oxapay e Planos)
    app.add_handler(CallbackQueryHandler(handle_topup_selection, pattern="^topup:")) # Escolha de valor
    # Removed the '$' to allow text after check_pay (like check_pay:12345)
    app.add_handler(CallbackQueryHandler(handle_check_payment, pattern="^check_pay"))
    app.add_handler(CallbackQueryHandler(handle_plan_purchase, pattern="^buy_plan:")) # Comprar VIP

    # Ações Administrativas & Extras
    app.add_handler(CallbackQueryHandler(admin_actions, pattern="^admin_")) # Botões do Painel Admin
    app.add_handler(CallbackQueryHandler(handle_vote, pattern="^vote:"))    # Votos da Enquete

    print("🤖 Bot Running Successfully (System Unified)...")
    app.run_polling()

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()

