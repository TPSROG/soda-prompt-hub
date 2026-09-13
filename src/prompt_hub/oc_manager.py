from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SUPPORTED_FORMATS = {
    "oc-manager-single-character",
    "oc-manager-world-folders",
    "oc-manager-full-database",
    "oc-manager-app-data",
    "oc-manager-character-array",
}

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class OCImportBundle:
    format_name: str
    characters: list[dict[str, Any]]
    worlds: list[dict[str, Any]]
    lore: dict[str, dict[str, Any]]


def parse_oc_manager_json(raw: bytes) -> OCImportBundle:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "Invalid OC Manager JSON"
        raise ValueError(msg) from error

    if isinstance(payload, list):
        return OCImportBundle(
            format_name="oc-manager-character-array",
            characters=_validate_characters(payload),
            worlds=[],
            lore={},
        )
    if not isinstance(payload, dict):
        msg = "OC Manager export must be a JSON object or character array"
        raise TypeError(msg)

    format_name = str(payload.get("format", "")).strip()
    if format_name == "oc-manager-single-character":
        characters = _validate_characters([payload.get("character")])
        return OCImportBundle(format_name, characters, [], {})
    if format_name == "oc-manager-world-folders":
        return _parse_world_folders(payload)
    if format_name == "oc-manager-full-database" or isinstance(payload.get("characters"), list):
        normalized_format = format_name or "oc-manager-app-data"
        if normalized_format not in SUPPORTED_FORMATS:
            normalized_format = "oc-manager-app-data"
        return OCImportBundle(
            format_name=normalized_format,
            characters=_validate_characters(payload.get("characters", [])),
            worlds=_mapping_list(payload.get("worlds", []), "worlds"),
            lore=_lore_map(payload.get("lore", {})),
        )

    msg = f"Unsupported OC Manager export format: {format_name or 'unknown'}"
    raise ValueError(msg)


def archive_import(root: Path, filename: str, raw: bytes) -> tuple[Path, str]:
    digest = hashlib.sha256(raw).hexdigest()
    destination = root / "sources" / "imports" / "oc-manager"
    destination.mkdir(parents=True, exist_ok=True)
    existing = next(destination.glob(f"*-{digest[:12]}-*.json"), None)
    if existing is not None:
        return existing, digest

    safe_name = _safe_filename(filename)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = destination / f"{timestamp}-{digest[:12]}-{safe_name}"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(raw)
    temporary.replace(target)
    return target, digest


def character_search_text(character: Mapping[str, Any]) -> str:
    fields = (
        character.get("name"),
        character.get("gender"),
        character.get("age"),
        character.get("race"),
        character.get("affiliation"),
        character.get("identity"),
        character.get("residence"),
        character.get("faction"),
        character.get("birthplace"),
        character.get("world"),
        character.get("story"),
        character.get("modules"),
        character.get("preferences"),
        character.get("timeline"),
        character.get("relationships"),
        character.get("prompts"),
    )
    return "\n".join(_text_values(fields))


def lore_search_text(lore: Mapping[str, Any]) -> str:
    return "\n".join(_text_values(lore.values()))


def build_oc_creative_seed(
    character: Mapping[str, Any],
    *,
    prompts: Iterable[Mapping[str, Any]] | None = None,
    lore: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize an OC Manager character into choices for the creative workspace."""
    character_id = _clean_text(character.get("id"))
    name = _clean_text(character.get("name"))
    appearance_value = character.get("appearance")
    appearance = appearance_value if isinstance(appearance_value, Mapping) else {}
    basic_parts = [
        name,
        _clean_text(character.get("gender")),
        _age_text(character.get("age")),
        _clean_text(character.get("race")),
        _clean_text(character.get("identity")),
    ]
    basic_character = _join_parts(basic_parts)

    views: dict[str, dict[str, str]] = {}
    for view in ("front", "back"):
        face = _layer_text(appearance.get("face"), view)
        sfw_parts = (
            face,
            _layer_text(appearance.get("upperSfw"), view),
            _layer_text(appearance.get("fullSfw"), view),
        )
        nsfw_parts = (
            face,
            _layer_text(appearance.get("upperNsfw"), view),
            _layer_text(appearance.get("fullNsfw"), view),
        )
        views[view] = {"sfw": _join_parts(sfw_parts), "nsfw": _join_parts(nsfw_parts)}

    outfit_values = appearance.get("outfits")
    raw_outfits = outfit_values if isinstance(outfit_values, list) else []
    active_outfit_id = _clean_text(appearance.get("activeOutfitId"))
    outfits = []
    for index, raw_outfit in enumerate(raw_outfits):
        if not isinstance(raw_outfit, Mapping):
            continue
        outfit_id = _clean_text(raw_outfit.get("id")) or f"outfit-{index + 1}"
        name_cn = _clean_text(raw_outfit.get("nameCN"))
        name_en = _clean_text(raw_outfit.get("nameEN"))
        outfits.append(
            {
                "id": outfit_id,
                "label": name_cn or name_en or outfit_id,
                "name_cn": name_cn,
                "name_en": name_en,
                "front": _join_parts(
                    (
                        _layer_text(raw_outfit.get("upper"), "front"),
                        _layer_text(raw_outfit.get("full"), "front"),
                    )
                ),
                "back": _join_parts(
                    (
                        _layer_text(raw_outfit.get("upper"), "back"),
                        _layer_text(raw_outfit.get("full"), "back"),
                    )
                ),
                "photo_prompt": _clean_text(raw_outfit.get("photoPrompt")),
                "active": outfit_id == active_outfit_id,
            }
        )

    prompt_source = prompts if prompts is not None else _mapping_values(character.get("prompts"))
    normalized_prompts = []
    for index, prompt in enumerate(prompt_source):
        text = _clean_text(prompt.get("text"))
        if not text:
            continue
        normalized_prompts.append(
            {
                "id": _clean_text(prompt.get("prompt_id") or prompt.get("id"))
                or f"prompt-{index + 1}",
                "label": _clean_text(prompt.get("label")) or "未命名提示词",
                "text": text,
            }
        )

    gallery = []
    for index, image in enumerate(_mapping_values(character.get("gallery"))):
        url = _clean_text(image.get("original_url") or image.get("url"))
        thumbnail_url = _clean_text(image.get("thumbnail_url")) or url
        if not _is_remote_visual(url) and not _is_remote_visual(thumbnail_url):
            continue
        gallery.append(
            {
                "id": _clean_text(image.get("id")) or f"image-{index + 1}",
                "caption": _clean_text(image.get("caption")),
                "thumbnail_url": thumbnail_url,
                "original_url": url or thumbnail_url,
            }
        )

    timeline = [
        {
            "id": _clean_text(item.get("id")) or f"event-{index + 1}",
            "date": _clean_text(item.get("date")),
            "title": _clean_text(item.get("title")),
            "description": _clean_text(item.get("description")),
            "importance": _clean_text(item.get("importance")) or "normal",
        }
        for index, item in enumerate(_mapping_values(character.get("timeline")))
        if any(_clean_text(item.get(key)) for key in ("date", "title", "description"))
    ]
    relationships = [
        {
            "id": _clean_text(item.get("id")) or f"relationship-{index + 1}",
            "target_id": _clean_text(item.get("targetId") or item.get("target_id")),
            "type": _clean_text(item.get("type")) or "other",
            "strength": item.get("strength", 0),
            "note": _clean_text(item.get("note")),
        }
        for index, item in enumerate(_mapping_values(character.get("relationships")))
    ]
    world_name = _clean_text(character.get("world"))
    return {
        "character_id": character_id,
        "name": name,
        "world": world_name,
        "story": _clean_text(character.get("story")),
        "basic_character": basic_character,
        "appearance": {
            "front": views["front"],
            "back": views["back"],
            "negative": _clean_text(appearance.get("negative")),
            "has_sfw": any(
                _layer_has_text(appearance.get(key)) for key in ("face", "upperSfw", "fullSfw")
            ),
            "has_nsfw": any(
                _layer_has_text(appearance.get(key)) for key in ("upperNsfw", "fullNsfw")
            ),
        },
        "outfits": outfits,
        "active_outfit_id": active_outfit_id,
        "prompts": normalized_prompts,
        "gallery": gallery,
        "relationships": relationships,
        "timeline": timeline,
        "world_context": {"world_name": world_name, "lore": dict(lore or {})},
    }


def _parse_world_folders(payload: dict[str, Any]) -> OCImportBundle:
    raw_worlds = payload.get("worlds", {})
    if not isinstance(raw_worlds, dict):
        msg = "worlds must be an object in oc-manager-world-folders"
        raise TypeError(msg)
    characters: list[Any] = []
    worlds: list[dict[str, Any]] = []
    for world_name, folder in raw_worlds.items():
        if not isinstance(folder, dict):
            continue
        clean_name = str(world_name).strip()
        if clean_name:
            worlds.append({"id": f"folder:{clean_name}", "name": clean_name, "system": "generic"})
        for raw_character in folder.get("characters", []):
            character = raw_character
            if isinstance(character, dict) and clean_name and not character.get("world"):
                character = {**character, "world": clean_name}
            characters.append(character)
    characters.extend(payload.get("unassigned", []))
    return OCImportBundle(
        format_name="oc-manager-world-folders",
        characters=_validate_characters(characters),
        worlds=worlds,
        lore=_lore_map(payload.get("lore", {})),
    )


def _validate_characters(raw_characters: Iterable[Any]) -> list[dict[str, Any]]:
    characters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_character in enumerate(raw_characters):
        if not isinstance(raw_character, dict):
            msg = f"Character at index {index} is not an object"
            raise TypeError(msg)
        character_id = str(raw_character.get("id", "")).strip()
        name = str(raw_character.get("name", "")).strip()
        if not character_id or not name:
            msg = f"Character at index {index} requires id and name"
            raise ValueError(msg)
        if character_id in seen:
            msg = f"Duplicate character id: {character_id}"
            raise ValueError(msg)
        seen.add(character_id)
        characters.append(dict(raw_character))
    return characters


def _mapping_list(value: object, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        msg = f"{field_name} must be an array"
        raise TypeError(msg)
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            msg = f"{field_name}[{index}] is not an object"
            raise TypeError(msg)
        result.append(dict(item))
    return result


def _lore_map(value: object) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        msg = "lore must be an object"
        raise TypeError(msg)
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def _text_values(values: Iterable[Any]) -> Iterable[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            clean = value.strip()
            if clean and not clean.startswith(("http://", "https://", "data:")):
                yield clean
        elif isinstance(value, (int, float, bool)):
            yield str(value)
        elif isinstance(value, Mapping):
            yield from _text_values(value.values())
        elif isinstance(value, Iterable):
            yield from _text_values(value)


def _mapping_values(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _clean_text(value: object) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _age_text(value: object) -> str:
    age = _clean_text(value)
    if not age:
        return ""
    return f"{age} years old" if age.isdigit() else age


def _layer_text(value: object, view: str) -> str:
    if not isinstance(value, Mapping):
        return ""
    primary = "back" if view == "back" else "front"
    fallback = "front" if primary == "back" else "back"
    return _clean_text(value.get(primary)) or _clean_text(value.get(fallback))


def _layer_has_text(value: object) -> bool:
    return isinstance(value, Mapping) and bool(
        _clean_text(value.get("front")) or _clean_text(value.get("back"))
    )


def _join_parts(values: Iterable[object]) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in _clean_text(value).split(","):
            clean = part.strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
    return ", ".join(result)


def _is_remote_visual(value: str) -> bool:
    return value.startswith(("https://", "http://"))


def _safe_filename(filename: str) -> str:
    original = Path(filename).name[:120]
    safe = _SAFE_FILENAME_RE.sub("-", original).strip("-.") or "oc-manager-export.json"
    if not safe.lower().endswith(".json"):
        safe += ".json"
    return safe
