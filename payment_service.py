
Folder highlights
Project centers on a Python-based Telegram bot for document download, featuring OCR scanning, payment processing, and Drive synchronization.

# payment_service.py
import httpx
import json
import os # Melhor usar variáveis de ambiente

# ⚠️ IMPORTANTE: Use variável de ambiente ou troque a chave e não mostre a ninguém
OXAPAY_KEY = "0RWRPM-SYDZQP-CQ2NBK-EIJB7N" 

BASE_URL = "https://api.oxapay.com/merchants"

async def create_payment(user_id, amount_usd):
    url = f"{BASE_URL}/request"
    
    data = {
        "merchant": OXAPAY_KEY,
        "amount": amount_usd,
        "currency": "USDT",
        "lifeTime": 30,
        "feePaidByPayer": 0,
        "underPaidCover": 2.0,
        "callbackUrl": "", 
        "description": f"User {user_id} Topup",
        "orderId": f"ORDER_{user_id}_{int(amount_usd)}"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=10.0) # Timeout adicionado
            result = response.json()
            
            if result.get("result") == 100:
                return {
                    "pay_link": result.get("payLink"),
                    "track_id": result.get("trackId")
                }
            else:
                print(f"Erro OxaPay (Create): {result}")
                return None
        except Exception as e:
            print(f"Erro Conexão Payment: {e}")
            return None

async def check_payment_status(track_id):
    """
    Verifica se o pagamento foi concluído.
    Retorna: 'Paid', 'Confirming', 'Waiting', 'Expired' ou 'Error'
    """
    url = f"{BASE_URL}/inquiry"
    
    data = {
        "merchant": OXAPAY_KEY,
        "trackId": track_id
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=10.0)
            result = response.json()
            
            # 100 = Sucesso na requisição
            if result.get("result") == 100:
                status = result.get("status")
                # Vamos normalizar o status para evitar erros de maiúscula/minúscula
                return status 
            
            print(f"Erro OxaPay (Check): {result}")
            return "Error"
        except Exception as e:
            print(f"Erro Conexão Check: {e}")
            return "Error"
