"""
Script to configure Evolution API and retrieve WhatsApp QR Code.
"""
import base64
import os
import sys
import time
from pathlib import Path

# Force UTF-8 for console output on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx

from app.config import get_settings

settings = get_settings()

BASE_URL = os.getenv("EVOLUTION_HOST_URL", "http://localhost:8080")
API_KEY = settings.EVOLUTION_API_KEY
INSTANCE_NAME = settings.EVOLUTION_INSTANCE_NAME
WEBHOOK_URL = "http://api:8000/webhook/evolution"

HEADERS = {
    "apikey": API_KEY,
    "Content-Type": "application/json",
}


def wait_for_evolution(max_attempts=30):
    print(f"⏳ Conectando ao Evolution API em {BASE_URL}...")
    for i in range(max_attempts):
        try:
            r = httpx.get(f"{BASE_URL}/", timeout=3.0)
            if r.status_code == 200:
                print("✅ Evolution API está online e pronta!")
                return True
        except Exception:
            pass
        time.sleep(2)
    print("❌ Tempo esgotado aguardando o Evolution API.")
    return False


def create_instance():
    print(f"⚙️ Verificando/criando instância '{INSTANCE_NAME}'...")
    url = f"{BASE_URL}/instance/create"
    payload = {
        "instanceName": INSTANCE_NAME,
        "token": API_KEY,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
    }
    try:
        r = httpx.post(url, json=payload, headers=HEADERS, timeout=10.0)
        if r.status_code in (200, 201):
            print(f"✅ Instância '{INSTANCE_NAME}' criada com sucesso!")
        elif r.status_code == 403 or "already in use" in r.text or "already exists" in r.text:
            print(f"ℹ️ Instância '{INSTANCE_NAME}' já existe.")
        else:
            print(f"⚠️ Resposta na criação da instância [{r.status_code}]: {r.text}")
    except Exception as exc:
        print(f"❌ Erro ao criar instância: {exc}")


def set_webhook():
    print(f"🔗 Configurando Webhook para '{WEBHOOK_URL}'...")
    url = f"{BASE_URL}/webhook/set/{INSTANCE_NAME}"
    payload = {
        "webhook": {
            "enabled": True,
            "url": WEBHOOK_URL,
            "byEvents": False,
            "base64": False,
            "events": [
                "MESSAGES_UPSERT",
            ],
        }
    }
    try:
        r = httpx.post(url, json=payload, headers=HEADERS, timeout=10.0)
        if r.status_code in (200, 201):
            print("✅ Webhook configurado com sucesso!")
        else:
            print(f"⚠️ Resposta na configuração do webhook [{r.status_code}]: {r.text}")
    except Exception as exc:
        print(f"❌ Erro ao configurar webhook: {exc}")


def get_qrcode():
    print("📲 Solicitando QR Code do WhatsApp...")
    url = f"{BASE_URL}/instance/connect/{INSTANCE_NAME}"
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15.0)
        data = r.json()
        
        # Check connection state
        state = data.get("instance", {}).get("state") or data.get("state")
        if state == "open":
            print("🎉 WhatsApp já está conectado e pronto para uso!")
            return

        base64_img = data.get("base64")
        if not base64_img:
            # Fallback if inside qrcode object
            qrcode_obj = data.get("qrcode") or {}
            base64_img = qrcode_obj.get("base64")

        if base64_img:
            # Remove header if present
            if "," in base64_img:
                base64_img = base64_img.split(",", 1)[1]
            img_bytes = base64.b64decode(base64_img)
            qr_path = Path("qrcode.png").resolve()
            with open(qr_path, "wb") as f:
                f.write(img_bytes)
            print(f"\n📸 QR Code gerado e salvo com sucesso em:")
            print(f"👉 {qr_path}")
            print("\nAbra a imagem acima e escaneie com seu WhatsApp em: Aparelhos conectados > Conectar um aparelho.")
        else:
            print(f"ℹ️ Status da conexão: {data}")
    except Exception as exc:
        print(f"❌ Erro ao buscar QR Code: {exc}")


def get_pairing_code(phone_number: str):
    clean_number = "".join(filter(str.isdigit, phone_number))
    if not clean_number.startswith("55") and len(clean_number) in (10, 11):
        clean_number = "55" + clean_number
    print(f"\n📲 Solicitando Código de Pareamento para o número +{clean_number}...")
    url = f"{BASE_URL}/instance/connect/{INSTANCE_NAME}?number={clean_number}"
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15.0)
        data = r.json()
        code = data.get("pairingCode") or data.get("code")
        if code:
            print("\n" + "=" * 45)
            print(f"🔢 CÓDIGO DE PAREAMENTO DO WHATSAPP: {code}")
            print("=" * 45)
            print("\nPasso a passo no seu celular:")
            print("1. Abra o WhatsApp > Aparelhos conectados > Conectar um aparelho.")
            print("2. Clique na opção abaixo: 'Conectar com número de telefone' (ou 'Link with phone number').")
            print(f"3. Digite o código: {code}\n")
            return code
        else:
            print(f"ℹ️ Resposta da API: {data}")
    except Exception as exc:
        print(f"❌ Erro ao buscar código de pareamento: {exc}")


def main():
    if not wait_for_evolution():
        sys.exit(1)
    create_instance()
    set_webhook()
    if len(sys.argv) > 1 and sys.argv[1].strip():
        get_pairing_code(sys.argv[1].strip())
    else:
        get_qrcode()


if __name__ == "__main__":
    main()
