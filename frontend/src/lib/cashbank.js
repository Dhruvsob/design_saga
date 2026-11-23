/**
 * Cash / Bank pairing rules shared by every Money In / Money Out form.
 * Mirrors backend core/finance.validate_method_account: the default chart
 * flags Cash and Petty Cash with is_bank so they appear in pickers, so the
 * flag alone never proves an account is a real bank.
 */
const CASH_NAMES = new Set(["cash", "petty cash"]);
// Holds value but is not money you can spend (owner data, 2026-11-23: Gold and
// an equity "drawings" account were flagged as banks and offered in pickers).
const NOT_CASH = /^(investments?\b|gold\b|advance to -|loan from -|accounts (receivable|payable)|input gst|fixed assets|inventory|security deposits?|vendor advances|gst payable|tds)/i;

export const isCashAccount = (a) => CASH_NAMES.has(String(a?.name || "").trim().toLowerCase());
export const isBankAccount = (a) => Boolean(a?.is_bank) && !isCashAccount(a);
export const isCardAccount = (a) => Boolean(a?.is_card) && a?.type === "liability" && a?.active !== false;
/** Cash in hand or a bank: the only accounts money can be received into or paid from. */
export const isMoneyAccount = (a) => Boolean(a) && a.active !== false
  && (a.type === undefined || a.type === "asset")
  && Boolean(a.is_bank || isCashAccount(a))
  && !NOT_CASH.test(String(a.name || ""));
export const moneyAccounts = (accounts) => (accounts || []).filter(isMoneyAccount);
export const cardAccounts = (accounts) => (accounts || []).filter(isCardAccount);
export const methodForAccount = (a) => (isCardAccount(a) ? "credit_card" : isCashAccount(a) ? "cash" : "bank_transfer");

/** First account compatible with the method: Cash for "cash", a real bank otherwise. */
export function compatibleAccount(accounts, method) {
  if (method === "credit_card") return (accounts || []).find(isCardAccount);
  return (accounts || []).find((a) => (method === "cash" ? isCashAccount(a) : isBankAccount(a) && isMoneyAccount(a)));
}
