import type { LucideIcon } from "lucide-react";
import {
  AirVent, Anchor, Axe, Bath, Building2, CarFront, ChefHat, CloudHail, Construction, DoorOpen, Droplets, Fence, Flame,
  Gavel, Hammer, Home, House, HousePlus, Key, Landmark, Layers, LayoutGrid, Leaf, PaintRoller, Plug, Receipt, Ruler,
  Scale, Shovel, Sparkles, Sun, Trees, Warehouse, Waves, Wind, Wrench, Zap, FileWarning, Scroll, Zap as Bolt,
  Thermometer, Columns3, Store, Truck, BrickWall, Shield, Fan, Siren,
} from "lucide-react";

/** Six tag families, colored with the validated categorical palette (slot order matters for color-blind safety).
 *  Color is never the only signal: every tag also shows its icon and label. */
export const FAMILIES = {
  build: { label: "Building", light: "#2a78d6", dark: "#3987e5" },
  exterior: { label: "Exterior", light: "#eb6834", dark: "#d95926" },
  systems: { label: "Systems", light: "#1baf7a", dark: "#199e70" },
  outdoor: { label: "Outdoor", light: "#eda100", dark: "#c98500" },
  realestate: { label: "Real estate", light: "#e87ba4", dark: "#d55181" },
  storm: { label: "Storm & damage", light: "#008300", dark: "#008300" },
} as const;
export type Family = keyof typeof FAMILIES;

const TAGS: Record<string, [Family, LucideIcon]> = {
  new_construction: ["build", HousePlus], house_framing: ["build", Ruler], garage_framing: ["build", Warehouse],
  addition: ["build", LayoutGrid], deck: ["build", Layers], kitchen: ["build", ChefHat], bath: ["build", Bath],
  remodel: ["build", Hammer], cabinets_counters: ["build", Columns3], drywall: ["build", Construction],
  multifamily: ["build", Building2], commercial_fitout: ["build", Store], demolition: ["build", Axe],
  mobile_home: ["build", Truck],
  roofing: ["exterior", Home], siding: ["exterior", BrickWall], windows_doors: ["exterior", DoorOpen],
  garage_door: ["exterior", Warehouse], gutters: ["exterior", Droplets], painting: ["exterior", PaintRoller],
  insulation: ["exterior", Thermometer],
  hvac: ["systems", AirVent], plumbing: ["systems", Wrench], water_heater: ["systems", Flame],
  electrical: ["systems", Plug], generator: ["systems", Zap], ev_charger: ["systems", CarFront], solar: ["systems", Sun],
  pool: ["outdoor", Waves], fence: ["outdoor", Fence], landscaping: ["outdoor", Leaf], concrete: ["outdoor", Shovel],
  foundation_repair: ["outdoor", Shield], tree_service: ["outdoor", Trees], dock_marine: ["outdoor", Anchor],
  flooring: ["build", LayoutGrid],
  re_sale: ["realestate", Key], re_violation: ["realestate", FileWarning], re_tax_delinquent: ["realestate", Receipt],
  re_foreclosure: ["realestate", Gavel], re_probate: ["realestate", Scroll], re_eviction: ["realestate", Scale],
  re_expired: ["realestate", Landmark], re_listing: ["realestate", House], re_fsbo: ["realestate", Sparkles],
  re_vacant: ["realestate", House], re_absentee: ["realestate", Key], re_subdivision: ["realestate", LayoutGrid],
  storm_hail: ["storm", CloudHail], storm_wind: ["storm", Wind], storm_flood: ["storm", Waves],
  fire_water_restoration: ["storm", Siren],
};

export function tagMeta(tag: string | null | undefined): { family: Family; Icon: LucideIcon } {
  const hit = tag ? TAGS[tag] : undefined;
  return hit ? { family: hit[0], Icon: hit[1] } : { family: "build", Icon: Bolt };
}

export function familyColor(family: Family): string {
  const dark = document.documentElement.classList.contains("dark");
  return dark ? FAMILIES[family].dark : FAMILIES[family].light;
}

export const TRADE_ICONS: Record<string, LucideIcon> = {
  hammer: Hammer, home: Home, ruler: Ruler, deck: Layers, wrench: Wrench, sink: Bath, roof: Home, window: DoorOpen,
  fan: Fan, pipe: Wrench, bolt: Plug, sun: Sun, pool: Waves, fence: Fence, leaf: Leaf, brick: BrickWall,
  brush: PaintRoller, tiles: LayoutGrid, shield: Thermometer, drop: Droplets, tree: Trees, anchor: Anchor,
  flame: Flame, bulldozer: Axe, truck: Truck, key: Key, chart: Landmark,
};
