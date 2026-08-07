from __future__ import annotations

import argparse
import os
import time
import requests

from config import DB_PATH
from db import init_db, mark_notified, pending_alert_matches
from services.ingestion import ingest_configured_feeds


def send_ntfy(alert: dict, listing: dict) -> bool:
    topic = alert.get("ntfy_topic") or os.getenv("HABITUA_NTFY_TOPIC", "")
    if not topic:
        print(f"[aviso] O alerta {alert['id']} não tem tópico ntfy; resultado não notificado.")
        return False
    base = os.getenv("HABITUA_NTFY_BASE", "https://ntfy.sh").rstrip("/")
    target = f"{base}/{topic}"
    price = f"{float(listing['price']):,.0f} €".replace(",", " ")
    suffix = "/mês" if listing["transaction"] == "Arrendar" else ""
    location = ", ".join(filter(None, [listing.get("municipality"), listing.get("district")]))
    headers = {
        "Title": f"Habitua · {alert['name']}",
        "Priority": "high",
        "Tags": "house,magnifying_glass_tilted_left",
    }
    if listing.get("url"):
        headers["Click"] = listing["url"]
    response = requests.post(
        target,
        data=f"{listing['title']}\n{price}{suffix} · {location}\nFonte: {listing['source']}".encode("utf-8"),
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    return True


def check_once() -> None:
    processed, messages = ingest_configured_feeds()
    print(f"Feeds: {processed} anúncios processados")
    for message in messages:
        print(f"  - {message}")
    matches = pending_alert_matches()
    print(f"Alertas: {len(matches)} novo(s) resultado(s)")
    for alert, listing in matches:
        try:
            if send_ntfy(alert, listing):
                mark_notified(alert["id"], listing["uid"])
                print(f"  - enviado: {listing['title']}")
        except requests.RequestException as exc:
            print(f"  - falhou: {listing['title']} ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza feeds Habitua e envia alertas ntfy.")
    parser.add_argument("--interval", type=int, default=300, help="Segundos entre verificações (mínimo: 60).")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma verificação.")
    args = parser.parse_args()
    init_db(DB_PATH)
    while True:
        check_once()
        if args.once:
            return
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    main()
