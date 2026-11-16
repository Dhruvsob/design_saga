import { useState } from "react";
import { toast } from "sonner";
import { IdentificationCard } from "@phosphor-icons/react";
import api from "../lib/api";
import { errText } from "../lib/errors";

/**
 * For a login with no employee record (typically the studio owner).
 * canCreate: the person may create their own record (employees.create);
 * otherwise they are told who can do it.
 */
export default function CreateMyProfile({ canCreate, onCreated, compact = false }) {
  const [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/employees/me", {});
      toast.success(data?.created
        ? `Employee profile ${data.employee?.employee_id || ""} created. Attendance and leave now work for you.`.replace("  ", " ")
        : "Your login is now linked to your employee profile.");
      onCreated && onCreated(data);
    } catch (e) {
      toast.error(errText(e, "Could not create your employee profile"));
      setBusy(false);
    }
  };
  return (
    <div className={`border border-[var(--line)] rounded-md ${compact ? "p-3" : "p-4"} bg-white`} data-testid="create-my-profile">
      <div className="flex items-center gap-2 text-xs text-[var(--ink-2)]"><IdentificationCard size={14} /> Your attendance</div>
      <p className="text-sm mt-1">
        {canCreate
          ? "Your login has no employee profile yet, so your own check-in and leave are not tracked."
          : "Attendance is not set up for your login yet. Ask your administrator to add your employee profile."}
      </p>
      {canCreate && (
        <button type="button" className="btn-primary text-xs mt-2" onClick={create} disabled={busy} data-testid="create-my-profile-btn">
          {busy ? "Creating…" : "Create my employee profile"}
        </button>
      )}
    </div>
  );
}
