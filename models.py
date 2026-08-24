"""
Une seule table suffit pour l'instant : cached_fares.

Elle sert à deux choses différentes selon la ligne :
- Les prix Aircalin : écrits par le cron horaire (scraping), lus par l'API.
- Les prix Duffel (Qantas, Air NZ, Fiji Airways) : écrits par l'API elle-même
  juste après un appel à Duffel, pour servir de cache de 10-15 min et éviter
  de repayer Duffel à chaque recherche sur la même route.

La colonne "source" permet de distinguer les deux, car elles n'ont pas la
même logique de fraîcheur (TTL) :
- source="scrape"  -> valable jusqu'au prochain passage du cron (≈1h)
- source="duffel"  -> valable 10-15 min seulement, à vérifier via fetched_at
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class CachedFare(Base):
    __tablename__ = "cached_fares"

    id = Column(Integer, primary_key=True, index=True)

    # Ex : "NOU" -> "SYD"
    origin = Column(String(3), nullable=False, index=True)
    destination = Column(String(3), nullable=False, index=True)

    # "oneway" ou "roundtrip"
    trip_type = Column(String(10), nullable=False)

    # Code IATA de la compagnie : "SB" (Aircalin), "QF" (Qantas), "NZ", "FJ"...
    airline_code = Column(String(3), nullable=False)

    # "direct" ou "escale" — permet de garder DEUX lignes pour la même
    # route/compagnie : le meilleur direct ET la meilleure option avec
    # escale, quand cette dernière est moins chère que le direct.
    variante = Column(String(10), nullable=False, default="direct")

    # Prix en XPF (nombre entier suffit, pas de centimes en XPF)
    price = Column(Numeric(10, 0), nullable=False)

    # Nombre d'escales de cette variante (0 pour "direct", 1+ pour "escale").
    escales = Column(Integer, nullable=False, default=0)

    # "scrape" (Aircalin) ou "duffel" (compagnies partenaires)
    source = Column(String(10), nullable=False)

    # Dernière mise à jour de cette ligne — sert à calculer la fraîcheur
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Une ligne par route + type de vol + compagnie + variante
        # (jusqu'à 2 lignes par compagnie : "direct" et "escale")
        UniqueConstraint("origin", "destination", "trip_type", "airline_code", "variante", name="uq_fare_route"),
    )


class PriceCalibration(Base):
    """
    Une ligne = une vérification manuelle : "à telle date, GoVoyages
    affichait X XPF pour cette route, et le vrai prix sur aircalin.nc
    était Y XPF". Sert à calculer un pourcentage moyen d'écart entre les
    deux, pour corriger le prix affiché sur le site au fil du temps.

    Alimentée par le script ajouter_calibration.py, jamais par le cron.
    """

    __tablename__ = "price_calibrations"

    id = Column(Integer, primary_key=True, index=True)

    origin = Column(String(3), nullable=False)
    destination = Column(String(3), nullable=False)
    trip_type = Column(String(10), nullable=False)

    prix_govoyages_xpf = Column(Numeric(10, 0), nullable=False)
    prix_aircalin_reel_xpf = Column(Numeric(10, 0), nullable=False)

    # (govoyages - aircalin_reel) / aircalin_reel * 100 — calculé à l'ajout
    ecart_pourcent = Column(Numeric(6, 2), nullable=False)

    observe_le = Column(DateTime(timezone=True), server_default=func.now())
