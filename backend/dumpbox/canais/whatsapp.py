"""WhatsApp: mesmo núcleo do Telegram (base.tratar), dois provedores com o mesmo contrato.
- Evolution API (Docker local, pareia por QR; NÃO oficial, use um número separado): DUMPBOX_ZAP=evolution
- Cloud API da Meta (oficial, webhook público): DUMPBOX_ZAP=cloud
Webhook: POST /api/canais/whatsapp. Permitidos: DUMPBOX_ZAP_PERMITIDOS (números, vírgula, só dígitos)."""
import hashlib
import hmac
import os

import httpx

from . import base


class Evolution:
    """Evento messages.upsert da Evolution. Autentica pelo header `x-dumpbox-segredo` (configurado no webhook dela)."""

    def __init__(self, url: str, instancia: str, chave: str, segredo: str, cliente: httpx.Client | None = None):
        self.url, self.instancia, self.chave, self.segredo = url.rstrip("/"), instancia, chave, segredo
        self.http = cliente or httpx.Client(timeout=15)

    def autentico(self, headers, corpo: bytes) -> bool:
        return bool(self.segredo) and hmac.compare_digest(headers.get("x-dumpbox-segredo", ""), self.segredo)

    def receber(self, payload: dict) -> list[tuple[str, str, str]]:
        if payload.get("event") not in ("messages.upsert", "MESSAGES_UPSERT"):
            return []
        d = payload.get("data") or {}
        k, m = d.get("key") or {}, d.get("message") or {}
        if k.get("fromMe") or not str(k.get("remoteJid", "")).endswith("@s.whatsapp.net"):
            return []  # fromMe: o bot leria a própria resposta (loop); @g.us = grupo, fora de escopo
        texto = m.get("conversation") or (m.get("extendedTextMessage") or {}).get("text")
        numero = k["remoteJid"].split("@")[0]
        return [(numero, k.get("id", ""), texto if texto else "\0midia")]

    def enviar(self, numero: str, texto: str) -> None:
        self.http.post(f"{self.url}/message/sendText/{self.instancia}", headers={"apikey": self.chave},
                       json={"number": numero, "text": texto[:4000]}).raise_for_status()


class CloudAPI:
    """Webhook da Meta: assinatura X-Hub-Signature-256 = HMAC-SHA256(app secret, corpo cru)."""

    def __init__(self, token: str, telefone_id: str, app_secret: str, verificar: str, cliente: httpx.Client | None = None):
        self.token, self.telefone_id, self.app_secret, self.verificar = token, telefone_id, app_secret, verificar
        self.http = cliente or httpx.Client(timeout=15)

    def autentico(self, headers, corpo: bytes) -> bool:
        esperado = "sha256=" + hmac.new(self.app_secret.encode(), corpo, hashlib.sha256).hexdigest()
        return bool(self.app_secret) and hmac.compare_digest(headers.get("x-hub-signature-256", ""), esperado)

    def receber(self, payload: dict) -> list[tuple[str, str, str]]:
        saida = []
        for e in payload.get("entry") or []:
            for ch in e.get("changes") or []:
                for m in (ch.get("value") or {}).get("messages") or []:
                    texto = (m.get("text") or {}).get("body") if m.get("type") == "text" else "\0midia"
                    saida.append((m.get("from", ""), m.get("id", ""), texto or ""))
        return saida

    def enviar(self, numero: str, texto: str) -> None:
        # ponytail: texto livre só vale na janela de 24 h; lembrete fora dela precisa de template aprovado na Meta
        self.http.post(f"https://graph.facebook.com/v20.0/{self.telefone_id}/messages",
                       headers={"Authorization": f"Bearer {self.token}"},
                       json={"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto[:4000]}}).raise_for_status()


def provedor():
    e = os.getenv
    if e("DUMPBOX_ZAP") == "evolution":
        return Evolution(e("DUMPBOX_ZAP_URL", "http://127.0.0.1:8080"), e("DUMPBOX_ZAP_INSTANCIA", "dumpbox"),
                         e("DUMPBOX_ZAP_CHAVE", ""), e("DUMPBOX_ZAP_SEGREDO", ""))
    if e("DUMPBOX_ZAP") == "cloud":
        return CloudAPI(e("DUMPBOX_ZAP_TOKEN", ""), e("DUMPBOX_ZAP_TELEFONE_ID", ""), e("DUMPBOX_ZAP_APP_SECRET", ""),
                        e("DUMPBOX_ZAP_VERIFICAR", ""))
    return None


def permitidos() -> set[str]:
    return {"".join(ch for ch in p if ch.isdigit()) for p in os.getenv("DUMPBOX_ZAP_PERMITIDOS", "").split(",") if p.strip()}


def tratar_todas(c, prov, payload: dict, quem: set[str]) -> list[tuple[str, str]]:
    """Mensagens do webhook -> respostas (numero, texto) a enviar. Número fora da lista: ignora sem responder."""
    saida = []
    for numero, msg_id, texto in prov.receber(payload):
        if numero not in quem:
            continue
        resp = "Só texto por enquanto." if texto == "\0midia" else base.tratar(c, "whatsapp", numero, msg_id, texto)
        if resp:
            saida.append((numero, resp))
    return saida


def aviso(texto: str) -> None:
    """Destino dos lembretes (lembretes.avisar)."""
    prov = provedor()
    for n in permitidos():
        prov.enviar(n, texto)
