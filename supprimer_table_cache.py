"""
Supprime la table cached_fares pour qu'elle soit recréée proprement avec
toutes les colonnes actuelles (variante, escales) au prochain init_db.py.

Sans risque : cette table ne contient que des prix mis en cache, rien
d'important à perdre — le scraper la remplit à nouveau à son prochain passage.

Lancer avec (DATABASE_URL défini) :
    python supprimer_table_cache.py
"""

from database import engine
from sqlalchemy import text

with engine.connect() as connexion:
    connexion.execute(text("DROP TABLE IF EXISTS cached_fares;"))
    connexion.commit()

print("Table cached_fares supprimée. Lancez maintenant : python init_db.py")
