from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

from app_monitor.models import SpeciesImage, SpeciesInfo


class Command(BaseCommand):
    help = "Backfill missing SpeciesImage records from Wikidata P18 images."

    WIKIDATA_API = "https://www.wikidata.org/w/api.php"
    GBIF_API = "https://api.gbif.org/v1"
    INAT_API = "https://api.inaturalist.org/v1"
    USER_AGENT = "YellowRiverWetland/1.0 (species image backfill)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of species to try. 0 means all missing species.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.2,
            help="Seconds to wait between Wikidata requests.",
        )
        parser.add_argument(
            "--skip-wikidata",
            action="store_true",
            help="Use GBIF only. Helpful when Wikidata is temporarily rate-limited.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        sleep = options["sleep"]

        species_qs = (
            SpeciesInfo.objects.filter(images__isnull=True)
            .order_by("name_cn")
            .distinct()
        )
        if limit:
            species_qs = species_qs[:limit]

        created = 0
        tried = 0
        missed = []

        for species in species_qs:
            tried += 1
            image = self._find_image(species, skip_wikidata=options["skip_wikidata"])
            if not image:
                missed.append(species.name_cn)
                continue

            image_url = image["url"]
            if SpeciesImage.objects.filter(species=species, image_url=image_url).exists():
                continue

            SpeciesImage.objects.create(
                species=species,
                image_url=image_url,
                caption=f"{species.name_cn} {image['label']} image",
                source=image["source"],
                source_url=image.get("source_url", ""),
                source_author=image.get("author", ""),
                is_featured=not SpeciesImage.objects.filter(
                    species=species, is_featured=True
                ).exists(),
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"added {species.name_cn}: {image['label']}"))
            time.sleep(sleep)

        self.stdout.write(
            self.style.SUCCESS(f"Species image backfill done: tried={tried}, created={created}")
        )
        if missed:
            preview = ", ".join(missed[:30])
            suffix = "..." if len(missed) > 30 else ""
            self.stdout.write(
                self.style.WARNING(
                    f"No external image for {len(missed)} species: {preview}{suffix}"
                )
            )

    def _find_image(self, species, skip_wikidata=False):
        if not skip_wikidata:
            filename, entity_id = self._find_commons_file(species)
            if filename:
                return {
                    "url": f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}",
                    "source": "wikimedia",
                    "source_url": f"https://www.wikidata.org/wiki/{entity_id}" if entity_id else "",
                    "author": "Wikimedia Commons",
                    "label": "Wikimedia Commons",
                }

        gbif = self._find_gbif_image(species)
        if gbif:
            return gbif

        inat = self._find_inaturalist_image(species)
        if inat:
            return inat

        return None

    def _find_commons_file(self, species):
        search_terms = []
        if species.name_latin:
            search_terms.append(species.name_latin.strip())
        if species.name_cn:
            search_terms.append(species.name_cn.strip())

        for term in search_terms:
            entity_ids = self._search_entities(term)
            for entity_id in entity_ids:
                filename = self._get_p18_filename(entity_id)
                if filename:
                    return filename, entity_id
        return None, None

    def _find_gbif_image(self, species):
        for term in self._latin_terms(species.name_latin):
            match = self._get_json(
                self.GBIF_API + "/species/match?" + urlencode({"name": term})
            )
            usage_key = match.get("usageKey") or match.get("speciesKey")
            if not usage_key or match.get("matchType") == "NONE":
                continue

            media = self._get_json(
                f"{self.GBIF_API}/species/{usage_key}/media?" + urlencode({"limit": 5})
            )
            for item in media.get("results", []):
                url = item.get("identifier")
                if not url:
                    continue
                return {
                    "url": url,
                    "source": "other",
                    "source_url": f"https://www.gbif.org/species/{usage_key}",
                    "author": item.get("rightsHolder") or "GBIF",
                    "label": "GBIF",
                }
        return None

    def _find_inaturalist_image(self, species):
        for term in self._latin_terms(species.name_latin):
            data = self._get_json(
                self.INAT_API + "/taxa?" + urlencode({
                    "q": term,
                    "rank": "species",
                    "per_page": 5,
                })
            )
            for item in data.get("results", []):
                if item.get("iconic_taxon_name") != "Aves":
                    continue
                photo = item.get("default_photo") or {}
                url = photo.get("medium_url") or photo.get("url")
                if not url:
                    continue
                return {
                    "url": url,
                    "source": "other",
                    "source_url": f"https://www.inaturalist.org/taxa/{item.get('id')}",
                    "author": photo.get("attribution_name") or "iNaturalist",
                    "label": "iNaturalist",
                }
        return None

    def _latin_terms(self, latin):
        text = " ".join((latin or "").split())
        if not text:
            return []
        terms = [text]
        # Some imported rows accidentally removed the space between genus and species.
        # Keep the exact value first, then try a simple capitalized-genus split.
        if " " not in text and len(text) > 8:
            for i in range(4, min(14, len(text) - 3)):
                candidate = f"{text[:i]} {text[i:]}"
                if candidate[0].isupper() and candidate[i + 1].islower():
                    terms.append(candidate)
        return terms

    def _search_entities(self, term):
        params = {
            "action": "wbsearchentities",
            "search": term,
            "language": "en",
            "format": "json",
            "limit": 5,
        }
        data = self._get_json(self.WIKIDATA_API + "?" + urlencode(params))
        results = data.get("search", []) if data else []
        return [item["id"] for item in results if item.get("id")]

    def _get_p18_filename(self, entity_id):
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "claims",
            "format": "json",
        }
        data = self._get_json(self.WIKIDATA_API + "?" + urlencode(params))
        entity = (data.get("entities") or {}).get(entity_id, {}) if data else {}
        claims = entity.get("claims") or {}
        images = claims.get("P18") or []
        for claim in images:
            try:
                value = claim["mainsnak"]["datavalue"]["value"]
            except (KeyError, TypeError):
                continue
            if value:
                return value
        return None

    def _get_json(self, url):
        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.stdout.write(self.style.WARNING(f"Image source request failed: {exc}"))
            return {}
