import { useEffect, useRef, useState } from "react";
import { Backspace, LockKey, ShieldCheck, SignOut, X } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";

const cleanPin = (value) => value.replace(/\D/g, "").slice(0, 6);

export function PinLockOverlay() {
  const { user, pinLocked, unlockPin, logout } = useAuth();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (pinLocked) {
      setPin("");
      setError("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [pinLocked]);

  if (!user || !user.app_pin_enabled || !pinLocked) return null;

  const submit = async (event) => {
    event?.preventDefault();
    if (pin.length !== 6) return setError("Enter your six-digit PIN.");
    setBusy(true); setError("");
    try {
      await unlockPin(pin);
      setPin("");
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not unlock the ERP.");
      setPin("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    } finally { setBusy(false); }
  };

  const addDigit = (digit) => {
    if (busy) return;
    setError("");
    setPin((current) => `${current}${digit}`.slice(0, 6));
    inputRef.current?.focus();
  };

  return (
    <div className="fixed inset-0 z-[1000] bg-[#F7F6F2] flex items-center justify-center p-5" data-testid="app-pin-lock">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-[#E5E5E5] shadow-xl p-7">
        <div className="w-12 h-12 mx-auto mb-5 flex items-center justify-center bg-[#0A0A0A] text-white">
          <LockKey size={23} weight="fill" />
        </div>
        <div className="overline text-center text-[#8B7F6A]">APP LOCKED</div>
        <h1 className="font-display font-bold text-3xl text-center mt-2">Welcome back, {user.name?.split(" ")[0] || "there"}.</h1>
        <p className="text-sm text-[#5C5C5C] text-center mt-2 mb-6">
          Enter your personal six-digit PIN. The ERP locks after one minute without activity.
        </p>
        <input
          ref={inputRef}
          type="password"
          inputMode="numeric"
          autoComplete="off"
          maxLength={6}
          value={pin}
          onChange={(event) => { setError(""); setPin(cleanPin(event.target.value)); }}
          className="input-flat w-full text-center font-mono text-2xl h-14"
          aria-label="Six-digit App PIN"
          data-testid="app-pin-input"
        />
        <div className="grid grid-cols-3 gap-2 mt-4" aria-label="PIN keypad">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((digit) => (
            <button key={digit} type="button" onClick={() => addDigit(String(digit))}
              className="h-11 border border-[#E5E5E5] bg-white hover:bg-[#F7F6F2] font-mono font-semibold">
              {digit}
            </button>
          ))}
          <span />
          <button type="button" onClick={() => addDigit("0")}
            className="h-11 border border-[#E5E5E5] bg-white hover:bg-[#F7F6F2] font-mono font-semibold">0</button>
          <button type="button" onClick={() => setPin((current) => current.slice(0, -1))}
            className="h-11 border border-[#E5E5E5] bg-white hover:bg-[#F7F6F2] flex items-center justify-center"
            aria-label="Delete last digit"><Backspace size={18} /></button>
        </div>
        {error && <div className="text-xs text-[#B4001C] text-center mt-3" role="alert">{error}</div>}
        <button className="btn-primary w-full justify-center mt-4" disabled={busy || pin.length !== 6} data-testid="app-pin-unlock">
          <LockKey size={15} /> {busy ? "Unlocking..." : "Unlock"}
        </button>
        <button type="button" onClick={logout} className="btn-ghost w-full justify-center mt-2 text-xs">
          <SignOut size={14} /> Sign out instead
        </button>
      </form>
    </div>
  );
}

export function PinSecurityDialog({ onClose }) {
  const { user, setupPin, lockNow, disablePin } = useAuth();
  const enabled = Boolean(user?.app_pin_enabled);
  const [mode, setMode] = useState(enabled ? "summary" : "setup");
  const [currentPin, setCurrentPin] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async (event) => {
    event.preventDefault();
    if (enabled && currentPin.length !== 6) return setError("Enter your current six-digit PIN.");
    if (pin.length !== 6) return setError("Choose exactly six digits.");
    if (pin !== confirmPin) return setError("The new PINs do not match.");
    setBusy(true); setError("");
    try {
      await setupPin(pin, enabled ? currentPin : null);
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not save the App PIN.");
    } finally { setBusy(false); }
  };

  const remove = async (event) => {
    event.preventDefault();
    if (currentPin.length !== 6) return setError("Enter your current six-digit PIN.");
    setBusy(true); setError("");
    try {
      await disablePin(currentPin);
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not disable App Lock.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[600] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md bg-white border border-[#E5E5E5] shadow-2xl p-6" onClick={(event) => event.stopPropagation()} data-testid="pin-security-dialog">
        <div className="flex items-start justify-between gap-3 mb-5">
          <div>
            <div className="overline text-[#8B7F6A]">PERSONAL SECURITY</div>
            <h2 className="font-display font-bold text-2xl mt-1">App Lock</h2>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close App Lock settings"><X size={16} /></button>
        </div>

        {mode === "summary" && (
          <div>
            <div className="flex items-start gap-3 py-4 border-y border-[#E5E5E5]">
              <ShieldCheck size={24} className="text-[#1D633E] shrink-0" weight="fill" />
              <div>
                <div className="font-semibold">Six-digit PIN enabled</div>
                <div className="text-xs text-[#5C5C5C] mt-1">This account locks after one minute without activity. Each user has a separate PIN.</div>
              </div>
            </div>
            <div className="flex flex-wrap justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setMode("disable")}>Disable</button>
              <button className="btn-ghost" onClick={() => setMode("change")}>Change PIN</button>
              <button className="btn-primary" onClick={() => { lockNow(); onClose(); }}>
                <LockKey size={14} /> Lock now
              </button>
            </div>
          </div>
        )}

        {(mode === "setup" || mode === "change") && (
          <form onSubmit={save} className="space-y-3">
            <p className="text-sm text-[#5C5C5C]">Use six digits that employees cannot guess. Do not reuse your phone PIN or birth date.</p>
            {mode === "change" && (
              <label className="block"><span className="text-xs text-[#5C5C5C]">Current PIN</span>
                <input type="password" inputMode="numeric" maxLength={6} autoComplete="off" className="input-flat w-full mt-1"
                  value={currentPin} onChange={(event) => setCurrentPin(cleanPin(event.target.value))} /></label>
            )}
            <label className="block"><span className="text-xs text-[#5C5C5C]">New six-digit PIN</span>
              <input type="password" inputMode="numeric" maxLength={6} autoComplete="off" className="input-flat w-full mt-1"
                value={pin} onChange={(event) => setPin(cleanPin(event.target.value))} data-testid="pin-setup-new" /></label>
            <label className="block"><span className="text-xs text-[#5C5C5C]">Confirm PIN</span>
              <input type="password" inputMode="numeric" maxLength={6} autoComplete="off" className="input-flat w-full mt-1"
                value={confirmPin} onChange={(event) => setConfirmPin(cleanPin(event.target.value))} data-testid="pin-setup-confirm" /></label>
            {error && <div className="text-xs text-[#B4001C]" role="alert">{error}</div>}
            <div className="flex justify-end gap-2 pt-2">
              {enabled && <button type="button" className="btn-ghost" onClick={() => setMode("summary")}>Back</button>}
              <button className="btn-primary" disabled={busy}>{busy ? "Saving..." : (enabled ? "Save new PIN" : "Enable App Lock")}</button>
            </div>
          </form>
        )}

        {mode === "disable" && (
          <form onSubmit={remove} className="space-y-3">
            <p className="text-sm text-[#5C5C5C]">Enter your current PIN to disable the one-minute lock on this account.</p>
            <label className="block"><span className="text-xs text-[#5C5C5C]">Current PIN</span>
              <input type="password" inputMode="numeric" maxLength={6} autoComplete="off" className="input-flat w-full mt-1"
                value={currentPin} onChange={(event) => setCurrentPin(cleanPin(event.target.value))} /></label>
            {error && <div className="text-xs text-[#B4001C]" role="alert">{error}</div>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className="btn-ghost" onClick={() => setMode("summary")}>Back</button>
              <button className="btn-primary bg-[#B4001C]" disabled={busy}>{busy ? "Disabling..." : "Disable App Lock"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
