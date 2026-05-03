use crate::error::ParserError;
use crate::schema::{Federation, Leader, Snapshot, War};
use jomini::{text::ArrayReader, text::ObjectReader, TextDeserializer, TextTape};
use serde::{de::DeserializeOwned, Deserialize};
use std::collections::HashMap;

const PARSER_VERSION: &str = env!("CARGO_PKG_VERSION");

// ── Meta ─────────────────────────────────────────────────────────────────────

#[derive(Deserialize, Default)]
struct MetaFile {
    version: Option<String>,
    date: Option<String>,
    player_portrait: Option<String>,
    #[serde(default)]
    ironman: bool,
}

// ── Entry point ───────────────────────────────────────────────────────────────

pub fn extract(meta_bytes: &[u8], gamestate_bytes: &[u8]) -> Result<Snapshot, ParserError> {
    let meta = cwparse::<MetaFile>(meta_bytes)?;

    let tape = TextTape::from_slice(gamestate_bytes)
        .map_err(|e| ParserError::ParseError(format!("gamestate tape error: {}", e)))?;

    let mut snapshot = Snapshot::default();
    snapshot.parser_version = PARSER_VERSION.to_string();
    snapshot.patch_version = meta.version;
    snapshot.date = meta.date;
    snapshot.ironman = meta.ironman;

    let player_portrait = meta.player_portrait.unwrap_or_default();
    let (player_country_id, leaders) = extract_leaders_tape(&tape, &player_portrait)?;

    snapshot.player_country_id = player_country_id;
    snapshot.leaders = leaders;

    if let Some(country_id) = player_country_id {
        extract_country_tape(&tape, country_id, &mut snapshot)?;
    }

    Ok(snapshot)
}

// ── Leaders ───────────────────────────────────────────────────────────────────

#[derive(Default)]
struct RawLeader {
    portrait: String,
    name: Option<String>,
    class: Option<String>,
    gender: Option<String>,
    age: Option<f64>,
    country: Option<i64>,
}

fn extract_leaders_tape(
    tape: &TextTape<'_>,
    player_portrait: &str,
) -> Result<(Option<i64>, Vec<Leader>), ParserError> {
    let reader = tape.windows1252_reader();
    let mut raw_leaders: Vec<(i64, RawLeader)> = Vec::new();

    'top: for (key, _op, value) in reader.fields() {
        if key.read_str().as_ref() != "leaders" {
            continue;
        }
        let leaders_obj = match value.read_object() {
            Ok(o) => o,
            Err(_) => break 'top,
        };
        raw_leaders = read_leaders_obj(leaders_obj);
        break 'top;
    }

    let player_country_id = raw_leaders
        .iter()
        .find(|(_, d)| d.portrait == player_portrait)
        .and_then(|(_, d)| d.country);

    if player_country_id.is_none() && !player_portrait.is_empty() {
        return Err(ParserError::ExtractionError(format!(
            "no leader with portrait '{}' — cannot identify player country",
            player_portrait
        )));
    }

    let leaders: Vec<Leader> = raw_leaders
        .into_iter()
        .filter(|(_, d)| player_country_id.is_some() && d.country == player_country_id)
        .map(|(id, d)| Leader {
            id: Some(id),
            name: d.name,
            class: d.class,
            age: d.age,
            gender: d.gender,
            traits: vec![],
        })
        .collect();

    Ok((player_country_id, leaders))
}

fn read_leaders_obj<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
) -> Vec<(i64, RawLeader)> {
    let mut out = Vec::new();
    for (key, _op, value) in obj.fields() {
        let id = match key.read_str().parse::<i64>() {
            Ok(n) => n,
            Err(_) => continue,
        };
        let entry_obj = match value.read_object() {
            Ok(o) => o,
            Err(_) => continue,
        };
        out.push((id, read_leader_entry(entry_obj)));
    }
    out
}

fn read_leader_entry<E: jomini::Encoding + Clone>(obj: ObjectReader<'_, '_, E>) -> RawLeader {
    let mut d = RawLeader::default();
    for (fk, _op, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "portrait" => d.portrait = fv.read_str().map(|s| s.into_owned()).unwrap_or_default(),
            "class" => d.class = fv.read_str().ok().map(|s| s.into_owned()),
            "gender" => d.gender = fv.read_str().ok().map(|s| s.into_owned()),
            "age" => d.age = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "country" => d.country = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "name" => {
                if let Ok(name_obj) = fv.read_object() {
                    for (nk, _, nv) in name_obj.fields() {
                        if nk.read_str().as_ref() == "first_name" {
                            d.name = nv.read_str().ok().map(|s| s.into_owned());
                            break;
                        }
                    }
                }
            }
            _ => {}
        }
    }
    d
}

// ── Country ───────────────────────────────────────────────────────────────────

#[derive(Default)]
struct RawCountry {
    name: Option<String>,
    adjective: Option<String>,
    authority: Option<String>,
    ruler_id: Option<i64>,
    capital_id: Option<i64>,
    military_power: f64,
    ethics: Vec<String>,
    civics: Vec<String>,
    species_id: Option<i64>,
    monthly_energy: f64,
    monthly_minerals: f64,
    monthly_alloys: f64,
    technologies: Vec<String>,
    traditions: Vec<String>,
    ascension_perks: Vec<String>,
    subjects: Vec<i64>,
    allies: Vec<i64>,
    rivals: Vec<i64>,
    federation_id: Option<i64>,
}

#[derive(Default)]
struct RawSpecies {
    name: Option<String>,
    portrait: Option<String>,
    class: Option<String>,
    traits: Vec<String>,
}

// ── War ───────────────────────────────────────────────────────────────────────

struct RawWar {
    id: i64,
    name: Option<String>,
    start_date: Option<String>,
    primary_attacker: Option<i64>,
    primary_defender: Option<i64>,
    our_warscore: f64,
}

// ── Federation ────────────────────────────────────────────────────────────────

struct RawFederation {
    name: Option<String>,
    members: Vec<i64>,
    leader: Option<i64>,
}

// ── Country extraction ────────────────────────────────────────────────────────

fn extract_country_tape(
    tape: &TextTape<'_>,
    country_id: i64,
    snapshot: &mut Snapshot,
) -> Result<(), ParserError> {
    let reader = tape.windows1252_reader();
    let mut raw_country: Option<RawCountry> = None;
    let mut country_name_map: HashMap<i64, String> = HashMap::new();
    let mut species_vec: Vec<RawSpecies> = Vec::new();
    let mut planet_vec: Vec<RawPlanet> = Vec::new();
    let mut galobj_map: HashMap<i64, String> = HashMap::new();
    let mut raw_wars: Vec<RawWar> = Vec::new();
    let mut federation_map: HashMap<i64, RawFederation> = HashMap::new();

    for (key, _op, value) in reader.fields() {
        match key.read_str().as_ref() {
            "country" => {
                if raw_country.is_none() {
                    if let Ok(obj) = value.read_object() {
                        let (rc, nm) = scan_countries(obj, country_id);
                        raw_country = rc;
                        country_name_map = nm;
                    }
                }
            }
            "species" => {
                // Top-level species block is an unnamed array: species={ {...} {...} }
                if let Ok(arr) = value.read_array() {
                    species_vec = read_species_array(arr);
                }
            }
            "planets" => {
                // planets = { planet = { 0={...} 1={...} } }
                if let Ok(outer) = value.read_object() {
                    for (pk, _, pv) in outer.fields() {
                        if pk.read_str().as_ref() == "planet" {
                            if let Ok(planets_obj) = pv.read_object() {
                                planet_vec = collect_planets(planets_obj);
                            }
                            break;
                        }
                    }
                }
            }
            "galactic_object" => {
                if let Ok(obj) = value.read_object() {
                    galobj_map = collect_galactic_objects(obj);
                }
            }
            "war" => {
                if let Ok(obj) = value.read_object() {
                    raw_wars = collect_wars(obj, country_id);
                }
            }
            "federation" => {
                if let Ok(obj) = value.read_object() {
                    collect_federations_into(obj, &mut federation_map);
                }
            }
            _ => {}
        }
    }

    let country = match raw_country {
        Some(c) => c,
        None => return Ok(()),
    };

    snapshot.empire.name = country.name;
    snapshot.empire.adjective = country.adjective;
    snapshot.empire.authority = country.authority;
    snapshot.empire.ethics = country.ethics;
    snapshot.empire.civics = country.civics;

    snapshot.state.fleet_power = country.military_power as u64;
    snapshot.state.monthly_energy = country.monthly_energy;
    snapshot.state.monthly_minerals = country.monthly_minerals;
    snapshot.state.monthly_alloys = country.monthly_alloys;
    snapshot.state.traditions = country.traditions;
    snapshot.state.ascension_perks = country.ascension_perks;

    let tech_count = country.technologies.len();
    snapshot.state.recent_technologies = if tech_count > 10 {
        country.technologies[tech_count - 10..].to_vec()
    } else {
        country.technologies
    };

    if let Some(ruler_id) = country.ruler_id {
        if let Some(leader) = snapshot.leaders.iter().find(|l| l.id == Some(ruler_id)) {
            snapshot.ruler = leader.clone();
        }
    }

    if let Some(idx) = country.species_id {
        if let Some(sp) = species_vec.get(idx as usize) {
            snapshot.empire.species_name = sp.name.clone();
            snapshot.empire.species_traits = sp.traits.clone();
            snapshot.empire.species_class = sp.class.clone().or_else(|| {
                sp.portrait.as_ref().map(|p| portrait_to_class(p))
            });
        }
    }

    // ── Planets ───────────────────────────────────────────────────────────────

    let capital_id = country.capital_id;

    let owned: Vec<&RawPlanet> = planet_vec
        .iter()
        .filter(|p| p.owner == Some(country_id))
        .collect();

    snapshot.state.owned_planet_count = owned.len() as u32;
    snapshot.state.owned_planets = owned.iter().filter_map(|p| p.name.clone()).collect();
    snapshot.state.total_pops = owned.iter().map(|p| p.pop_count()).sum();

    if let Some(cap_id) = capital_id {
        if let Some(cap_planet) = planet_vec.iter().find(|p| p.id == cap_id) {
            snapshot.empire.home_planet = cap_planet.name.clone();
            if let Some(sys_id) = cap_planet.system_id {
                snapshot.empire.home_system = galobj_map.get(&sys_id).cloned();
            }
        }
    }

    // ── Wars ──────────────────────────────────────────────────────────────────

    snapshot.wars = raw_wars
        .into_iter()
        .map(|w| War {
            id: w.id,
            name: w.name,
            attacker: w.primary_attacker.and_then(|id| country_name_map.get(&id).cloned()),
            defender: w.primary_defender.and_then(|id| country_name_map.get(&id).cloned()),
            start_date: w.start_date,
            our_warscore: w.our_warscore,
            active: true,
        })
        .collect();

    // Wars in the `war` block are all active; concluded wars don't persist
    snapshot.concluded_wars = Vec::new();

    // ── Diplomacy ─────────────────────────────────────────────────────────────

    snapshot.diplomacy.subjects = country
        .subjects
        .iter()
        .filter_map(|id| country_name_map.get(id).cloned())
        .collect();
    snapshot.diplomacy.allies = country
        .allies
        .iter()
        .filter_map(|id| country_name_map.get(id).cloned())
        .collect();
    snapshot.diplomacy.rivals = country
        .rivals
        .iter()
        .filter_map(|id| country_name_map.get(id).cloned())
        .collect();

    if let Some(fed_id) = country.federation_id {
        if let Some(raw_fed) = federation_map.remove(&fed_id) {
            let player_role = if raw_fed.leader == Some(country_id) {
                Some("president".to_string())
            } else {
                Some("member".to_string())
            };
            snapshot.diplomacy.federation = Some(Federation {
                name: raw_fed.name,
                members: raw_fed
                    .members
                    .iter()
                    .filter_map(|id| country_name_map.get(id).cloned())
                    .collect(),
                player_role,
            });
        }
    }

    Ok(())
}

// Scans all country entries: returns full RawCountry for player + name map for all countries.
fn scan_countries<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
    country_id: i64,
) -> (Option<RawCountry>, HashMap<i64, String>) {
    let mut player_country: Option<RawCountry> = None;
    let mut name_map: HashMap<i64, String> = HashMap::new();

    for (key, _op, value) in obj.fields() {
        let id: i64 = match key.read_str().parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if id == country_id {
            if let Ok(entry_obj) = value.read_object() {
                let rc = read_country_entry(entry_obj);
                if let Some(ref n) = rc.name {
                    name_map.insert(id, n.clone());
                }
                player_country = Some(rc);
            }
        } else if let Ok(entry_obj) = value.read_object() {
            for (fk, _, fv) in entry_obj.fields() {
                if fk.read_str().as_ref() == "name" {
                    if let Ok(s) = fv.read_str() {
                        name_map.insert(id, s.into_owned());
                    }
                    break;
                }
            }
        }
    }

    (player_country, name_map)
}

fn read_country_entry<E: jomini::Encoding + Clone>(obj: ObjectReader<'_, '_, E>) -> RawCountry {
    let mut d = RawCountry::default();
    for (fk, _op, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "name" => d.name = fv.read_str().ok().map(|s| s.into_owned()),
            "adjective" => d.adjective = fv.read_str().ok().map(|s| s.into_owned()),
            "authority" => d.authority = fv.read_str().ok().map(|s| s.into_owned()),
            "ruler" => d.ruler_id = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "capital" => d.capital_id = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "military_power" => {
                d.military_power =
                    fv.read_str().ok().and_then(|s| s.parse().ok()).unwrap_or(0.0)
            }
            "ethos" => {
                if let Ok(ethos_obj) = fv.read_object() {
                    for (ek, _, ev) in ethos_obj.fields() {
                        if ek.read_str().as_ref() == "ethic" {
                            if let Ok(s) = ev.read_str() {
                                d.ethics.push(s.into_owned());
                            }
                        }
                    }
                }
            }
            "government" => {
                // authority and civics live inside the government sub-block in 4.x
                if let Ok(gov_obj) = fv.read_object() {
                    for (gk, _, gv) in gov_obj.fields() {
                        match gk.read_str().as_ref() {
                            "authority" => {
                                d.authority = gv.read_str().ok().map(|s| s.into_owned())
                            }
                            "civics" => {
                                if let Ok(arr) = gv.read_array() {
                                    for v in arr.values() {
                                        if let Ok(s) = v.read_str() {
                                            d.civics.push(s.into_owned());
                                        }
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
            "species_index" => {
                d.species_id = fv.read_str().ok().and_then(|s| s.parse().ok());
            }
            "budget" => {
                if let Ok(budget_obj) = fv.read_object() {
                    for (bk, _, bv) in budget_obj.fields() {
                        if bk.read_str().as_ref() == "current_month" {
                            if let Ok(month_obj) = bv.read_object() {
                                for (mk, _, mv) in month_obj.fields() {
                                    if mk.read_str().as_ref() == "balance" {
                                        // Sum all source sub-blocks under balance
                                        if let Ok(balance_obj) = mv.read_object() {
                                            for (_, _, source_val) in balance_obj.fields() {
                                                if let Ok(source_obj) = source_val.read_object() {
                                                    for (rk, _, rv) in source_obj.fields() {
                                                        match rk.read_str().as_ref() {
                                                            "energy" => {
                                                                d.monthly_energy += rv
                                                                    .read_str()
                                                                    .ok()
                                                                    .and_then(|s| {
                                                                        s.parse::<f64>().ok()
                                                                    })
                                                                    .unwrap_or(0.0);
                                                            }
                                                            "minerals" => {
                                                                d.monthly_minerals += rv
                                                                    .read_str()
                                                                    .ok()
                                                                    .and_then(|s| {
                                                                        s.parse::<f64>().ok()
                                                                    })
                                                                    .unwrap_or(0.0);
                                                            }
                                                            "alloys" => {
                                                                d.monthly_alloys += rv
                                                                    .read_str()
                                                                    .ok()
                                                                    .and_then(|s| {
                                                                        s.parse::<f64>().ok()
                                                                    })
                                                                    .unwrap_or(0.0);
                                                            }
                                                            _ => {}
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        break;
                                    }
                                }
                            }
                            break;
                        }
                    }
                }
            }
            "tech_status" => {
                if let Ok(ts_obj) = fv.read_object() {
                    for (tk, _, tv) in ts_obj.fields() {
                        if tk.read_str().as_ref() == "technology" {
                            if let Ok(s) = tv.read_str() {
                                d.technologies.push(s.into_owned());
                            }
                        }
                    }
                }
            }
            "tradition_cats" => {
                // Wolfe 2.x: object with tradition tree names as keys
                if let Ok(tc_obj) = fv.read_object() {
                    for (k, _, _) in tc_obj.fields() {
                        let s = k.read_str().into_owned();
                        if !s.is_empty() {
                            d.traditions.push(s);
                        }
                    }
                }
            }
            "traditions" | "tradition_categories" => {
                // 3.x+: array of tradition names
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(s) = v.read_str() {
                            d.traditions.push(s.into_owned());
                        }
                    }
                }
            }
            "ascension_perks" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(s) = v.read_str() {
                            d.ascension_perks.push(s.into_owned());
                        }
                    }
                }
            }
            "subjects" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(s) = v.read_str() {
                            if let Ok(id) = s.parse::<i64>() {
                                d.subjects.push(id);
                            }
                        }
                    }
                }
            }
            "allies" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(s) = v.read_str() {
                            if let Ok(id) = s.parse::<i64>() {
                                d.allies.push(id);
                            }
                        }
                    }
                }
            }
            "standard_diplomacy_module" => {
                // rivals = { { country = X ... } ... } inside this sub-block
                if let Ok(mod_obj) = fv.read_object() {
                    for (mk, _, mv) in mod_obj.fields() {
                        if mk.read_str().as_ref() == "rivals" {
                            if let Ok(arr) = mv.read_array() {
                                for v in arr.values() {
                                    if let Ok(rival_obj) = v.read_object() {
                                        for (rk, _, rv) in rival_obj.fields() {
                                            if rk.read_str().as_ref() == "country" {
                                                if let Ok(s) = rv.read_str() {
                                                    if let Ok(id) = s.parse::<i64>() {
                                                        d.rivals.push(id);
                                                    }
                                                }
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                            break;
                        }
                    }
                }
            }
            "federation" => {
                d.federation_id = fv.read_str().ok().and_then(|s| s.parse().ok());
            }
            _ => {}
        }
    }
    d
}

// ── Wars ──────────────────────────────────────────────────────────────────────

fn collect_wars<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
    player_id: i64,
) -> Vec<RawWar> {
    let mut out = Vec::new();
    for (key, _op, value) in obj.fields() {
        let id: i64 = match key.read_str().parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if let Ok(war_obj) = value.read_object() {
            if let Some(war) = read_war_entry(war_obj, id, player_id) {
                out.push(war);
            }
        }
    }
    out
}

fn read_war_entry<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
    id: i64,
    player_id: i64,
) -> Option<RawWar> {
    let mut name: Option<String> = None;
    let mut start_date: Option<String> = None;
    let mut attacker_ids: Vec<i64> = Vec::new();
    let mut defender_ids: Vec<i64> = Vec::new();
    let mut our_warscore: f64 = 0.0;

    for (fk, _, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "name" => name = fv.read_str().ok().map(|s| s.into_owned()),
            "start_date" => start_date = fv.read_str().ok().map(|s| s.into_owned()),
            "attackers" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(part_obj) = v.read_object() {
                            let (cid, score) = read_war_participant(part_obj);
                            if let Some(cid) = cid {
                                attacker_ids.push(cid);
                                if cid == player_id {
                                    our_warscore = score;
                                }
                            }
                        }
                    }
                }
            }
            "defenders" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(part_obj) = v.read_object() {
                            let (cid, score) = read_war_participant(part_obj);
                            if let Some(cid) = cid {
                                defender_ids.push(cid);
                                if cid == player_id {
                                    our_warscore = score;
                                }
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    let player_in_war =
        attacker_ids.contains(&player_id) || defender_ids.contains(&player_id);
    if !player_in_war {
        return None;
    }

    Some(RawWar {
        id,
        name,
        start_date,
        primary_attacker: attacker_ids.first().copied(),
        primary_defender: defender_ids.first().copied(),
        our_warscore,
    })
}

fn read_war_participant<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
) -> (Option<i64>, f64) {
    let mut country: Option<i64> = None;
    let mut war_score: f64 = 0.0;
    for (fk, _, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "country" => country = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "war_score" => {
                war_score = fv
                    .read_str()
                    .ok()
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0.0)
            }
            _ => {}
        }
    }
    (country, war_score)
}

// ── Federations ───────────────────────────────────────────────────────────────

fn collect_federations_into<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
    map: &mut HashMap<i64, RawFederation>,
) {
    for (key, _op, value) in obj.fields() {
        let id: i64 = match key.read_str().parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if let Ok(fed_obj) = value.read_object() {
            map.insert(id, read_federation_entry(fed_obj));
        }
    }
}

fn read_federation_entry<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
) -> RawFederation {
    let mut fed = RawFederation {
        name: None,
        members: Vec::new(),
        leader: None,
    };
    for (fk, _, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "name" => fed.name = fv.read_str().ok().map(|s| s.into_owned()),
            "members" => {
                if let Ok(arr) = fv.read_array() {
                    for v in arr.values() {
                        if let Ok(s) = v.read_str() {
                            if let Ok(id) = s.parse::<i64>() {
                                fed.members.push(id);
                            }
                        }
                    }
                }
            }
            "leader" => fed.leader = fv.read_str().ok().and_then(|s| s.parse().ok()),
            _ => {}
        }
    }
    fed
}

// ── Planets + Galactic Objects ────────────────────────────────────────────────

#[derive(Default)]
struct RawPlanet {
    id: i64,
    name: Option<String>,
    owner: Option<i64>,
    system_id: Option<i64>,
    pop_from_array: u32,
    pop_count_field: Option<u32>,
}

impl RawPlanet {
    fn pop_count(&self) -> u32 {
        self.pop_count_field.unwrap_or(self.pop_from_array)
    }
}

fn collect_planets<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
) -> Vec<RawPlanet> {
    let mut out = Vec::new();
    for (key, _op, value) in obj.fields() {
        let id: i64 = match key.read_str().parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if let Ok(planet_obj) = value.read_object() {
            let mut p = read_planet_entry(planet_obj);
            p.id = id;
            out.push(p);
        }
    }
    out
}

fn read_planet_entry<E: jomini::Encoding + Clone>(obj: ObjectReader<'_, '_, E>) -> RawPlanet {
    let mut d = RawPlanet::default();
    for (fk, _op, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "name" => {
                // Scalar name (older saves). Sub-block names (4.x+) will be None.
                d.name = fv.read_str().ok().map(|s| s.into_owned());
            }
            "owner" => d.owner = fv.read_str().ok().and_then(|s| s.parse().ok()),
            "coordinate" => {
                if let Ok(coord_obj) = fv.read_object() {
                    for (ck, _, cv) in coord_obj.fields() {
                        if ck.read_str().as_ref() == "origin" {
                            d.system_id = cv.read_str().ok().and_then(|s| s.parse().ok());
                            break;
                        }
                    }
                }
            }
            "pop_count" => {
                d.pop_count_field = fv.read_str().ok().and_then(|s| s.parse().ok());
            }
            "pop" => {
                if d.pop_count_field.is_none() {
                    if let Ok(arr) = fv.read_array() {
                        d.pop_from_array += arr.values().count() as u32;
                    }
                }
            }
            _ => {}
        }
    }
    d
}

fn collect_galactic_objects<E: jomini::Encoding + Clone>(
    obj: ObjectReader<'_, '_, E>,
) -> HashMap<i64, String> {
    let mut map = HashMap::new();
    for (key, _op, value) in obj.fields() {
        let id: i64 = match key.read_str().parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if let Ok(go_obj) = value.read_object() {
            for (gk, _, gv) in go_obj.fields() {
                if gk.read_str().as_ref() == "name" {
                    if let Ok(s) = gv.read_str() {
                        map.insert(id, s.into_owned());
                    }
                    break;
                }
            }
        }
    }
    map
}

fn read_species_array<E: jomini::Encoding + Clone>(
    arr: ArrayReader<'_, '_, E>,
) -> Vec<RawSpecies> {
    // Top-level species block is an array of unnamed objects: species={ {...} {...} }
    let mut out = Vec::new();
    for v in arr.values() {
        if let Ok(sp_obj) = v.read_object() {
            out.push(read_species_entry(sp_obj));
        }
    }
    out
}

fn read_species_entry<E: jomini::Encoding + Clone>(obj: ObjectReader<'_, '_, E>) -> RawSpecies {
    let mut d = RawSpecies::default();
    for (fk, _op, fv) in obj.fields() {
        match fk.read_str().as_ref() {
            "name" => d.name = fv.read_str().ok().map(|s| s.into_owned()),
            "portrait" => d.portrait = fv.read_str().ok().map(|s| s.into_owned()),
            "class" => d.class = fv.read_str().ok().map(|s| s.into_owned()),
            "traits" => {
                if let Ok(traits_obj) = fv.read_object() {
                    for (tk, _, tv) in traits_obj.fields() {
                        if tk.read_str().as_ref() == "trait" {
                            if let Ok(s) = tv.read_str() {
                                d.traits.push(s.into_owned());
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
    d
}

fn portrait_to_class(portrait: &str) -> String {
    let prefix: String = portrait.chars().take_while(|c| c.is_alphabetic()).collect();
    match prefix.as_str() {
        "mam" => "Mammalian".to_string(),
        "rep" => "Reptilian".to_string(),
        "avi" => "Avian".to_string(),
        "mol" => "Molluscoid".to_string(),
        "fun" => "Fungoid".to_string(),
        "art" => "Arthropoid".to_string(),
        "lit" => "Lithoid".to_string(),
        "nec" => "Necroids".to_string(),
        "aqu" => "Aquatic".to_string(),
        "inf" | "ins" => "Insectoid".to_string(),
        "hum" => "Humanoid".to_string(),
        "pla" => "Plantoid".to_string(),
        "tok" => "Toxoid".to_string(),
        "bot" | "mac" => "Machine".to_string(),
        _ => prefix,
    }
}

// ── Parsing helpers ───────────────────────────────────────────────────────────

fn cwparse<T: DeserializeOwned>(bytes: &[u8]) -> Result<T, ParserError> {
    let de = TextDeserializer::from_windows1252_slice(bytes)
        .map_err(|e| ParserError::ParseError(format!("clausewitz parse error: {}", e)))?;
    T::deserialize(&de)
        .map_err(|e| ParserError::ParseError(format!("clausewitz deserialize error: {}", e)))
}
