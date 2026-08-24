"""
Planning hebdomadaire des vols directs au départ de Nouméa-La Tontouta,
déduit manuellement d'UNE semaine d'observation (24-30 août 2026) sur le
site de la CCI Nouvelle-Calédonie Aéroports (recherche de vol).

⚠️ À rafraîchir périodiquement : les compagnies ajustent parfois leurs
fréquences selon la saison. Une seule semaine d'observation ne garantit
pas que ce planning reste exact toute l'année.

Jours au format court français : Lun, Mar, Mer, Jeu, Ven, Sam, Dim.
"""

ROUTE_SCHEDULE = {
    "BNE": {"jours": ["Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"], "compagnies": "Aircalin, Qantas"},
    "SYD": {"jours": ["Mar", "Mer", "Jeu", "Sam", "Dim"], "compagnies": "Aircalin, Qantas"},
    "AKL": {"jours": ["Mer", "Ven", "Dim"], "compagnies": "Aircalin (codeshare Air New Zealand)"},
    "SIN": {"jours": ["Mar", "Ven", "Dim"], "compagnies": "Aircalin"},
    "BKK": {"jours": ["Lun", "Sam"], "compagnies": "Aircalin"},
    "VLI": {"jours": ["Lun", "Jeu"], "compagnies": "Air Calédonie"},
    "WLS": {"jours": ["Lun", "Jeu"], "compagnies": "Aircalin"},
    "NAN": {"jours": ["Sam"], "compagnies": "Aircalin"},
    "PPT": {"jours": ["Ven"], "compagnies": "Aircalin"},
}


def obtenir_planning(destination: str) -> dict | None:
    """Renvoie {"jours": [...], "compagnies": "..."} pour une destination, ou None si inconnue."""
    return ROUTE_SCHEDULE.get(destination.upper())
