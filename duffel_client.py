"""
Client pour l'API Duffel (Qantas, Air New Zealand, Fiji Airways).

Pour l'instant, cette fonction renvoie une liste vide : le temps que vous
créiez un compte Duffel et récupériez une clé API (variable d'environnement
DUFFEL_API_KEY), le site continuera de fonctionner normalement avec
uniquement les prix Aircalin.

Quand vous aurez votre clé, on remplira get_duffel_offers() ensemble pour
appeler réellement l'API Duffel et convertir sa réponse au même format que
ce qu'attend results.html.
"""

import os

DUFFEL_API_KEY = os.getenv("DUFFEL_API_KEY")


def get_duffel_offers(origin: str, destination: str, departure_date: str, return_date: str | None) -> list[dict]:
    """
    Doit renvoyer une liste de dicts au même format que ceux construits
    dans app.py pour Aircalin, ex:
    [{"airline": "Qantas Airways", "prix_xpf_num": 52000, "price": "52 000 XPF", ...}]

    Tant que DUFFEL_API_KEY n'est pas défini, on ne fait aucun appel externe
    et on renvoie simplement une liste vide.
    """
    if not DUFFEL_API_KEY:
        return []

    # TODO (à faire ensemble une fois la clé API en main) :
    # 1. Appeler POST https://api.duffel.com/air/offer_requests avec origin/destination/dates
    # 2. Récupérer les offers renvoyées
    # 3. Les convertir au même format que les résultats Aircalin ci-dessous
    return []
