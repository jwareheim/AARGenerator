use serde::Serialize;

#[derive(Serialize, Default)]
pub struct Snapshot {
    pub parser_version: String,
    pub patch_version: Option<String>,
    pub ironman: bool,
    pub date: Option<String>,
    pub player_country_id: Option<i64>,

    pub empire: Empire,
    pub state: State,
    pub ruler: Leader,
    pub leaders: Vec<Leader>,
    pub wars: Vec<War>,
    pub concluded_wars: Vec<ConcludedWar>,
    pub diplomacy: Diplomacy,
}

#[derive(Serialize, Default)]
pub struct Empire {
    pub name: Option<String>,
    pub adjective: Option<String>,
    pub authority: Option<String>,
    pub ethics: Vec<String>,
    pub civics: Vec<String>,
    pub origin: Option<String>,
    pub home_planet: Option<String>,
    pub home_system: Option<String>,
    pub species_name: Option<String>,
    pub species_class: Option<String>,
    pub species_traits: Vec<String>,
}

#[derive(Serialize, Default)]
pub struct State {
    pub owned_planets: Vec<String>,
    pub owned_planet_count: u32,
    pub total_pops: u32,
    pub fleet_power: u64,
    pub monthly_energy: f64,
    pub monthly_minerals: f64,
    pub monthly_alloys: f64,
    pub traditions: Vec<String>,
    pub ascension_perks: Vec<String>,
    pub recent_technologies: Vec<String>,
}

#[derive(Serialize, Default, Clone)]
pub struct Leader {
    pub id: Option<i64>,
    pub name: Option<String>,
    pub gender: Option<String>,
    pub age: Option<f64>,
    pub traits: Vec<String>,
    pub class: Option<String>,
}

#[derive(Serialize)]
pub struct War {
    pub id: i64,
    pub name: Option<String>,
    pub attacker: Option<String>,
    pub defender: Option<String>,
    pub start_date: Option<String>,
    pub our_warscore: f64,
    pub active: bool,
}

#[derive(Serialize)]
pub struct ConcludedWar {
    pub id: i64,
    pub name: Option<String>,
    pub attacker: Option<String>,
    pub defender: Option<String>,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub outcome: Option<String>,
}

#[derive(Serialize, Default)]
pub struct Diplomacy {
    pub federation: Option<Federation>,
    pub subjects: Vec<String>,
    pub rivals: Vec<String>,
    pub allies: Vec<String>,
}

#[derive(Serialize)]
pub struct Federation {
    pub name: Option<String>,
    pub members: Vec<String>,
    pub player_role: Option<String>,
}
