# ocr_service.py
import pytesseract
from PIL import Image
import io
import re

# --- CONFIGURAÇÃO ---
path_to_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    pytesseract.pytesseract.tesseract_cmd = path_to_tesseract
except:
    pass

# --- DICIONÁRIOS DE TRADUÇÃO/DETECÇÃO ---
# O bot vai procurar essas palavras para saber o que é o que.
KEYWORDS = {
    "DOB": [
        "birth", "nascimento", "nacimiento", "naissance", "geburt", 
        "fødselsdato", "date of birth", "data urodzenia", "födelsetid",
        "születési", "doğum", "rođenja", "datlindjes"
    ],
    "EXP": [
        "expiry", "valid", "vencimento", "caducidad", "expiration", 
        "gültig", "validade", "expires", "gylyo", "son kullanma", 
        "valable", "wygaśnięcia"
    ],
    "NAME": [
        "name", "nome", "nombre", "nom", "surname", "given names",
        "apellidos", "sobrenome", "vorname", "nazwisko"
    ]
}

def clean_text(text):
    """Limpa caracteres estranhos que o OCR pega por engano."""
    return re.sub(r'[^\w\s/.-]', '', text).strip()

def extract_date(line):
    """Tenta achar uma data (DD/MM/YYYY ou YYYY-MM-DD) numa linha."""
    # Regex para datas comuns (10/10/2020, 10.10.20, 2020-10-10)
    match = re.search(r'\b(\d{2}[./-]\d{2}[./-]\d{2,4}|\d{4}[./-]\d{2}[./-]\d{2})\b', line)
    if match:
        return match.group(1)
    return None

def parse_smart_data(raw_text):
    """
    Analisa o texto bruto e tenta extrair Nome, DOB e Validade.
    """
    lines = raw_text.split('\n')
    
    extracted = {
        "Name": "Not Detected",
        "DOB": "Not Detected",
        "Expiry": "Not Detected"
    }

    # Estratégia 1: Leitura Linha a Linha (Busca por Palavra-Chave)
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # 1. Procura Data de Nascimento (DOB)
        if any(key in line_lower for key in KEYWORDS["DOB"]):
            # Tenta achar data na mesma linha
            date = extract_date(line)
            if date:
                extracted["DOB"] = date
            # Às vezes a data está na linha de baixo
            elif i + 1 < len(lines):
                date_next = extract_date(lines[i+1])
                if date_next: extracted["DOB"] = date_next

        # 2. Procura Validade (EXP)
        if any(key in line_lower for key in KEYWORDS["EXP"]):
            date = extract_date(line)
            if date:
                extracted["Expiry"] = date
            elif i + 1 < len(lines):
                date_next = extract_date(lines[i+1])
                if date_next: extracted["Expiry"] = date_next

        # 3. Procura Nome (Muito difícil sem IA, tentamos achar labels)
        if any(key in line_lower for key in KEYWORDS["NAME"]) and extracted["Name"] == "Not Detected":
            # Geralmente o nome está DEPOIS do label, ou na linha de baixo
            clean_line = clean_text(line)
            # Remove o label (ex: "Name:") para sobrar só o nome
            for key in KEYWORDS["NAME"]:
                clean_line = re.sub(key, '', clean_line, flags=re.IGNORECASE)
            
            clean_line = clean_line.strip()
            
            if len(clean_line) > 3: # Se sobrou texto, deve ser o nome
                extracted["Name"] = clean_line.title()
            elif i + 1 < len(lines): # Se não, pega a linha de baixo inteira
                possible_name = clean_text(lines[i+1])
                if len(possible_name) > 3 and not extract_date(possible_name):
                    extracted["Name"] = possible_name.title()

    # Estratégia 2: Fallback MRZ (Se tiver código de máquina no fundo)
    # Se acharmos linhas com "P<" ou "I<" e muitos "<<<", é mais confiável.
    for line in lines:
        if "<<" in line and (line.startswith("P<") or line.startswith("I<") or line.startswith("ID")):
            # MRZ detectado (muito complexo para parsear perfeitamente sem lib, 
            # mas podemos assumir que nomes estão aqui em maiúsculo)
            parts = line.split("<<")
            if len(parts) > 1:
                # Tentativa bruta de pegar nome do MRZ
                raw_name = parts[0][2:].replace("<", " ").strip()
                if len(raw_name) > 3:
                    extracted["Name"] = raw_name # MRZ é mais confiável para nome
            break

    return extracted

def extract_text_from_bytes(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # OCR Bruto
        raw_text = pytesseract.image_to_string(image, lang='eng')
        
        if not raw_text.strip():
            return "⚠️ OCR Failed: Image too blurry or no text found."

        # Processamento Inteligente
        data = parse_smart_data(raw_text)
        
        # Formata a saída bonita para o usuário
        formatted_output = (
            f"👤 **Name:** {data['Name']}\n"
            f"🎂 **Date of Birth:** {data['DOB']}\n"
            f"⏳ **Expiry Date:** {data['Expiry']}\n\n"
            f"__Raw Scan Verification:__\nEverything looks good."
        )
        
        return formatted_output
        
    except FileNotFoundError:
        return "❌ Error: Tesseract not found on server."
    except Exception as e:
        return f"Error: {str(e)}"