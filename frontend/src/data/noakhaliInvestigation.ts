/**
 * Noakhali road infrastructure investigation – research dossier, updated through 14 November 2026.
 *
 * Everything here is transcribed from the dossier. Nothing is invented:
 *  - Figures come from different dates and categories and must NOT be added together.
 *  - Contract awards are not proof of completion or payment. Repair tenders do not prove earlier repairs.
 *  - Allegations about materials/subcontracting are allegations, not established findings.
 *  - Coordinates: only `precision: "osm"` locations come from real OSM road geometry already in the database.
 *    `"approx"` points are indicative (an area or upazila-level position), never a surveyed alignment.
 */

export type Evidence = "A" | "B" | "C";
/** repeat = documented repeated repair/failure · repair = official repair/maintenance contract on a damaged road
 *  (recurrence NOT established) · damage = news-reported damage · planned = improvement/design procurement, no failure evidence */
export type Recurrence = "repeat" | "repair" | "damage" | "planned";
export type Precision = "osm" | "approx";

export const EVIDENCE_LABEL: Record<Evidence, string> = {
  A: "A · Official record",
  B: "B · Named news report",
  C: "C · Lead, needs primary document",
};

export const RECURRENCE_LABEL: Record<Recurrence, string> = {
  repeat: "Documented repeat repair",
  repair: "Repair contract (recurrence unverified)",
  damage: "Reported damage",
  planned: "Planned improvement / design",
};

export const RECURRENCE_COLOR: Record<Recurrence, string> = {
  repeat: "#ef4444",
  repair: "#fb923c",
  damage: "#facc15",
  planned: "#60a5fa",
};

export type RoadCase = {
  id: string;
  upazila: string;
  road: string;
  issue: string;
  evidence: Evidence;
  recurrence: Recurrence;
  /** [lng, lat] */
  at: [number, number];
  precision: Precision;
  /** Where the position comes from, shown to the user. */
  locationNote: string;
  detail?: string[];
  /** Exact OSM road name(s) to draw as a real line. */
  osmNames?: string[];
};

// Indicative upazila positions (not road alignments). Points within one upazila are nudged apart so they stay clickable.
const SADAR: [number, number] = [91.0995, 22.8696];
const BEGUMGANJ: [number, number] = [91.1, 22.93];
const CHATKHIL: [number, number] = [91.17, 22.97];
const SONAIMURI: [number, number] = [91.03, 23.0];
const SENBAGH: [number, number] = [91.23, 23.0];
const COMPANIGANJ: [number, number] = [91.22, 22.8];
const SUBARNACHAR: [number, number] = [91.0, 22.6];
const HATIYA: [number, number] = [91.13, 22.37];
const nudge = (p: [number, number], i: number): [number, number] => [p[0] + (i % 3) * 0.018 - 0.018, p[1] + Math.floor(i / 3) * 0.016 - 0.008];
const AX = "Upazila-level position (indicative); the road alignment still has to be reconciled with LGED/RHD road IDs.";

export const ROADS: RoadCase[] = [
  {
    id: "R01", upazila: "Sadar", road: "Hospital Road, Maijdee (1.05 km)",
    issue: "Repeated repairs; sealcoat peeled one day after completion",
    evidence: "B", recurrence: "repeat",
    at: [91.0922, 22.8716], precision: "osm",
    locationNote: "The road passing Prime Hospital, Maijdee (OSM way 538203415, about 1 km, unnamed in OSM). Drawn from OSM geometry.",
    detail: [
      "Serves more than 100 government and private hospitals and clinics.",
      "Sealcoat completed 3 July 2026 and began peeling on 4 July; the municipality reportedly issued a notice to the contractor.",
      "Contractor attributed the damage to rainfall and promised corrective work.",
      "Allegations of low-quality materials and subcontracting are allegations, not established findings.",
    ],
  },
  { id: "R02", upazila: "Sadar", road: "Maijdee–Noruttompur–Otarhat–Kabirhat (Z-1459), 5th–6th km", issue: "Damaged pavement, carpeting tender (RHD Noakhali Road Division, tender 1245404, awarded; award record needs verification)", evidence: "A", recurrence: "repair", at: [91.118, 22.884], precision: "approx", locationNote: "Indicative position on the Maijdee–Kabirhat corridor; chainage 5th–6th km not surveyed." },
  { id: "R03", upazila: "Begumganj", road: "Kachua–Sahapur–Bot-toli", issue: "Potholes, surface deterioration", evidence: "B", recurrence: "damage", at: nudge(BEGUMGANJ, 0), precision: "approx", locationNote: AX },
  { id: "R04", upazila: "Chatkhil", road: "Chatkhil–Monohorpur via Palla Bazar", issue: "Potholes, eroded pavement", evidence: "B", recurrence: "damage", at: nudge(CHATKHIL, 0), precision: "approx", locationNote: AX },
  { id: "R05", upazila: "Chatkhil", road: "Khilpara–Deliai", issue: "Potholes and road deterioration", evidence: "B", recurrence: "damage", at: nudge(CHATKHIL, 1), precision: "approx", locationNote: AX },
  { id: "R06", upazila: "Begumganj", road: "Bangla Bazar–Padipara", issue: "Potholes and surface erosion", evidence: "B", recurrence: "damage", at: nudge(BEGUMGANJ, 1), precision: "approx", locationNote: AX },
  { id: "R07", upazila: "Sonaimuri", road: "Amisha Para–Padi Para", issue: "Potholes and road deterioration", evidence: "B", recurrence: "damage", at: nudge(SONAIMURI, 0), precision: "approx", locationNote: AX },
  { id: "R08", upazila: "Begumganj", road: "Rajganj–Bangla Bazar", issue: "Poor road surface", evidence: "B", recurrence: "damage", at: nudge(BEGUMGANJ, 2), precision: "approx", locationNote: AX },
  { id: "R09", upazila: "Sadar", road: "Bahadurpur–Gopinathpur", issue: "Poor road surface", evidence: "B", recurrence: "damage", at: nudge(SADAR, 6), precision: "approx", locationNote: AX },
  { id: "R10", upazila: "Sadar", road: "Krishnarampur Board Office", issue: "Poor road surface", evidence: "B", recurrence: "damage", at: nudge(SADAR, 8), precision: "approx", locationNote: AX },
  { id: "R11", upazila: "Senbagh", road: "Chhatar Paiya–Dumurua", issue: "Unsafe travel, damaged surface", evidence: "B", recurrence: "damage", at: nudge(SENBAGH, 0), precision: "approx", locationNote: AX },
  { id: "R12", upazila: "Chatkhil", road: "Gasherkhil–Sadur Khil, Ch. 0–472 m (Road ID 475104013)", issue: "Periodic maintenance contract: M/S Lovely Enterprise, ৳19,76,965.20, signed 19 Jul 2026, proposed completion 28 Sep 2026", evidence: "A", recurrence: "repair", at: nudge(CHATKHIL, 2), precision: "approx", locationNote: AX },
  { id: "R13", upazila: "Chatkhil", road: "Chatkhil emergency evacuation road, 11.67 km", issue: "Rehabilitation and box culvert reconstruction: B-STRONG/LGED, M/S Riasat & Brothers, ৳9,01,60,803.19, awarded 11 Aug 2026, signed 31 Aug 2026, completion 24 Apr 2028", evidence: "A", recurrence: "repair", at: nudge(CHATKHIL, 3), precision: "approx", locationNote: AX },
  { id: "R14", upazila: "Companiganj", road: "Sonagazi–Olamabazar–Chardarbeshpur–Companiganj, 10th and 18th km", issue: "Damaged pavement repair and rigid pavement tender", evidence: "A", recurrence: "repair", at: nudge(COMPANIGANJ, 0), precision: "approx", locationNote: AX },
  { id: "R15", upazila: "Hatiya", road: "Bhuiyarhat–Jahajmara", issue: "Soil investigation, CBR, feasibility and design", evidence: "A", recurrence: "planned", at: nudge(HATIYA, 0), precision: "approx", locationNote: AX },
  { id: "R16", upazila: "Hatiya", road: "Jahajmara–Moktaria Ghat", issue: "Soil investigation and feasibility/design procurement", evidence: "A", recurrence: "planned", at: nudge(HATIYA, 1), precision: "approx", locationNote: AX },
  { id: "R17", upazila: "Subarnachar", road: "Sonapur Bazar–Banglabazar–Subarnachar Upazila HQ", issue: "Soil investigation, CBR and design procurement", evidence: "A", recurrence: "planned", at: nudge(SUBARNACHAR, 0), precision: "approx", locationNote: AX },
  { id: "R18", upazila: "Subarnachar", road: "Rural road rehabilitation, 16.63 km", issue: "LGED improvement project award listing (৳18.98 crore, U.T. Mong, per ProcureIndex)", evidence: "C", recurrence: "planned", at: nudge(SUBARNACHAR, 1), precision: "approx", locationNote: AX },
  { id: "R19", upazila: "Sonaimuri", road: "Kachihata–Thanar Hat–Amanullahpur–Amishapara, 14.19 km", issue: "Improvement project", evidence: "C", recurrence: "planned", at: nudge(SONAIMURI, 1), precision: "approx", locationNote: AX },
  { id: "R20", upazila: "Begumganj", road: "Bangla Bazar–Rajgonj, 7.245 km", issue: "LGED improvement package", evidence: "C", recurrence: "planned", at: nudge(BEGUMGANJ, 3), precision: "approx", locationNote: AX },
  { id: "R21", upazila: "Sadar", road: "Karamullah–Underchar–Fazumiarhat–Lauranch Khasher Hat", issue: "Widening, strengthening, RCC pavement and culverts (৳21.35 crore, EK Enterprise JV, per ProcureIndex)", evidence: "C", recurrence: "planned", at: nudge(SADAR, 7), precision: "approx", locationNote: AX },
  { id: "R22", upazila: "Hatiya", road: "Afajia–Ramcharan Bazar", issue: "Widening and strengthening procurement listing", evidence: "C", recurrence: "planned", at: nudge(HATIYA, 2), precision: "approx", locationNote: AX },
  { id: "R23", upazila: "Hatiya", road: "Burir Char UP Office–Sagoria Bazar–Chowmuhani Bazar", issue: "Widening and strengthening procurement listing", evidence: "C", recurrence: "planned", at: nudge(HATIYA, 3), precision: "approx", locationNote: AX },
  { id: "R24", upazila: "Subarnachar", road: "Bishow Beri–FWC–Chowrasta Bazar", issue: "Connecting-road improvement listing", evidence: "C", recurrence: "planned", at: nudge(SUBARNACHAR, 2), precision: "approx", locationNote: AX },
];

/** Not one of the 24, but named in the dossier as the best candidate for tracking future repair durability (Case 03). */
export const WATCHLIST: RoadCase = {
  id: "W01", upazila: "Begumganj / Sonaimuri", road: "Begumganj–Sonaimuri–Ramganj Regional Highway (R-142), 4th, 5th, 6th and 10th km",
  issue: "2026–27 RHD tender to restore damaged pavement by sealcoat; candidate for tracking repair durability",
  evidence: "A", recurrence: "repair", at: [91.04, 23.06], precision: "osm",
  locationNote: "OSM geometry of R142 (the whole highway is drawn); the 4th, 5th, 6th and 10th km chainage points are not located.",
};

export const ALL_CASES: RoadCase[] = [...ROADS, WATCHLIST];

export type Hotspot = {
  name: string;
  /** Matches an OSM road name that is drawn as a real line, otherwise it is listed but not mapped. */
  osmNames?: string[];
};

/** Areas reported with waterlogging after heavy rain (July 2025). Only those with a real OSM road are drawn. */
export const WATERLOGGING: Hotspot[] = [
  { name: "Stadium Para", osmNames: ["Stadium road"] },
  { name: "DC Road", osmNames: ["DC Office Road"] },
  { name: "Jail Road" },
  { name: "Horinarayanpur" },
  { name: "Lokkhinorayanpur" },
  { name: "Alipur" },
  { name: "Housing Estate", osmNames: ["New Housing Road"] },
  { name: "Islamia Road", osmNames: ["Al-Jamiatul Islamia Road, Maijdee"] },
  { name: "Town Hall Mor" },
  { name: "Pour Bazar Road" },
  { name: "Municipal Market area" },
];

export const HOSPITAL_ROAD_SPEND = [
  { period: "2018", work: "Initial construction", lakh: 179, counted: true },
  { period: "FY 2024–25", work: "Repair contract", lakh: 21.29, counted: true },
  { period: "FY 2024–25", work: "Further carpeting", lakh: 20.95, counted: true },
  { period: "FY 2025–26", work: "Further repair", lakh: 5.99, counted: true },
  { period: "FY 2026–27", work: "Renovation allocation, 3 packages", lakh: 75, counted: false },
] as const;

export const HOSPITAL_TOTAL_LAKH = HOSPITAL_ROAD_SPEND.filter((r) => r.counted).reduce((a, r) => a + r.lakh, 0); // 227.23
export const HOSPITAL_REPAIR_LAKH = HOSPITAL_ROAD_SPEND.filter((r) => r.counted && r.period !== "2018").reduce((a, r) => a + r.lakh, 0); // 48.23

export const DISTRICT_FACTS = {
  lgedUrgentKm: 9079,
  lgedBreakdown: [
    { label: "Paved", value: 3509, color: "#fb923c" },
    { label: "Brick-paved", value: 209, color: "#facc15" },
    { label: "Earthen", value: 5310, color: "#a78bfa" },
  ],
  lgedNeedCrore: 600,
  lgedRepairedKm: 180,
  lgedRepairedCrore: 109,
  municipalityDamagedKm: 112,
  municipalityNetworkKm: 196,
  municipalityRepairedKm: 84,
  municipalityNeedCrore: 500,
  floodDamagedKm: 3671,
  floodBridges: 71,
  floodCulverts: 178,
  floodCrore: 1169,
  procurement: { crore: 470, contracts: 258, firms: 163, medianLakh: 83.9 },
};

export const FLOOD_DRAINAGE_LOG = [
  { date: "Sep 2024", area: "Begumganj, Sonaimuri, Chatkhil, Sadar", text: "Flood-damaged roads, bridges and culverts", source: "Daily Star" },
  { date: "Apr 2025", area: "Noakhali Municipality", text: "Long-term drain maintenance and sewage problems", source: "Daily Star" },
  { date: "Jul 2025", area: "Maijdee and other low-lying areas", text: "Prolonged waterlogging after heavy rain; blocked drains, canal encroachment, waste dumping, box culverts obstructing flow", source: "BSS" },
  { date: "Dec 2025", area: "Municipality, nine wards", text: "63 km drainage network; ৳65 lakh spent on cleaning last fiscal year against ৳500 crore estimated for rehabilitation", source: "Daily Star" },
  { date: "Jul 2026", area: "Hospital Road, Maijdee", text: "Sealcoat peeled one day after completion; contractor blamed rainfall", source: "Dhaka Tribune / T TIMES" },
] as const;

export const KNOWN_UNKNOWN: Array<[string, "yes" | "no" | "partly"]> = [
  ["Is road deterioration a district-wide issue?", "yes"],
  ["Are roads repeatedly repaired? (strongest case: Hospital Road)", "yes"],
  ["Are large infrastructure budgets being awarded?", "yes"],
  ["Are all payments verified?", "no"],
  ["Are all contractors' performance records available?", "no"],
  ["Can we establish why each road fails?", "no"],
  ["Can we identify every recurring failure?", "no"],
];

export const WORKSTREAMS = [
  ["Repeat road repairs", "Road-wise repair history 2018–2026"],
  ["Public expenditure", "Tender amounts, contractor, bills, completion certificates"],
  ["Flood-related damage", "2024 and 2025 damage locations and recovery"],
  ["Drainage failures", "Canals, culverts, waterlogging and road deterioration"],
  ["Construction quality", "Material tests, specifications, inspection, defect liability"],
] as const;

export const RECORD_REQUESTS = [
  ["LGED Noakhali", "Road inventory, road IDs, condition surveys, annual maintenance plans"],
  ["RHD Noakhali Road Division", "Chainage-wise repair history, work orders, completion reports"],
  ["Noakhali Municipality", "Ward-wise road repair records and Hospital Road contract documents"],
  ["Upazila Parishads", "Rural road repair and maintenance expenditure"],
  ["District administration", "2024–26 flood damage assessments"],
  ["LGED and municipality", "Measurement books, bills, quality tests, defect-liability records"],
] as const;

export const SOURCES = [
  "The Daily Star: Noakhali road repair crisis (July 2025) and municipality reports (July 2026, December 2025)",
  "The Daily Star: 3,671 km of flood-damaged roads (2024)",
  "Dhaka Tribune and T TIMES: Hospital Road sealcoat failure",
  "Bangladesh e-GP procurement portal (eprocure.gov.bd): LGED and RHD award records",
  "ProcureIndex: 2026 LGED Noakhali aggregate (not an audited expenditure statement)",
  "BSS: July 2025 Maijdee waterlogging",
];
