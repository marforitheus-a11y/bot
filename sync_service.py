# sync_service.py
from googleapiclient.discovery import build
from google.oauth2 import service_account
from config import GOOGLE_CREDENTIALS, DRIVE_FOLDER_ID
import db

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def get_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

def sync_drive_to_db(status_callback=None):
    """
    Função pesada que lê o Drive inteiro e salva no SQLite.
    status_callback: função opcional para enviar mensagens ao Telegram avisando o progresso.
    """
    service = get_service()
    
    print("🚀 Iniciando sincronização...")
    if status_callback: status_callback("🔄 **Sync started...** Clearing old cache.")
    
    # 1. Limpa o cache antigo para evitar duplicatas ou itens deletados
    db.clear_cache()
    
    # 2. Fila de pastas para processar (Começa pela Raiz)
    # Estrutura: (id_da_pasta, nome_da_pasta)
    folders_to_scan = [(DRIVE_FOLDER_ID, "ROOT")]
    
    total_folders = 0
    total_files = 0
    
    while folders_to_scan:
        current_id, current_name = folders_to_scan.pop(0)
        
        # Busca tudo que tem dentro dessa pasta
        q = f"'{current_id}' in parents and trashed = false"
        results = service.files().list(
            q=q, 
            fields="files(id, name, mimeType)", 
            pageSize=1000
        ).execute()
        
        items = results.get("files", [])
        
        for item in items:
            is_folder = item['mimeType'] == 'application/vnd.google-apps.folder'
            node_type = 'folder' if is_folder else 'file'
            
            # Salva no Banco
            db.insert_cache_item(
                item_id=item['id'],
                name=item['name'],
                parent_id=current_id,
                node_type=node_type,
                mime_type=item['mimeType']
            )
            
            # Se for pasta, adiciona na fila para ser escaneada depois
            if is_folder:
                folders_to_scan.append((item['id'], item['name']))
                total_folders += 1
            else:
                total_files += 1
        
        print(f"Processando: {current_name} | Fila: {len(folders_to_scan)}")
    
    msg = f"✅ **Sync Complete!**\n📂 Folders: {total_folders}\n📄 Files: {total_files}"
    print(msg)
    if status_callback: status_callback(msg)