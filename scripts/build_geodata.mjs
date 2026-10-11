// Builds pegasus/data/us_counties.json and us_zips.json from free npm datasets:
//   us-atlas (Census cartographic boundaries, ISC) and zipcodes (BSD).
// Usage: npm i us-atlas@3 zipcodes@8 topojson-client@3 && node scripts/build_geodata.mjs <out_dir>
import { createRequire } from "module";
import { writeFileSync } from "fs";
const require = createRequire(import.meta.url);
const topo = require("topojson-client");
const atlas = require("us-atlas/counties-10m.json");
const { codes } = require("zipcodes/lib/codes.js");

const STATE_FIPS = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL",
"13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA",
"26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC",
"38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT",
"51":"VA","53":"WA","54":"WV","55":"WI","56":"WY","60":"AS","66":"GU","69":"MP","72":"PR","78":"VI"};

const out = process.argv[2] || ".";
const counties = topo.feature(atlas, atlas.objects.counties).features;

function rings(geom) {
  return geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
}
function inRing(lat, lng, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi) inside = !inside;
  }
  return inside;
}
const rows = [];
for (const f of counties) {
  if (!f.geometry) continue;
  let minLat = 90, maxLat = -90, minLng = 180, maxLng = -180, sLat = 0, sLng = 0, n = 0;
  for (const poly of rings(f.geometry)) for (const [lng, lat] of poly[0]) {
    minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
    sLat += lat; sLng += lng; n++;
  }
  const fips = String(f.id).padStart(5, "0");
  const state = STATE_FIPS[fips.slice(0, 2)];
  if (!state) continue;
  rows.push({ fips, name: f.properties.name, state, lat: +(sLat / n).toFixed(4), lng: +(sLng / n).toFixed(4),
              bbox: [+minLat.toFixed(4), +maxLat.toFixed(4), +minLng.toFixed(4), +maxLng.toFixed(4)], geom: f.geometry });
}
const zips = {};
for (const [zip, z] of Object.entries(codes)) {
  if (z.country !== "US" || z.latitude == null) continue;
  let fips = null;
  for (const c of rows) {
    const [a, b, w, e] = c.bbox;
    if (z.latitude < a || z.latitude > b || z.longitude < w || z.longitude > e || c.state !== z.state) continue;
    if (rings(c.geom).some(p => inRing(z.latitude, z.longitude, p[0]))) { fips = c.fips; break; }
  }
  zips[zip] = [z.city, z.state, +z.latitude.toFixed(4), +z.longitude.toFixed(4), fips];
}
writeFileSync(`${out}/us_counties.json`, JSON.stringify(rows.map(({ geom, ...r }) => r)));
writeFileSync(`${out}/us_zips.json`, JSON.stringify(zips));
console.log(`counties=${rows.length} zips=${Object.keys(zips).length} zips_with_county=${Object.values(zips).filter(z => z[4]).length}`);
