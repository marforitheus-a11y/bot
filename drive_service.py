from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from config import GOOGLE_CREDENTIALS, DRIVE_FOLDER_ID
import io
import random

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def get_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

service = get_service()

def find_folder_by_name(parent_id, folder_name):
    """Finds a specific folder (case-insensitive) inside the root folder."""
    # We use contains to be safer with casing, or exact match if preferred
    q = f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = service.files().list(q=q, fields="files(id, name)").execute()
        files = results.get("files", [])
        return files[0] if files else None
    except:
        return None

def list_subfolders(parent_id):
    """Lists all folders inside a parent folder (e.g., Types inside Country, or States inside Type)."""
    q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        # Increased page size to handle 50 states if necessary
        results = service.files().list(q=q, fields="files(id, name)", pageSize=100, orderBy="name").execute()
        return results.get("files", [])
    except:
        return []

def list_kits_in_folder(folder_id):
    """Lists all KIT FOLDERS inside a folder."""
    q = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = service.files().list(q=q, fields="files(id, name)", pageSize=100).execute()
        return results.get("files", [])
    except:
        return []

def get_random_kit_recursive(type_folder_id):
    """
    USA SPECIAL: Goes into every subfolder (State) of the Type folder,
    collects ALL kits found, and picks one random one.
    """
    all_kits = []
    
    # 1. Get all State folders
    state_folders = list_subfolders(type_folder_id)
    
    # 2. Loop through every state and get their kits
    for state in state_folders:
        kits = list_kits_in_folder(state['id'])
        all_kits.extend(kits)
        
    return all_kits

def get_files_in_kit(kit_folder_id):
    """Gets all images inside a specific Kit Folder."""
    q = f"'{kit_folder_id}' in parents and mimeType contains 'image/' and trashed = false"
    try:
        results = service.files().list(q=q, fields="files(id, name)", pageSize=20).execute()
        return results.get("files", [])
    except:
        return []

def download_file_bytes(file_id):
    """Downloads file content to RAM."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        print(f"Download error: {e}")
        return None