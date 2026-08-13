// Human-readable labels for the MARC coded values shown on the collection
// comparison pages (languages, place of publication, format, LC classification).
// Each lookup is case-insensitive on the raw code and falls back to the code
// itself, so uncommon values (and the suppression "Other" bucket) pass through
// unchanged rather than being dropped.

// MARC leader/06 — type of record.
const RECORD_TYPE = {
  a: "Language material",
  c: "Notated music",
  d: "Manuscript music",
  e: "Cartographic",
  f: "Manuscript cartographic",
  g: "Projected medium",
  i: "Nonmusical sound",
  j: "Musical sound",
  k: "Two-dimensional image",
  m: "Computer file",
  o: "Kit",
  p: "Mixed material",
  r: "Three-dimensional object",
  t: "Manuscript language material",
};

// MARC language codes (008/35-37). Common values only; the rest fall back to
// the raw code. Note MARC codes differ from ISO for several languages
// (fre/ger/dut/chi/gre/rum/cze/per…).
const LANGUAGE = {
  eng: "English",
  fre: "French",
  ger: "German",
  spa: "Spanish",
  ita: "Italian",
  rus: "Russian",
  por: "Portuguese",
  chi: "Chinese",
  ara: "Arabic",
  lat: "Latin",
  jpn: "Japanese",
  heb: "Hebrew",
  dut: "Dutch",
  pol: "Polish",
  gre: "Greek, Modern",
  grc: "Greek, Ancient",
  kor: "Korean",
  tur: "Turkish",
  per: "Persian",
  hin: "Hindi",
  san: "Sanskrit",
  swe: "Swedish",
  dan: "Danish",
  nor: "Norwegian",
  fin: "Finnish",
  cze: "Czech",
  hun: "Hungarian",
  rum: "Romanian",
  ukr: "Ukrainian",
  cat: "Catalan",
  yid: "Yiddish",
  vie: "Vietnamese",
  tha: "Thai",
  ind: "Indonesian",
  wel: "Welsh",
  gle: "Irish",
  scr: "Croatian",
  srp: "Serbian",
  bul: "Bulgarian",
  slo: "Slovak",
  slv: "Slovenian",
  zxx: "No linguistic content",
  mul: "Multiple languages",
  und: "Undetermined",
};

// MARC country/place-of-publication codes (008/15-17). U.S. states, Canadian
// provinces, and countries are mixed in this list. Common values only.
const PLACE = {
  // United States (whole) + states
  xxu: "United States",
  alu: "Alabama",
  aku: "Alaska",
  azu: "Arizona",
  aru: "Arkansas",
  cau: "California",
  cou: "Colorado",
  ctu: "Connecticut",
  dcu: "Washington, D.C.",
  deu: "Delaware",
  flu: "Florida",
  gau: "Georgia",
  hiu: "Hawaii",
  idu: "Idaho",
  ilu: "Illinois",
  inu: "Indiana",
  iau: "Iowa",
  ksu: "Kansas",
  kyu: "Kentucky",
  lau: "Louisiana",
  meu: "Maine",
  mdu: "Maryland",
  mau: "Massachusetts",
  miu: "Michigan",
  mnu: "Minnesota",
  msu: "Mississippi",
  mou: "Missouri",
  mtu: "Montana",
  nbu: "Nebraska",
  nvu: "Nevada",
  nhu: "New Hampshire",
  nju: "New Jersey",
  nmu: "New Mexico",
  nyu: "New York",
  ncu: "North Carolina",
  ndu: "North Dakota",
  ohu: "Ohio",
  oku: "Oklahoma",
  oru: "Oregon",
  pau: "Pennsylvania",
  riu: "Rhode Island",
  scu: "South Carolina",
  sdu: "South Dakota",
  tnu: "Tennessee",
  txu: "Texas",
  utu: "Utah",
  vtu: "Vermont",
  vau: "Virginia",
  wau: "Washington",
  wvu: "West Virginia",
  wiu: "Wisconsin",
  wyu: "Wyoming",
  // Canada (whole) + provinces
  xxc: "Canada",
  abc: "Alberta",
  bcc: "British Columbia",
  mbc: "Manitoba",
  onc: "Ontario",
  quc: "Québec",
  // Europe
  xxk: "United Kingdom",
  enk: "England",
  stk: "Scotland",
  wlk: "Wales",
  nik: "Northern Ireland",
  ie: "Ireland",
  fr: "France",
  gw: "Germany",
  it: "Italy",
  sp: "Spain",
  ne: "Netherlands",
  be: "Belgium",
  sw: "Sweden",
  sz: "Switzerland",
  dk: "Denmark",
  no: "Norway",
  fi: "Finland",
  po: "Portugal",
  gr: "Greece",
  au: "Austria",
  hu: "Hungary",
  pl: "Poland",
  rm: "Romania",
  bu: "Bulgaria",
  ru: "Russia (Federation)",
  ur: "Soviet Union",
  un: "Ukraine",
  ic: "Iceland",
  // Asia / Middle East
  cc: "China",
  ja: "Japan",
  ko: "Korea, South",
  ii: "India",
  is: "Israel",
  ir: "Iran",
  tu: "Turkey",
  // Latin America
  mx: "Mexico",
  bl: "Brazil",
  ag: "Argentina",
  cl: "Chile",
  pe: "Peru",
  ck: "Colombia",
  // Other
  at: "Australia",
  nz: "New Zealand",
  sa: "South Africa",
  vp: "Various places",
  xx: "Unknown",
};

// Library of Congress classification — the 21 main classes, keyed by the first
// letter of the call number.
const LC_CLASS = {
  a: "General Works",
  b: "Philosophy & Religion",
  c: "Auxiliary Sciences of History",
  d: "World History",
  e: "American History",
  f: "American & Local History",
  g: "Geography & Anthropology",
  h: "Social Sciences",
  j: "Political Science",
  k: "Law",
  l: "Education",
  m: "Music",
  n: "Fine Arts",
  p: "Language & Literature",
  q: "Science",
  r: "Medicine",
  s: "Agriculture",
  t: "Technology",
  u: "Military Science",
  v: "Naval Science",
  z: "Library Science",
};

// MARC continuing-resources 008/06 — publication status.
const SERIAL_STATUS = {
  c: "Still published",
  d: "Ceased",
  u: "Status unknown",
};

// Serial linking entries: whether a serial points back/forward in a lineage.
const SUCCESSION_LINK = {
  pred: "Continues an earlier title (780)",
  succ: "Continued by a later title (785)",
};

// MARC 785 (succeeding entry) indicator 2 — the kind of title change.
const SUCCESSION_TYPE = {
  "0": "Continued by",
  "1": "Continued in part by",
  "2": "Superseded by",
  "3": "Superseded in part by",
  "4": "Absorbed by",
  "5": "Absorbed in part by",
  "6": "Split into",
  "7": "Merged to form",
  "8": "Changed back to",
};

// MARC 040 origin buckets (see queries.cataloging_source).
// No "OCLC" entry: 040 credits whoever wrote the description, not the utility the
// record travelled through, so OCoLC lands in $a on only 0.06% of records. The
// distribution-channel signal is in 035, not here.
const SOURCE_BUCKET = {
  lc: "Library of Congress",
  self: "This institution",
  // codes that follow the institution's symbol family but aren't confirmed as
  // theirs — kept visibly separate so the chart doesn't imply more than we know
  pod: "Another POD member",
  other: "Some other agency",
  none: "No agency given",
};

// Distinct 040 $d modifying-agency counts. "No 040 field" is kept apart from a
// record whose 040 simply names no modifying agency — they mean different things.
const MOD_DEPTH = {
  no_040: "No 040 field",
  "0": "None",
};

// Cataloging agencies (MARC 040 $a). A mix of MARC Organization Codes and OCLC
// symbols, normalized to upper case by the extract. Only codes we can name with
// confidence are here; the rest fall through as the raw code, which is the point
// of `labeler`'s passthrough. Members' own codes are labeled with the institution
// so the "who cataloged this" reading is obvious.
const AGENCY = {
  // national libraries & government
  dlc: "Library of Congress",
  "dlc-r": "Library of Congress (retrospective)",
  ocolc: "OCLC",
  gpo: "U.S. Government Publishing Office",
  dgpo: "U.S. Government Publishing Office",
  agl: "National Agricultural Library",
  dnlm: "National Library of Medicine",
  nlm: "National Library of Medicine",
  ukm: "British Library",
  ukmgb: "British Library",
  caoonl: "Library and Archives Canada",
  // POD members (both their MARC code and their OCLC symbol)
  rpb: "Brown",
  rbn: "Brown",
  rpjcb: "Brown (John Carter Brown Library)",
  ncd: "Duke",
  ndd: "Duke",
  mh: "Harvard",
  "mh-l": "Harvard (Law School)",
  "mh-hy": "Harvard (Yenching)",
  "mh-mu": "Harvard (Music)",
  "mh-fa": "Harvard (Fine Arts)",
  hls: "Harvard (Law School)",
  hul: "Harvard (University Library)",
  hms: "Harvard (Medical School)",
  hbs: "Harvard (Business School)",
  ddo: "Harvard (Dumbarton Oaks)",
  pu: "Penn",
  pau: "Penn",
  njp: "Princeton",
  "njp-g": "Princeton (Firestone)",
  pul: "Princeton",
  pulea: "Princeton (East Asian)",
  cst: "Stanford",
  "cst-h": "Stanford (Hoover Institution)",
  "cst-law": "Stanford (Law)",
  stf: "Stanford",
  // commercial suppliers & aggregators — the bulk of the long tail
  miaapq: "ProQuest",
  umi: "ProQuest (UMI)",
  eblcp: "ProQuest Ebook Central",
  lexisnexis: "LexisNexis",
  vaalasp: "Alexander Street Press",
  "ukmbam-d": "Adam Matthew Digital",
  migcl: "Gale",
  naxos: "Naxos",
  itfic: "Casalini Libri",
  ydx: "YBP Library Services",
  btcta: "Baker & Taylor",
  "n$t": "EBSCO",
  gw5xe: "Springer",
  e7b: "ebrary",
  mwa: "American Antiquarian Society",
};

// Distribution channels derived from the MARC 035 namespace (see
// queries._CHANNEL_TESTS). These overlap — one record can carry several.
const CHANNEL = {
  any_system: "Any system number",
  oclc: "OCLC / WorldCat",
  rlin: "RLIN (RLG, pre-2006)",
  alma_cz: "Ex Libris Community Zone",
  local_system: "A local library system",
  pod_system: "Another POD member's system",
};

// 035 namespaces that aren't cataloging agencies — union catalogues, knowledge
// bases and local systems. Falls back to the AGENCY table (the two vocabularies
// overlap heavily: DLC, MiAaPQ, VaAlASP and friends appear in both) and then to the
// raw code.
const NAMESPACE = {
  ocolc: "OCLC / WorldCat",
  "ocolc-m": "OCLC master record",
  "ocolc-i": "OCLC institution record",
  "ocolc-p": "OCLC provisional record",
  cstrlin: "RLIN (RLG union catalogue)",
  exlcz: "Ex Libris Community Zone",
  ckb: "Ex Libris knowledge base",
  sirsi: "Sirsi/Symphony (local)",
  puvoyagerbibid: "Voyager (local)",
  pqkb: "ProQuest knowledge base",
  ssid: "ProQuest (SSID)",
  miaaatc: "ProQuest (Ann Arbor)",
  ecco: "Gale ECCO",
  dash: "Harvard DASH repository",
  cotsendb: "Cotsen Children's Library",
  idcotsen: "Cotsen Children's Library",
  hsp: "Historical Society of Pennsylvania",
  caotulas: "University of Toronto",
  hkul: "University of Hong Kong",
  muls: "Minnesota Union List of Serials",
  isjeaiw: "Index to Jewish Periodicals",
};

const labeler = (table) => (code) =>
  table[String(code).toLowerCase()] ?? code;

// Institution code → display name. Institution codes are stored lowercase (they
// identify the org in the lake), and capitalizing the first letter is right for most
// of them — but not for acronyms, which come out as "Jhu" and "Mit". Add an entry
// here for any org whose display name isn't a simple capitalization.
const ORG_NAMES = {
  jhu: "JHU",
  mit: "MIT",
};
export const orgLabel = (org) =>
  ORG_NAMES[org] ??
  (org ? String(org).charAt(0).toUpperCase() + String(org).slice(1) : org);

export const recordTypeLabel = labeler(RECORD_TYPE);
export const languageLabel = labeler(LANGUAGE);
export const placeLabel = labeler(PLACE);
export const lcClassLabel = labeler(LC_CLASS);
export const serialStatusLabel = labeler(SERIAL_STATUS);
export const successionLinkLabel = labeler(SUCCESSION_LINK);
export const successionTypeLabel = labeler(SUCCESSION_TYPE);
export const sourceBucketLabel = labeler(SOURCE_BUCKET);
export const modDepthLabel = labeler(MOD_DEPTH);

// Not `labeler(AGENCY)`: several codes share one institution name (CSt and STF are
// both Stanford, NjP and PUL both Princeton), and the heatmaps take their y-domain
// straight from these labels — a band scale silently collapses duplicates, so two
// rows would land on top of each other. Keeping the code makes every label unique
// and lets a reader check it against _SELF_CODES.
export const agencyLabel = (code) => {
  const name = AGENCY[String(code).toLowerCase()];
  return name ? `${name} (${code})` : code;
};

export const channelLabel = labeler(CHANNEL);

// Same unique-label requirement as agencyLabel: several namespaces resolve to the
// same name (OCoLC, OCoLC-M and OCoLC-I are all WorldCat), and the heatmap y-domain
// comes from these strings, so the code has to stay.
export const namespaceLabel = (code) => {
  const key = String(code).toLowerCase();
  const name = NAMESPACE[key] ?? AGENCY[key];
  return name ? `${name} (${code})` : code;
};
