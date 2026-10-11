export type Tag = { key: string; label: string };

export type Signal = {
  id: number; kind: string; kind_label: string; title: string; tag: string; tag_label: string; tags: Tag[];
  address: string | null; city: string | null; state: string | null; zip: string | null;
  lat: number | null; lng: number | null; value: number | null; posted_at: string | null; due_at: string | null;
  contractor: string | null; commercial: boolean; url: string | null;
  description?: string | null; permit_type?: string | null; owner_name?: string | null; contact_name?: string | null;
  phone?: string | null; email?: string | null; source_id?: string; classified_by?: string; confidence?: number;
  facts?: Record<string, unknown>;
};

export type PropertyInfo = {
  id: number; address: string; city: string | null; state: string | null; zip: string | null;
  lat: number | null; lng: number | null; motivation: number; sell_probability: number; distress: string[];
  factors: string[]; absentee: boolean | null; vacant: boolean | null; year_built: number | null; sqft: number | null;
  est_value: number | null; equity_est: number | null; parcel_id?: string | null; owner_name?: string | null;
  owner_mailing_address?: string | null; assessed_value?: number | null; last_sale_date?: string | null;
  last_sale_price?: number | null; mortgage_est?: number | null;
};

export type Prediction = {
  tag: string; tag_label: string; window_start: string; window_end: string; probability: number; reason: string;
};

export type Lead = {
  id: number; type: "signal" | "prediction" | "property"; status: string; status_label: string; score: number;
  reasons: string[]; trade: string | null; trade_label: string | null; created_at: string; follow_up_at: string | null;
  value_won: number | null; locked: boolean; signal: Signal | null; property: PropertyInfo | null; prediction?: Prediction;
};

export type NextJob = {
  trade: string; trade_label: string; tag_label: string; window_start: string; window_end: string;
  probability: number; reason: string; yours: boolean;
};

export type LeadDetail = Lead & {
  history?: Signal[]; next_jobs?: NextJob[]; brief?: Brief | null;
  contacts?: { id: number; name: string | null; phones: Phone[]; emails: string[]; mailing_address: string | null }[];
  activities: { id: number; kind: string; body: string; created_at: string; user_id: number | null }[];
};

export type Phone = { number: string; type: string | null; dnc: boolean; litigator: boolean };
export type Brief = { source: string; summary: string; why_now: string; opener: string; talking_points: string[] };

export type Plan = {
  key: string; label: string; monthly: number; annual: number; tagline: string; highlights: string[];
  trades: number; territories: number; seats: number; credits: number; features: string[]; founding_monthly: number;
};

export type Trade = { key: string; label: string; group: "trades" | "realestate"; icon: string; ticket: number };

export type Me = {
  user: { id: number; email: string; name: string | null; phone: string | null; is_admin: boolean; xp: number;
    level: { level: number; xp: number; floor: number; next: number | null; progress: number }; streak: number; badges: string[] };
  org: { id: number; name: string; mode: string; trades: string[]; plan: string; plan_status: string;
    trial_ends_at: string | null; credits: number; founding_member: boolean; referral_code: string;
    base_lat: number | null; base_lng: number | null; settings: Record<string, any>; role: string; has_billing: boolean };
  plan: { key: string; label: string; features: string[]; trades: number; territories: number; seats: number;
    monthly_credits: number; lead_delay_days: number; monthly_lead_cap: number | null; max_radius_miles: number };
  usage: { leads_this_month: number; territories: number; seats: number };
  orgs: { id: number; name: string }[];
  digest_hour: number;
};

export type Catalog = {
  trades: Trade[]; tags: Record<string, string>; kinds: Record<string, string>; statuses: Record<string, string>;
  plans: Plan[];
};

export type Territory = { id: number; name: string; kind: string; data: any; trades: string[]; exclusive: boolean };
export type Coverage = { fips: string; name: string; coverage: string; sources: { id: string; name: string; kind: string; status: string }[] };

export type Stats = {
  new_24h: number; hot: number; predicted: number; follow_ups_due: number; by_status: Record<string, number>;
  won_this_month: number; pipeline_value: number; monthly_goal: number | null;
  radar: { tag: string; label: string; count: number }[]; next_drop_at: string; credits: number;
};

export type GeoResult = { type: "zip" | "city" | "county"; id: string; label: string; lat: number; lng: number; county_fips?: string | null };
