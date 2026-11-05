/**
 * Cash / Bank pairing rules shared by every Money In / Money Out form.
 * Mirrors backend core/finance.validate_method_account: the default chart
 * flags Cash and Petty Cash with is_bank so they appear in pickers, so the
 * flag alone never proves an account is a real bank.
 */
const CASH_NAMES = new Set(["cash", "petty cash"]);

export const isCashAccount = (a) => CASH_NAMES.has(String(a?.name || "").trim().toLowerCase());
export const isBankAccount = (a) => Boolean(a?.is_bank) && !isCashAccount(a);
export const methodForAccount = (a) => (isCashAccount(a) ? "cash" : "bank_transfer");

/** First account compatible with the method: Cash for "cash", a real bank otherwise. */
export function compatibleAccount(accounts, method) {
  return (accounts || []).find((a) => (method === "cash" ? isCashAccount(a) : isBankAccount(a)));
}
