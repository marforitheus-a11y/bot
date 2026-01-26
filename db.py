# db.py
import sqlite3
from datetime import datetime, timedelta

DB_NAME = "users.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    init_prices_table()
    init_subscription_prices()
    
    # --- ADICIONE ESSA LINHA AQUI: ---
    init_payments_table() # <--- ESSENCIAL PARA O PAGAMENTO NÃO SUMIR
    # ---------------------------------
    
    conn = get_connection()
    c = conn.cursor()
    
    # Tabela de Usuários (COM LAST_SEEN)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, 
        balance REAL DEFAULT 0,
        sub_expiry TEXT,
        last_seen TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS seen_history (
        user_id INTEGER, 
        kit_id TEXT, 
        price REAL,
        purchase_date TEXT,
        UNIQUE(user_id, kit_id)
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS drive_cache (
        id TEXT PRIMARY KEY,
        name TEXT,
        parent_id TEXT,
        node_type TEXT,
        mime_type TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_parent ON drive_cache (parent_id)")
    
    conn.commit()
    conn.close()
def update_last_seen(user_id):
    """Atualiza o horário que o usuário mexeu no bot."""
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Garante que o usuário existe
    c.execute("INSERT OR IGNORE INTO users (id, balance) VALUES (?, 0)", (user_id,))
    # Atualiza o visto por último
    c.execute("UPDATE users SET last_seen = ? WHERE id=?", (now, user_id))
    
    conn.commit()
    conn.close()

def get_active_users_count(minutes=10):
    """Conta quantos usuários interagiram nos últimos X minutos."""
    conn = get_connection()
    c = conn.cursor()
    
    limit_time = datetime.now() - timedelta(minutes=minutes)
    limit_str = limit_time.strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT COUNT(*) FROM users WHERE last_seen >= ?", (limit_str,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

# --- FUNÇÕES CORE (MANTIDAS) ---

def get_balance(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def add_balance(user_id, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, balance) VALUES (?, 0)", (user_id,))
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
    conn.commit()
    conn.close()

def set_subscription(user_id, days):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT sub_expiry FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    current_expiry = res[0] if res else None
    now = datetime.now()
    
    if current_expiry:
        try:
            exp_date = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S")
            if exp_date > now: new_expiry = exp_date + timedelta(days=days)
            else: new_expiry = now + timedelta(days=days)
        except: new_expiry = now + timedelta(days=days)
    else:
        new_expiry = now + timedelta(days=days)
        
    c.execute("UPDATE users SET sub_expiry = ? WHERE id=?", (new_expiry.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()
    return new_expiry

def check_vip_status(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT sub_expiry FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    if res and res[0]:
        try:
            exp_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
            if exp_date > datetime.now(): return True, exp_date.strftime("%d/%m/%Y")
        except: pass
    return False, None

def mark_kit_as_bought(user_id, kit_id, price):
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("INSERT OR IGNORE INTO seen_history (user_id, kit_id, price, purchase_date) VALUES (?, ?, ?, ?)", (user_id, kit_id, price, now))
        conn.commit()
    except: pass
    conn.close()

def get_sales_stats(days=7):
    conn = get_connection()
    c = conn.cursor()
    date_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = "SELECT substr(purchase_date, 1, 10) as day, SUM(price) as total, COUNT(*) as volume FROM seen_history WHERE purchase_date >= ? GROUP BY day ORDER BY day ASC"
    c.execute(query, (date_limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_last_sales(limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, kit_id, price, purchase_date FROM seen_history ORDER BY purchase_date DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    res = c.fetchone()
    conn.close()
    return res[0]

# No db.py - Substitua a função get_cached_children

def get_cached_children(parent_id, filter_type=None):
    conn = get_connection()
    c = conn.cursor()
    
    # MUDANÇA: Adicionamos 'node_type' na busca
    query = "SELECT id, name, node_type FROM drive_cache WHERE parent_id = ?"
    params = [parent_id]
    
    if filter_type == 'folder': query += " AND node_type = 'folder'"
    elif filter_type == 'file': query += " AND node_type = 'file'"
    
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    
    # MUDANÇA: Retornamos o 'type' no dicionário
    return [{'id': r[0], 'name': r[1], 'type': r[2]} for r in rows]


def get_cached_folder_by_name(parent_id, name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM drive_cache WHERE parent_id = ? AND name LIKE ? AND node_type = 'folder'", (parent_id, name))
    res = c.fetchone()
    conn.close()
    return {'id': res[0], 'name': res[1]} if res else None

def get_parent_id(file_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT parent_id FROM drive_cache WHERE id=?", (file_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def get_bought_kits(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT kit_id FROM seen_history WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def reset_history(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM seen_history WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def clear_cache():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM drive_cache")
    conn.commit()
    conn.close()

def insert_cache_item(item_id, name, parent_id, node_type, mime_type):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO drive_cache (id, name, parent_id, node_type, mime_type) VALUES (?, ?, ?, ?, ?)", (item_id, name, parent_id, node_type, mime_type))
    conn.commit()
    conn.close()
    
    # --- Adicione isso no final do db.py ---

def init_prices_table():
    """Cria a tabela de preços customizados se não existir."""
    conn = get_connection()
    c = conn.cursor()
    # Tabela: País, Nome da Pasta (Tipo), Preço
    c.execute("""
    CREATE TABLE IF NOT EXISTS custom_prices (
        country TEXT,
        folder_name TEXT,
        price REAL,
        UNIQUE(country, folder_name)
    )
    """)
    conn.commit()
    conn.close()

def set_custom_price(country, folder_name, price):
    """Define ou atualiza o preço de um tipo específico."""
    conn = get_connection()
    c = conn.cursor()
    # Salva tudo em minúsculo para facilitar a busca
    c.execute("INSERT OR REPLACE INTO custom_prices (country, folder_name, price) VALUES (?, ?, ?)", 
              (country.lower(), folder_name.lower(), price))
    conn.commit()
    conn.close()

# No db.py - Substitua a função get_custom_price

def get_custom_price(country, folder_name):
    """
    Busca o preço com hierarquia:
    1. Preço Específico do País (ex: Brazil > Passport)
    2. Preço Global (ex: Global > Passport)
    3. Retorna None (para usar o padrão depois)
    """
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Tenta achar o preço específico para este país
    c.execute("SELECT price FROM custom_prices WHERE country=? AND folder_name=?", 
              (country.lower(), folder_name.lower()))
    res_specific = c.fetchone()
    
    if res_specific:
        conn.close()
        return res_specific[0] # Retorna o preço específico
        
    # 2. Se não achou, tenta achar o preço GLOBAL ('global')
    c.execute("SELECT price FROM custom_prices WHERE country='global' AND folder_name=?", 
              (folder_name.lower(),))
    res_global = c.fetchone()
    
    conn.close()
    
    # Retorna o global se existir, senão retorna None
    return res_global[0] if res_global else None
# --- COLE ISSO NO FINAL DO ARQUIVO db.py ---

def update_balance(user_id, amount):
    """
    Atualiza o saldo do usuário.
    Se amount for positivo (+10), adiciona saldo.
    Se amount for negativo (-10), remove saldo.
    """
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Garante que o usuário existe na tabela antes de mexer no saldo
    # (Caso seja um usuário novo que nunca digitou /start)
    c.execute("INSERT OR IGNORE INTO users (id, balance) VALUES (?, 0)", (user_id,))
    
    # 2. Atualiza o valor
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    
    conn.commit()
    conn.close()
    
    # --- COLE ISSO NO FINAL DO ARQUIVO db.py ---

# --- COLE ISSO NO FINAL DO ARQUIVO db.py ---

def record_sale(user_id, kit_id, price):
    """
    Função de compatibilidade.
    O bot chama 'record_sale', mas o banco conhece como 'mark_kit_as_bought'.
    Isso redireciona uma para a outra.
    """
    return mark_kit_as_bought(user_id, kit_id, price)
# --- Adicione no final do db.py ---

def get_all_user_ids():
    """Retorna uma lista com o ID de TODOS os usuários que já usaram o bot."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM users")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def init_subscription_prices():
    """Cria tabela de preços de planos (VIP)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS sub_prices (
        days INTEGER PRIMARY KEY,
        price REAL
    )
    """)
    # Preços padrão iniciais (caso não existam)
    c.execute("INSERT OR IGNORE INTO sub_prices (days, price) VALUES (7, 10.0)")
    c.execute("INSERT OR IGNORE INTO sub_prices (days, price) VALUES (30, 25.0)")
    c.execute("INSERT OR IGNORE INTO sub_prices (days, price) VALUES (365, 100.0)")
    conn.commit()
    conn.close()

def set_plan_price(days, price):
    """Define o preço de um plano de X dias."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO sub_prices (days, price) VALUES (?, ?)", (days, price))
    conn.commit()
    conn.close()

def get_plan_price(days):
    """Pega o preço de um plano."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT price FROM sub_prices WHERE days=?", (days,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0.0

def get_all_plans():
    """Retorna todos os planos disponíveis para montar o menu."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT days, price FROM sub_prices ORDER BY days ASC")
    rows = c.fetchall()
    conn.close()
    return rows
# --- Adicione no final do db.py ---

def init_payments_table():
    """Cria tabela para salvar pedidos de pagamento pendentes."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        track_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_payment(track_id, user_id, amount):
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # We use str(track_id) to guarantee it saves as Text
    c.execute("INSERT OR REPLACE INTO payments (track_id, user_id, amount, created_at) VALUES (?, ?, ?, ?)", 
              (str(track_id), user_id, amount, now))
    conn.commit()
    conn.close()

def get_pending_payment(user_id):
    """Pega o último pagamento pendente do usuário."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT track_id, amount FROM payments WHERE user_id=? AND status='Pending' ORDER BY created_at DESC LIMIT 1", (user_id,))
    res = c.fetchone()
    conn.close()
    return {'track_id': res[0], 'amount': res[1]} if res else None

def mark_payment_completed(track_id):
    """Marca como pago para não cobrar 2x e remove da lista de pendentes."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='Completed' WHERE track_id=?", (track_id,))
    conn.commit()
    conn.close()
    
# --- ADD THIS TO THE END OF db.py ---

def get_payment_by_track_id(track_id):
    """Finds a specific payment by its ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, amount, status FROM payments WHERE track_id=?", (track_id,))
    res = c.fetchone()
    conn.close()
    if res:
        return {'user_id': res[0], 'amount': res[1], 'status': res[2]}
    return None

# ⚠️ IMPORTANTE: 
# Suba no início do db.py e adicione init_payments_table() dentro da função init_db()!
# ⚠️ IMPORTANTE: 
# Lembre-se de chamar init_subscription_prices() dentro da função init_db() lá no começo!
# No final do db.py

# ⚠️ IMPORTANTE: 
# Chame init_prices_table() dentro da função init_db() lá no começo do arquivo!