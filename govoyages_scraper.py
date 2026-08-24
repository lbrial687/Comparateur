"""
Scraper GoVoyages — alternative à Aircalin en direct (bloqué par Imperva).

⚠️ IMPORTANT : le prix récupéré ici est celui de GoVoyages, un revendeur.
Il inclut leur marge et ne correspond PAS exactement au prix Aircalin
affiché sur aircalin.nc. On le stocke avec airline_code="SB" quand même
pour l'instant (même logique de comparaison), mais avec source="govoyages"
pour bien le distinguer d'un futur scraping direct.

Même logique de décision que le scraper Aircalin (voir aircalin_scraper.py) :
seuil de 1500 XPF pour la mise à jour, garde-fou contre les prix aberrants,
un seul passage par heure.

Pour lancer manuellement en local (une fois DATABASE_URL défini) :
    python govoyages_scraper.py
"""

from datetime import datetime, timedelta
import re
import time

from playwright.sync_api import sync_playwright

from database import SessionLocal
from models import CachedFare
from alerts import send_alert

SEUIL_MISE_A_JOUR_XPF = 1500
RATIO_ABERRANT = 3
EUR_TO_XPF = 119.33  # taux fixe approximatif, comme pour Duffel

DESTINATIONS = ["BNE", "SYD", "AKL", "NAN", "PPT", "VLI", "WLS", "SIN", "BKK"]


def scrape_price(destination: str, trip_type: str) -> dict[str, list[tuple[str, int, int]]]:
    """
    Récupère les prix affichés sur govoyages.com pour une route donnée.
    Pour chaque compagnie trouvée, renvoie jusqu'à 2 options : le meilleur
    prix DIRECT, et le meilleur prix AVEC ESCALE (seulement si moins cher
    que le direct).
    Renvoie {code_compagnie: [(variante, prix_xpf, escales), ...]},
    vide si le scraping a échoué ou qu'aucune compagnie n'a été trouvée.
    """
    depart_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    retour_date = (datetime.now() + timedelta(days=44)).strftime("%Y-%m-%d")
    debut = time.perf_counter()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto("https://www.govoyages.com/frontend-home/flights/?searchExtension=true/#/", timeout=30000)

            # Bandeau de cookies éventuel (même logique de précaution que pour Aircalin)
            try:
                page.click("text=Accepter", timeout=5000)
                page.wait_for_timeout(500)
            except Exception:
                pass

            # Pop-up "Connectez-vous pour obtenir le Meilleur prix garanti"
            # qui s'affiche par-dessus le formulaire — on la ferme avec Échap.
            try:
                page.wait_for_selector("text=Meilleur prix garanti", timeout=5000)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            # S'assurer d'être sur l'onglet "Vols" dès le départ (identifiant
            # stable, plutôt que le texte "Vols" qui apparaît aussi ailleurs
            # sur la page, comme dans une bannière "Vols à partir de...").
            try:
                page.click("[test-id='tab-flights']", timeout=5000)
                page.wait_for_timeout(300)
            except Exception:
                pass

            # 1. Type de vol (cliquer le label, pas l'input caché)
            if trip_type == "oneway":
                page.click("label[for='tripTypeSwitcher_oneWayTrip']")
            else:
                page.click("label[for='tripTypeSwitcher_roundTrip']")
            page.wait_for_timeout(500)

            # 2. Origine (toujours Nouméa) — premier champ test-id="input-airport"
            champs_aeroport = page.locator("[test-id='input-airport']")
            champs_aeroport.nth(0).click()
            champs_aeroport.nth(0).fill("Nouméa")
            page.wait_for_timeout(1000)
            page.click(".prisma-dropdown-item >> nth=0")

            # 3. Destination — second champ test-id="input-airport"
            # On préfère un résultat contenant "Airport" (l'aéroport précis)
            # plutôt que la première entrée qui est souvent "Ville - tous les
            # aéroports" (générique), ce qui semblait faire basculer le
            # parcours vers "Hôtels" au lieu de "Vols".
            champs_aeroport.nth(1).click()
            champs_aeroport.nth(1).fill(destination)
            page.wait_for_timeout(1000)
            resultat_aeroport = page.locator(".prisma-dropdown-item").filter(has_text=re.compile("Airport", re.IGNORECASE))
            resultat_avec_code = page.locator(".prisma-dropdown-item").filter(has_text=re.compile(rf"\b{destination}\b"))

            if resultat_avec_code.count() > 0:
                resultat_avec_code.first.click()
            elif resultat_aeroport.count() > 0:
                resultat_aeroport.first.click()
            else:
                print(f"  -> Aucun résultat pertinent pour la destination {destination}, on abandonne cette route.")
                return {}

            # 4. Dates : calendrier avec prix par jour (odf-calendar-day)
            NOMS_MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                            "août", "septembre", "octobre", "novembre", "décembre"]

            def cliquer_jour(date_cible: datetime) -> None:
                nom_mois = NOMS_MOIS_FR[date_cible.month - 1]
                jour_texte = str(date_cible.day)

                # On limite d'abord la recherche au bon bloc de mois (le
                # calendrier affiche 2 mois côte à côte, donc un même numéro
                # de jour existe deux fois si on ne précise pas le mois).
                # Le titre du mois (.odf-calendar-title) est un frère du bloc
                # des jours (.odf-calendar-month) — leur parent commun est
                # .odf-calendar, c'est lui qu'il faut scoper.
                titre_mois = page.locator(".odf-calendar-title").filter(has_text=nom_mois)
                conteneur_mois = page.locator(".odf-calendar").filter(has=titre_mois)

                tentatives = 0
                while conteneur_mois.count() == 0 and tentatives < 6:
                    page.click("button:has(.odf-icon-arrow-right)")
                    page.wait_for_timeout(700)
                    titre_mois = page.locator(".odf-calendar-title").filter(has_text=nom_mois)
                    conteneur_mois = page.locator(".odf-calendar").filter(has=titre_mois)
                    tentatives += 1

                # Laisse le temps aux jours du mois nouvellement affiché de
                # bien se charger avant de chercher le jour précis dedans.
                page.wait_for_timeout(500)

                cellule = conteneur_mois.locator(".odf-calendar-day").filter(
                    has=page.locator(f"text=/^{jour_texte}$/")
                )
                cellule.first.click()
                page.wait_for_timeout(600)

            depart_dt = datetime.strptime(depart_date, "%Y-%m-%d")
            page.wait_for_timeout(1000)
            cliquer_jour(depart_dt)

            if trip_type == "roundtrip":
                retour_dt = datetime.strptime(retour_date, "%Y-%m-%d")
                cliquer_jour(retour_dt)

            # Le calendrier reste ouvert après la sélection des dates et
            # recouvre le bouton de recherche — on le referme en validant
            # avec le bouton "Continuer" du calendrier.
            try:
                page.click("text=Continuer", timeout=5000)
            except Exception:
                page.keyboard.press("Escape")  # filet de sécurité si le bouton n'apparaît pas
            page.wait_for_timeout(500)

            # Par précaution : un carrousel promotionnel sous le formulaire
            # semble pouvoir faire changer l'onglet actif (Vols/Hôtels/...)
            # tout seul avec le temps. On reclique "Vols" juste avant de
            # rechercher, pour être sûr d'être au bon endroit.
            try:
                page.click("[test-id='tab-flights']", timeout=3000)
                page.wait_for_timeout(300)
            except Exception:
                pass

            # 5. Lancer la recherche — ouvre un NOUVEL onglet avec les résultats,
            # il faut le capturer explicitement plutôt que de rester sur l'ancien.
            with page.expect_popup() as info_nouvel_onglet:
                page.click("[test-id='search-flights-btn']")
            page_resultats = info_nouvel_onglet.value
            page_resultats.wait_for_load_state()

            # 6. Attendre les résultats sur le nouvel onglet
            page_resultats.wait_for_timeout(8000)
            print(f"  -> URL du nouvel onglet : {page_resultats.url}")

            # Filet de sécurité : si l'URL de résultats ne mentionne pas la
            # bonne destination, on a sélectionné le mauvais aéroport plus
            # haut — mieux vaut abandonner que d'enregistrer une donnée fausse.
            if f"to={destination}" not in page_resultats.url:
                print(f"  -> Mauvaise destination dans l'URL de résultats (attendu {destination}), on abandonne cette route.")
                return {}

            # On cible précisément "Prix standard" (pas le "Prix réduit Prime",
            # réservé aux abonnés — un visiteur normal du comparateur ne
            # paierait pas ce tarif, l'afficher serait trompeur).
            # Pour chaque compagnie, on garde JUSQU'À DEUX options : le
            # meilleur prix DIRECT, et le meilleur prix AVEC ESCALE — mais
            # cette dernière seulement si elle est vraiment moins chère que
            # le direct (sinon inutile de la montrer).
            COMPAGNIES_A_EXTRAIRE = {
                "Air Caledonie International": "SB",  # Aircalin
                "Qantas Airways": "QF",
                "Air New Zealand": "NZ",
                "Fiji Airways": "FJ",
                # ⚠️ Nom exact à confirmer sur la route VLI — pas encore vu
                # dans nos captures, celui-ci est une supposition.
                "Air Calédonie": "TY",
            }

            texte_page = page_resultats.inner_text("body")
            prix_par_compagnie = {}  # {code: [(variante, prix_xpf, escales), ...]}

            for nom_compagnie, code_compagnie in COMPAGNIES_A_EXTRAIRE.items():
                motif_nom = rf"{re.escape(nom_compagnie)}(?! International)" if code_compagnie == "TY" else re.escape(nom_compagnie)
                correspondances = re.finditer(
                    rf"{motif_nom}.{{1,150}}?(Direct|(\d+)\s*corresp\.?).{{1,300}}?Prix standard\s*(\d[\d\s]*)\s?€",
                    texte_page,
                    re.DOTALL
                )

                options_directes = []    # [prix_eur, ...]
                options_avec_escale = [] # [(prix_eur, escales), ...]

                for m in correspondances:
                    texte_prix = m.group(3).replace(" ", "").replace("\xa0", "")
                    if not texte_prix.isdigit():
                        continue
                    prix_eur = int(texte_prix)
                    if m.group(1) == "Direct":
                        options_directes.append(prix_eur)
                    else:
                        options_avec_escale.append((prix_eur, int(m.group(2))))

                variantes_retenues = []  # [(variante, prix_eur, escales), ...]

                prix_direct_eur = min(options_directes) if options_directes else None
                if prix_direct_eur is not None:
                    variantes_retenues.append(("direct", prix_direct_eur, 0))

                if options_avec_escale:
                    prix_escale_eur, nb_escales = min(options_avec_escale, key=lambda x: x[0])
                    if prix_direct_eur is None or prix_escale_eur < prix_direct_eur:
                        variantes_retenues.append(("escale", prix_escale_eur, nb_escales))

                if variantes_retenues:
                    prix_par_compagnie[code_compagnie] = [
                        (variante, round(prix_eur * EUR_TO_XPF), escales)
                        for variante, prix_eur, escales in variantes_retenues
                    ]
                    for variante, prix_eur, escales in variantes_retenues:
                        label = "direct" if variante == "direct" else f"{escales} escale(s)"
                        print(f"  -> {nom_compagnie} [{variante}] : {prix_eur} € standard, {label}")
                elif nom_compagnie in texte_page:
                    print(f"  -> {nom_compagnie} présent sur la page mais aucun prix extrait (filtre à ajuster ?)")

            if not prix_par_compagnie:
                print(f"  -> Aucune compagnie trouvée dans les résultats pour {destination} ({trip_type}).")

            return prix_par_compagnie

        except Exception as e:
            # Pas de capture d'écran ici : sur Render, un fichier image
            # enregistré sur le disque du serveur n'est pas consultable
            # facilement. Le message d'erreur ci-dessous, lui, apparaît
            # dans les logs Render et suffit pour diagnostiquer.
            print(f"Erreur scraping {destination} ({trip_type}) : {e}")
            return {}
        finally:
            browser.close()
            duree = time.perf_counter() - debut
            print(f"  ⏱ NOU-{destination} ({trip_type}) : {duree:.1f}s")


def decider_et_enregistrer(db, destination: str, trip_type: str, airline_code: str, variante: str, nouvelle_option: tuple[int, int] | None) -> None:
    if nouvelle_option is None:
        send_alert(f"⚠️ Scraping GoVoyages échoué pour NOU-{destination} ({trip_type}, {airline_code}, {variante}) — aucun prix récupéré.")
        return

    nouveau_prix, nouvelles_escales = nouvelle_option

    existant = (
        db.query(CachedFare)
        .filter_by(origin="NOU", destination=destination, trip_type=trip_type, airline_code=airline_code, variante=variante)
        .first()
    )

    if existant is None:
        db.add(CachedFare(
            origin="NOU", destination=destination, trip_type=trip_type,
            airline_code=airline_code, variante=variante,
            price=nouveau_prix, escales=nouvelles_escales,
            source="govoyages",
        ))
        db.commit()
        print(f"NOU-{destination} ({trip_type}, {airline_code}, {variante}) : nouveau, {nouveau_prix} XPF enregistré.")
        return

    ancien_prix = int(existant.price)
    est_aberrant = (
        nouveau_prix <= 0
        or nouveau_prix > ancien_prix * RATIO_ABERRANT
        or ancien_prix > nouveau_prix * RATIO_ABERRANT
    )

    if est_aberrant:
        send_alert(
            f"⚠️ Prix aberrant détecté pour NOU-{destination} ({trip_type}, {airline_code}, {variante}) : "
            f"ancien={ancien_prix} XPF, nouveau (ignoré)={nouveau_prix} XPF."
        )
        return

    ecart = abs(nouveau_prix - ancien_prix)
    if ecart > SEUIL_MISE_A_JOUR_XPF:
        existant.price = nouveau_prix
        existant.escales = nouvelles_escales
        db.commit()
        print(f"NOU-{destination} ({trip_type}, {airline_code}, {variante}) : mis à jour {ancien_prix} -> {nouveau_prix} XPF.")
    else:
        if existant.escales != nouvelles_escales:
            existant.escales = nouvelles_escales
            db.commit()
        print(f"NOU-{destination} ({trip_type}, {airline_code}, {variante}) : écart de {ecart} XPF, sous le seuil, prix inchangé.")


def verifier_coherence_aller_retour(option_oneway: tuple[int, int] | None, option_roundtrip: tuple[int, int] | None) -> bool:
    """
    Vérifie que le prix aller-retour est cohérent avec le prix aller simple
    de la même route, compagnie ET variante (scrapés dans le même passage).
    Un aller-retour ne devrait jamais être moins cher qu'un aller simple, ni
    démesurément plus cher (au-delà de 4x, c'est probablement une erreur
    d'extraction plutôt qu'un vrai tarif).
    """
    if option_oneway is None or option_roundtrip is None:
        return True  # rien à comparer si l'un des deux a échoué
    prix_oneway, _ = option_oneway
    prix_roundtrip, _ = option_roundtrip
    if prix_roundtrip < prix_oneway:
        return False
    if prix_roundtrip > prix_oneway * 4:
        return False
    return True


def main():
    debut_total = time.perf_counter()
    db = SessionLocal()
    try:
        for destination in DESTINATIONS:
            debut_destination = time.perf_counter()
            resultats_par_type = {}
            for trip_type in ("oneway", "roundtrip"):
                brut = scrape_price(destination, trip_type)  # {code: [(variante, prix_xpf, escales), ...]}
                resultats_par_type[trip_type] = {
                    (code, variante): (prix_xpf, escales)
                    for code, variantes in brut.items()
                    for variante, prix_xpf, escales in variantes
                }

            cles_trouvees = set(resultats_par_type["oneway"]) | set(resultats_par_type["roundtrip"])

            for code_compagnie, variante in cles_trouvees:
                option_oneway = resultats_par_type["oneway"].get((code_compagnie, variante))
                option_roundtrip = resultats_par_type["roundtrip"].get((code_compagnie, variante))

                if not verifier_coherence_aller_retour(option_oneway, option_roundtrip):
                    send_alert(
                        f"⚠️ Incohérence de prix NOU-{destination} ({code_compagnie}, {variante}) : "
                        f"aller simple {option_oneway} vs aller-retour {option_roundtrip} — valeurs ignorées ce passage."
                    )
                    continue

                decider_et_enregistrer(db, destination, "oneway", code_compagnie, variante, option_oneway)
                decider_et_enregistrer(db, destination, "roundtrip", code_compagnie, variante, option_roundtrip)

            duree_destination = time.perf_counter() - debut_destination
            print(f"⏱⏱ NOU-{destination} (oneway + roundtrip) : {duree_destination:.1f}s au total\n")
    finally:
        db.close()
        duree_totale = time.perf_counter() - debut_total
        nb_destinations = len(DESTINATIONS)
        moyenne = duree_totale / nb_destinations if nb_destinations else 0
        print(f"⏱⏱⏱ Passage complet : {duree_totale:.1f}s pour {nb_destinations} destinations ({moyenne:.1f}s/destination en moyenne)")


if __name__ == "__main__":
    main()
