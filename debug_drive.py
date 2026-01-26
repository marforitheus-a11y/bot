from googleapiclient.discovery import build
from google.oauth2 import service_account
from config import GOOGLE_CREDENTIALS, DRIVE_FOLDER_ID

def test_connection():
    print(f"📂 Checking Folder ID: {DRIVE_FOLDER_ID}")
    
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)

    # 1. Check if bot can access the folder itself
    try:
        folder = service.files().get(fileId=DRIVE_FOLDER_ID).execute()
        print(f"✅ Success! Connected to folder: '{folder.get('name')}'")
    except Exception as e:
        print(f"❌ ERROR: Bot cannot see the folder.\nReason: {e}")
        return

    # 2. List ALL files inside (No name filters)
    print("\n🔎 Listing first 10 files inside:")
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents",
        pageSize=10,
        fields="files(id, name, mimeType)"
    ).execute()
    
    files = results.get("files", [])

    if not files:
        print("⚠️ The folder appears EMPTY to the bot.")
    else:
        for f in files:
            print(f"  - Found: {f['name']} (Type: {f['mimeType']})")

if __name__ == "__main__":
    test_connection()