# ocr.py V2 - Mais inteligente com Regex
import easyocr
import logging
import re
from datetime import datetime

# Carrega o modelo (mantém igual)
print("⏳ Loading OCR AI Model...")
reader = easyocr.Reader(['en', 'pt', 'es', 'fr', 'de', 'it'], gpu=False)
print("✅ OCR Model Loaded!")

def parse_dates(text):
    """
    Caça datas em formatos variados (DD/MM/YYYY, DD MMM YYYY, etc).
    """
    # Regex 1: Formato Numérico (12/05/1990 ou 12-05-90 ou 12.05.1990) - Aceita espaços
    regex_numeric = r'\b(\d{1,2}[\s./-]+\d{1,2}[\s./-]+\d{2,4})\b'
    
    # Regex 2: Formato Texto (12 JAN 1990 ou 12 FEV 90)
    regex_text = r'\b(\d{1,2}\s+[A-Za-z]{3,}\s+\d{2,4})\b'
    
    found_numeric = re.findall(regex_numeric, text)
    found_text = re.findall(regex_text, text, re.IGNORECASE)
    
    all_dates = found_numeric + found_text
    
    dob = "Not Found"
    expiry = "Not Found"
    current_year = datetime.now().year
    
    for d in all_dates:
        # Tenta extrair apenas o ano (últimos 4 ou 2 dígitos)
        try:
            # Remove caracteres não numéricos para achar o ano
            clean_d = re.sub(r'[^0-9]', '', d)
            if len(clean_d) >= 4:
                year = int(clean_d[-4:])
                # Correção para anos de 2 dígitos (ex: 90 -> 1990, 25 -> 2025)
                if year < 100: 
                    year += 2000 if year < 50 else 1900
                
                # Lógica de classificação
                if 1900 < year < (current_year - 12):
                    dob = d # Provável Nascimento
                elif year >= current_year:
                    expiry = d # Provável Validade
        except:
            continue
            
    return dob, expiry

def extract_specific_fields(text):
    """
    Usa 'Âncoras' para achar Nome e Sobrenome.
    Procura por 'Surname', 'Nom' e pega a palavra seguinte.
    """
    guessed_name = "Not Detected"
    
    # 1. Tenta achar SOBRENOME (Surname/Nom/Apellidos)
    # Procura a palavra chave e pega a próxima palavra em MAIÚSCULO
    surname_match = re.search(r'(?:Surname|Nom|Apellidos|Sobrenome)\W+([A-Z]+)', text, re.IGNORECASE)
    surname = surname_match.group(1) if surname_match else ""
    
    # 2. Tenta achar NOME (Given names/Prenoms/Nombres)
    name_match = re.search(r'(?:Given names|Prenoms|Nombres|Nome)\W+([A-Z]+)', text, re.IGNORECASE)
    name = name_match.group(1) if name_match else ""
    
    if surname or name:
        guessed_name = f"{name} {surname}".strip()
    else:
        # PLANO B: Se não achou âncoras, tenta pegar a linha mais promissora
        # (Linhas curtas, só letras, sem palavras proibidas)
        lines = text.split('\n')
        blacklist = ["PASSPORT", "TYPE", "CODE", "ISSUING", "UNITED", "STATES", "AMERICA", "REPUBLIC"]
        for line in lines:
            clean = line.strip().upper()
            if len(clean) > 3 and not any(x in clean for x in blacklist) and not any(c.isdigit() for c in clean):
                guessed_name = clean
                break
                
    return guessed_name

# No final do ocr.py

def extract_text_from_bytes(image_bytes):
    try:
        # Pega o texto corrido
        result_list = reader.readtext(image_bytes, detail=0)
        full_text_blob = " ".join(result_list)
        
        # 1. Datas
        dob, expiry = parse_dates(full_text_blob)
        
        # 2. Nomes
        guessed_name = extract_specific_fields(full_text_blob)
        
        # RETORNA UM DICIONÁRIO (DADOS PUROS)
        # Isso permite que o bot verifique: if result['dob'] != "Not Found"...
        return {
            "name": guessed_name,
            "dob": dob,
            "expiry": expiry,
            "raw_text": full_text_blob[:200] # Backup
        }

    except Exception as e:
        logging.error(f"OCR Error: {e}")
        return None # Retorna None se der erro grave
