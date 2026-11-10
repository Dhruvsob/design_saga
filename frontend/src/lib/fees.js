import { formatINR } from "./format";

export const FEE_LABELS = {
  lump_sum: "Lump Sum",
  percentage_consultancy: "Consultancy %",
  turnkey: "Turnkey",
  per_sqft: "Per Sq Ft",
};

/** Calculated fee from a form/project object, or null when inputs are incomplete. */
export function feeCalc(f) {
  const fst = f.fee_structure_type;
  if (fst === "lump_sum") return f.fee_lump_sum_amount ? Number(f.fee_lump_sum_amount) : null;
  if (fst === "percentage_consultancy") {
    const v = Number(f.fee_project_value || 0), pct = Number(f.fee_percentage || 0);
    return v && pct ? Math.round(v * pct / 100) : null;
  }
  if (fst === "turnkey") return f.fee_contract_value ? Number(f.fee_contract_value) : null;
  if (fst === "per_sqft") {
    const area = Number(f.site_area_sqft || 0), rate = Number(f.fee_rate_per_sqft || 0);
    return area && rate ? area * rate : null;
  }
  return null;
}

/** One-line fee summary for a project, or null when no fee type is set. */
export function projectFeeDisplay(p) {
  const fst = p.fee_structure_type;
  if (!fst) return null;
  const label = FEE_LABELS[fst] || fst;
  if (fst === "lump_sum" && p.fee_lump_sum_amount) return `${label} · ${formatINR(p.fee_lump_sum_amount)}`;
  if (fst === "percentage_consultancy" && p.fee_percentage) {
    const calc = p.fee_project_value ? formatINR(p.fee_project_value * p.fee_percentage / 100) : null;
    return `${label} · ${p.fee_percentage}%${calc ? ` = ${calc}` : ""}`;
  }
  if (fst === "turnkey" && p.fee_contract_value) return `${label} · ${formatINR(p.fee_contract_value)}`;
  if (fst === "per_sqft" && p.fee_rate_per_sqft) {
    const calc = p.site_area_sqft ? formatINR(p.site_area_sqft * p.fee_rate_per_sqft) : null;
    return `${label} · ₹${p.fee_rate_per_sqft}/sq ft${calc ? ` = ${calc}` : ""}`;
  }
  return label;
}
