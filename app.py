import json
import os
from pathlib import Path
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import CachedFare, PriceCalibration
from route_schedule import ROUTE_SCHEDULE

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Nom affiché et préfixe de numéro de vol par compagnie — toutes viennent
# maintenant de GoVoyages (scraping), plus de Duffel.
COMPAGNIES = {
    "SB": {"nom": "Aircalin", "prefixe_vol": "SB"},
    "QF": {"nom": "Qantas Airways", "prefixe_vol": "QF"},
    "NZ": {"nom": "Air New Zealand", "prefixe_vol": "NZ"},
    "FJ": {"nom": "Fiji Airways", "prefixe_vol": "FJ"},
    "TY": {"nom": "Air Calédonie", "prefixe_vol": "TY"},
}

# Détails d'affichage (durée, avion) qui ne viennent PAS du scraping —
# le scraper ne récupère que le PRIX, pas ces infos annexes.
# C'est une simplification volontaire pour l'instant : ces infos peuvent
# devenir fausses avec le temps (changement d'horaires, d'avion...) puisqu'elles
# ne sont pas mises à jour automatiquement. À enrichir plus tard si besoin.
ROUTE_INFO = {
    "BNE": {"dur": "2h 30m", "sb_num": "SB150", "plane": "Airbus A320neo"},
    "SYD": {"dur": "3h 15m", "sb_num": "SB140", "plane": "Airbus A320neo"},
    "AKL": {"dur": "2h 45m", "sb_num": "SB410", "plane": "Airbus A320neo"},
    "NAN": {"dur": "1h 55m", "sb_num": "SB330", "plane": "Boeing 737 MAX 8"},
    "PPT": {"dur": "6h 10m", "sb_num": "SB600", "plane": "Airbus A330neo"},
    "VLI": {"dur": "1h 05m", "sb_num": "SB230", "plane": "Airbus A320neo"},
    "WLS": {"dur": "1h 20m", "sb_num": "SB340", "plane": "Airbus A320neo"},
    "SIN": {"dur": "9h 10m", "sb_num": "SB700", "plane": "Airbus A330neo"},
    "BKK": {"dur": "10h 30m", "sb_num": "SB720", "plane": "Airbus A330neo"},
}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def read_index(
    request: Request,
    origin: str = Query(None),
    destination: str = Query(None),
    departure_date: str = Query(None),
    return_date: str = Query(None),
    trip_type: str = Query(None)
):
    clean_origin = origin if origin and origin.strip() else "NOU"
    clean_destination = destination if destination and destination.strip() else "SYD"
    clean_trip_type = trip_type if trip_type and trip_type.strip() else "roundtrip"
    clean_dep_date = departure_date if departure_date and departure_date.strip() else None
    clean_ret_date = return_date if return_date and return_date.strip() else None

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "saved_origin": clean_origin,
            "saved_destination": clean_destination,
            "saved_departure_date": clean_dep_date,
            "saved_return_date": clean_ret_date,
            "saved_trip_type": clean_trip_type,
            "route_schedule_json": json.dumps(ROUTE_SCHEDULE, ensure_ascii=False)
        }
    )


# Identifiants d'affiliation Trip.com — fixes, à réutiliser sur tous les liens
TRIP_COM_ALLIANCE_ID = "10253055"
TRIP_COM_SID = "329274464"
TRIP_COM_SUB3 = "D19448438"


def construire_lien_tripcom(origin: str, destination: str, departure_date: str, return_date: str | None) -> str:
    """
    Construit un lien d'affiliation Trip.com pré-rempli (origine, destination,
    dates, vols directs uniquement), avec vos identifiants d'affiliation.
    Format déduit d'une vraie recherche sur trip.com/flights.
    """
    params = {
        "dcity": origin.lower(),
        "acity": destination.lower(),
        "ddate": departure_date,
        "class": "y",
        "quantity": "1",
        "nonstoponly": "on",  # uniquement les vols directs
        "locale": "fr-FR",
        "curr": "EUR",
        "Allianceid": TRIP_COM_ALLIANCE_ID,
        "SID": TRIP_COM_SID,
        "trip_sub3": TRIP_COM_SUB3,
    }
    if return_date:
        params["rdate"] = return_date
        params["triptype"] = "rt"
    else:
        params["triptype"] = "ow"

    requete = "&".join(f"{cle}={valeur}" for cle, valeur in params.items())
    return f"https://fr.trip.com/flights/showfarefirst?{requete}"


def obtenir_correction_calibration(db: Session) -> tuple[float, int]:
    """
    Renvoie (écart moyen en %, nombre d'observations) à partir des
    vérifications manuelles enregistrées via ajouter_calibration.py.
    (0.0, 0) si aucune vérification n'a encore été faite — dans ce cas
    le prix GoVoyages brut est affiché tel quel, avec une mention "indicatif".
    """
    lignes = db.query(PriceCalibration).all()
    if not lignes:
        return 0.0, 0
    moyenne = sum(float(l.ecart_pourcent) for l in lignes) / len(lignes)
    return moyenne, len(lignes)


def build_flight_result(
    fare_row: CachedFare, airline_code: str, origin: str, destination: str, is_rt: bool,
    departure_date: str, return_date: str | None,
    ecart_pourcent: float = 0.0, nb_observations: int = 0
) -> dict:
    """Construit le dict résultat pour une compagnie à partir d'une ligne de cached_fares."""
    target_code = destination if origin == "NOU" else origin
    info = ROUTE_INFO.get(target_code, {"dur": "?", "plane": "Airbus A320neo"})
    compagnie = COMPAGNIES.get(airline_code, {"nom": airline_code, "prefixe_vol": airline_code})
    nom_compagnie = compagnie["nom"]
    numero_vol = f"{compagnie['prefixe_vol']}???"
    escales = fare_row.escales or 0
    # La durée dans ROUTE_INFO est celle d'un vol DIRECT — si ce n'est pas
    # le cas ce jour-là, on ne connaît pas la vraie durée avec escale(s),
    # mieux vaut l'indiquer clairement plutôt qu'afficher une durée fausse.
    duree_affichee = info["dur"] if escales == 0 else "Variable (avec escale)"

    slices = [{
        "depart_code": origin,
        "arrivee_code": destination,
        "depart_heure": "08:30",
        "arrivee_heure": "12:45",
        "duree_totale": duree_affichee,
        "escales": escales,
        "segments": [{
            "depart_code": origin,
            "depart_heure": "08:30",
            "arrivee_code": destination,
            "arrivee_heure": "12:45",
            "duree_vol": duree_affichee,
            "avion": info["plane"],
            "operateur": nom_compagnie,
            "vol_numero": numero_vol
        }]
    }]

    if is_rt:
        slices.append({
            "depart_code": destination,
            "arrivee_code": origin,
            "depart_heure": "14:10",
            "arrivee_heure": "18:25",
            "duree_totale": duree_affichee,
            "escales": escales,
            "segments": [{
                "depart_code": destination,
                "depart_heure": "14:10",
                "arrivee_code": origin,
                "arrivee_heure": "18:25",
                "duree_vol": duree_affichee,
                "avion": info["plane"],
                "operateur": nom_compagnie,
                "vol_numero": numero_vol
            }]
        })

    prix_brut = int(fare_row.price)

    # La calibration n'a été mesurée qu'entre GoVoyages et Aircalin — on ne
    # l'applique donc qu'à Aircalin. Pour les autres compagnies, le prix
    # GoVoyages est affiché tel quel, avec une mention "indicatif".
    if airline_code == "SB" and nb_observations > 0:
        prix = round(prix_brut / (1 + ecart_pourcent / 100))
        note_prix = f"Prix estimé, calibré sur {nb_observations} vérification(s) manuelle(s)"
    else:
        prix = prix_brut
        note_prix = "Prix indicatif (via revendeur)"

    return {
        "airline": nom_compagnie,
        "prix_xpf_num": prix,
        "price": f"{prix:,} XPF".replace(",", " "),
        "note_prix": note_prix,
        "booking_url": construire_lien_tripcom(origin, destination, departure_date, return_date if is_rt else None),
        "slices": slices
    }


@app.get("/search", response_class=HTMLResponse)
async def search_flights(
    request: Request,
    origin: str = Query(None),
    destination: str = Query(None),
    departure_date: str = Query(None),
    return_date: str = Query(None),
    trip_type: str = Query("roundtrip"),
    db: Session = Depends(get_db)
):
    if not origin or not destination or not departure_date or origin.strip() == "" or destination.strip() == "":
        return RedirectResponse(url="/")

    is_rt = (trip_type == "roundtrip" and return_date and return_date.strip() != "")

    results = []

    # Prix — lus depuis la base (alimentée par le cron horaire de scraping
    # GoVoyages), toutes compagnies confondues pour cette route.
    fare_rows = (
        db.query(CachedFare)
        .filter_by(origin=origin, destination=destination, trip_type=trip_type)
        .all()
    )
    if fare_rows:
        ecart_pourcent, nb_observations = obtenir_correction_calibration(db)
        for fare_row in fare_rows:
            results.append(build_flight_result(
                fare_row, fare_row.airline_code, origin, destination, is_rt,
                departure_date, return_date,
                ecart_pourcent, nb_observations
            ))

    results.sort(key=lambda x: x["prix_xpf_num"])

    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "results": results,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date or "",
            "trip_type": trip_type
        }
    )
