"""
À lancer à la main, de temps en temps (une fois par semaine par exemple),
après avoir vérifié un vrai prix sur aircalin.nc.

Le script va chercher le prix GoVoyages déjà en base pour cette route,
vous demande le vrai prix Aircalin que vous avez vu, et enregistre l'écart.

Lancer avec :
    python ajouter_calibration.py
"""

from database import SessionLocal
from models import CachedFare, PriceCalibration


def main():
    db = SessionLocal()
    try:
        origin = input("Origine (ex: NOU) : ").strip().upper() or "NOU"
        destination = input("Destination (ex: SYD) : ").strip().upper()
        trip_type = input("Type (oneway/roundtrip) [oneway] : ").strip().lower() or "oneway"

        fare = (
            db.query(CachedFare)
            .filter_by(origin=origin, destination=destination, trip_type=trip_type, airline_code="SB")
            .first()
        )

        if not fare:
            print(f"Aucun prix GoVoyages en base pour {origin}-{destination} ({trip_type}).")
            print("Lancez d'abord govoyages_scraper.py sur cette route, ou vérifiez le code destination.")
            return

        prix_govoyages = int(fare.price)
        print(f"Prix GoVoyages actuellement en base : {prix_govoyages} XPF")

        prix_aircalin_texte = input("Vrai prix vu sur aircalin.nc (en XPF, nombre entier) : ").strip()
        if not prix_aircalin_texte.isdigit():
            print("Prix invalide, annulé.")
            return
        prix_aircalin = int(prix_aircalin_texte)

        ecart_pourcent = round((prix_govoyages - prix_aircalin) / prix_aircalin * 100, 2)

        db.add(PriceCalibration(
            origin=origin,
            destination=destination,
            trip_type=trip_type,
            prix_govoyages_xpf=prix_govoyages,
            prix_aircalin_reel_xpf=prix_aircalin,
            ecart_pourcent=ecart_pourcent,
        ))
        db.commit()

        print(f"Enregistré : GoVoyages est {ecart_pourcent:+.1f}% par rapport au vrai prix Aircalin sur cette route.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
