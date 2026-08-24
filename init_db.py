"""
Lance ce script une seule fois pour créer les tables dans votre base
PostgreSQL (en local pour tester, ou une fois sur Render en production) :

    python init_db.py
"""

from database import engine, Base
import models  # nécessaire pour que SQLAlchemy "voie" le modèle CachedFare

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Tables créées avec succès.")
