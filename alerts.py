"""
Envoi d'une alerte simple via un webhook Discord.

Pour l'utiliser :
1. Dans un serveur Discord (le vôtre, même un serveur perso avec juste vous
   dedans), allez dans les paramètres d'un salon > Intégrations > Webhooks
   > Nouveau webhook, et copiez son URL.
2. Mettez cette URL dans une variable d'environnement DISCORD_WEBHOOK_URL
   (en local ET sur le cron job Render).

Si la variable n'est pas définie, send_alert() n'envoie rien mais n'empêche
pas le reste du script de continuer (le scraping ne doit jamais planter à
cause d'une alerte qui ne part pas).
"""

import os
import requests

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def send_alert(message: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        print(f"[ALERTE non envoyée, DISCORD_WEBHOOK_URL absent] {message}")
        return

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except requests.RequestException as e:
        print(f"Échec de l'envoi de l'alerte Discord : {e}")
