import { Plus, Trash, ArrowUp, ArrowDown } from "@phosphor-icons/react";
import { formatINR } from "../lib/format";

/**
 * Editor for a consultancy design proposal (letter-style quotation).
 * Mirrors the firm's own proposal: project details, scope, design process,
 * fees & instalments, procurement, communication, optional site coordinator
 * and the signatory. Saved through the normal quotation Save button.
 */

const EVERY = [1, 2, 3, 4, 6, 12];

export function feeSchedule(fee = {}) {
  const paise = (v) => Math.round((Number(v) || 0) * 100);
  const total = paise(fee.total_fee);
  if (total <= 0) return [];
  const advance = Math.min(paise(fee.advance_amount), total);
  const step = paise(fee.instalment_amount);
  const every = Number(fee.instalment_every_months) || 1;
  const rows = [];
  if (advance > 0) rows.push({ label: "Advance on confirmation", month: 0, amount: advance / 100 });
  let balance = total - advance;
  if (balance <= 0) return rows;
  if (step <= 0) {
    rows.push({ label: "Balance fee", month: null, amount: balance / 100 });
    return rows;
  }
  let n = 0;
  while (balance > 0 && n < 120) {
    n += 1;
    const part = Math.min(step, balance);
    rows.push({ label: `Instalment ${n}`, month: n * every, amount: part / 100 });
    balance -= part;
  }
  return rows;
}

export function ProposalDetails({ q, update, tpl, readOnly }) {
  const p = q.proposal || {};
  const setP = (patch) => update({ proposal: { ...p, ...patch } });
  const salutations = tpl?.salutations || ["Mr.", "Ms.", "Mrs.", "Dr.", "M/s.", ""];
  const sc = p.site_coordinator || {};
  const setSC = (patch) => setP({ site_coordinator: { ...sc, ...patch } });

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6" data-testid="proposal-editor">
      <div className="xl:col-span-2 space-y-6">
        <Section title="Client & project" hint="Shown in the greeting and the Project details block.">
          <div className="grid grid-cols-1 sm:grid-cols-[110px_1fr] gap-3">
            <Field label="Title">
              <select aria-label="Salutation" className="input-flat" value={p.salutation ?? "Mr."} disabled={readOnly}
                      onChange={(e) => setP({ salutation: e.target.value })} data-testid="proposal-salutation">
                {salutations.map((s) => <option key={s || "none"} value={s}>{s || "None"}</option>)}
              </select>
            </Field>
            <Field label="Client name in greeting">
              <input className="input-flat" value={p.greeting_name || ""} disabled={readOnly}
                     placeholder={q.client_name || "Client name"} onChange={(e) => setP({ greeting_name: e.target.value })}
                     data-testid="proposal-greeting" />
            </Field>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Location">
              <input className="input-flat" value={q.project_location || ""} disabled={readOnly}
                     onChange={(e) => update({ project_location: e.target.value })} data-testid="proposal-location" />
            </Field>
            <Field label="Area (sq.ft, optional)">
              <input type="number" min="0" className="input-flat" value={q.area_sqft || ""} disabled={readOnly}
                     onChange={(e) => update({ area_sqft: e.target.value === "" ? 0 : Number(e.target.value) })} />
            </Field>
          </div>
          <Field label="Scope (one line)">
            <input className="input-flat" value={p.scope_summary || ""} disabled={readOnly}
                   placeholder="Interior Design Consultancy & Execution Coordination"
                   onChange={(e) => setP({ scope_summary: e.target.value })} data-testid="proposal-scope-summary" />
          </Field>
          <Field label="Introduction">
            <textarea rows={3} className="input-flat" value={p.intro || ""} disabled={readOnly}
                      onChange={(e) => setP({ intro: e.target.value })} />
          </Field>
        </Section>

        <Section title="Scope of work" hint="One service per line, in the order the client should read them.">
          <ListEditor items={q.design_scope || []} onChange={(items) => update({ design_scope: items })}
                      placeholder="e.g. Landscape design" readOnly={readOnly} testid="scope" />
          <details className="mt-3" open={(q.exclusions || []).length > 0}>
            <summary className="text-xs font-semibold text-[#5C5C5C] cursor-pointer">Not included (optional)</summary>
            <div className="mt-2">
              <ListEditor items={q.exclusions || []} onChange={(items) => update({ exclusions: items })}
                          placeholder="e.g. Civil and structural design" readOnly={readOnly} testid="exclusions" />
            </div>
          </details>
        </Section>

        <Section title="Design process & approvals"
                 hint="{revisions} and {renders} in a clause are replaced with the counts below.">
          <div className="grid grid-cols-2 gap-3 max-w-sm">
            <Field label="Extra revisions included">
              <input type="number" min="0" max="20" className="input-flat" value={p.revisions_included ?? 1} disabled={readOnly}
                     onChange={(e) => setP({ revisions_included: Number(e.target.value) || 0 })} data-testid="proposal-revisions" />
            </Field>
            <Field label="Final renders included">
              <input type="number" min="0" max="50" className="input-flat" value={p.renders_included ?? 1} disabled={readOnly}
                     onChange={(e) => setP({ renders_included: Number(e.target.value) || 0 })} />
            </Field>
          </div>
          <ListEditor items={p.process_clauses || []} onChange={(items) => setP({ process_clauses: items })}
                      multiline placeholder="Add a clause" readOnly={readOnly} testid="clauses" />
        </Section>

        <Section title="Procurement & communication">
          <Field label="Material procurement">
            <textarea rows={2} className="input-flat" value={p.procurement_note || ""} disabled={readOnly}
                      onChange={(e) => setP({ procurement_note: e.target.value })} />
          </Field>
          <Field label="Communication">
            <textarea rows={3} className="input-flat" value={p.communication_note || ""} disabled={readOnly}
                      onChange={(e) => setP({ communication_note: e.target.value })} />
          </Field>
          <Field label="Office number">
            <input className="input-flat max-w-xs" inputMode="tel" value={p.office_phone || ""} disabled={readOnly}
                   onChange={(e) => setP({ office_phone: e.target.value })} data-testid="proposal-phone" />
          </Field>
        </Section>

        <Section title="Optional site coordination support">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!sc.enabled} disabled={readOnly}
                   onChange={(e) => setSC({ enabled: e.target.checked })} data-testid="proposal-sc-toggle" />
            Offer a dedicated Site Coordinator
          </label>
          {sc.enabled && (
            <div className="space-y-3 pl-6 border-l-2 border-[#E8E6E1]">
              <Field label="Charge per month (Rs.)">
                <input type="number" min="0" className="input-flat max-w-[200px]" value={sc.monthly_fee || ""} disabled={readOnly}
                       onChange={(e) => setSC({ monthly_fee: Number(e.target.value) || 0 })} data-testid="proposal-sc-fee" />
              </Field>
              <div className="text-xs font-semibold text-[#5C5C5C]">Responsibilities</div>
              <ListEditor items={sc.duties || []} onChange={(items) => setSC({ duties: items })}
                          placeholder="Add a responsibility" readOnly={readOnly} testid="duties" />
              <Field label="Note on limits of the role">
                <textarea rows={3} className="input-flat" value={sc.note || ""} disabled={readOnly}
                          onChange={(e) => setSC({ note: e.target.value })} />
              </Field>
            </div>
          )}
        </Section>
      </div>

      <div className="space-y-6">
        <Section title="Closing & signatory">
          <Field label="Closing line">
            <input className="input-flat" value={p.closing || ""} disabled={readOnly}
                   onChange={(e) => setP({ closing: e.target.value })} />
          </Field>
          <Field label="Signed by">
            <input className="input-flat" value={p.signatory_name || ""} disabled={readOnly}
                   onChange={(e) => setP({ signatory_name: e.target.value })} data-testid="proposal-signatory" />
          </Field>
          <Field label="Designation">
            <input className="input-flat" value={p.signatory_title || ""} disabled={readOnly}
                   onChange={(e) => setP({ signatory_title: e.target.value })} />
          </Field>
        </Section>
        <FeeSummaryCard q={q} />
      </div>
    </div>
  );
}

export function ProposalFees({ q, update, readOnly }) {
  const p = q.proposal || {};
  const fee = p.fee || {};
  const setFee = (patch) => update({ proposal: { ...p, fee: { ...fee, ...patch } } });
  const cost = q.cost || {};
  const schedule = feeSchedule(fee);
  const total = Number(fee.total_fee) || 0;
  const problems = [];
  if (total <= 0) problems.push("Enter the total design fee.");
  if (Number(fee.advance_amount) > total && total > 0) problems.push("The advance is more than the total fee.");
  if (Number(fee.instalment_amount) > total && total > 0) problems.push("The instalment is more than the total fee.");

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6" data-testid="proposal-fees">
      <div className="xl:col-span-2 space-y-6">
        <Section title="Design fee" hint="A fixed professional fee, an advance on confirmation, then regular instalments.">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Total design fee (Rs.)">
              <input type="number" min="0" className="input-flat" value={fee.total_fee || ""} disabled={readOnly}
                     onChange={(e) => setFee({ total_fee: Number(e.target.value) || 0 })} data-testid="fee-total" />
            </Field>
            <Field label="Advance on confirmation (Rs.)">
              <input type="number" min="0" className="input-flat" value={fee.advance_amount || ""} disabled={readOnly}
                     onChange={(e) => setFee({ advance_amount: Number(e.target.value) || 0 })} data-testid="fee-advance" />
            </Field>
            <Field label="Then pay (Rs.)">
              <input type="number" min="0" className="input-flat" value={fee.instalment_amount || ""} disabled={readOnly}
                     onChange={(e) => setFee({ instalment_amount: Number(e.target.value) || 0 })} data-testid="fee-instalment" />
            </Field>
            <Field label="Every">
              <select aria-label="Instalment frequency" className="input-flat" value={fee.instalment_every_months || 2} disabled={readOnly}
                      onChange={(e) => setFee({ instalment_every_months: Number(e.target.value) })} data-testid="fee-every">
                {EVERY.map((m) => <option key={m} value={m}>{m === 1 ? "month" : `${m} months`}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Extra work note">
            <input className="input-flat" value={fee.extra_work_note || ""} disabled={readOnly}
                   onChange={(e) => setFee({ extra_work_note: e.target.value })} />
          </Field>
          <Field label="GST % (leave 0 if not charged)">
            <input type="number" min="0" max="28" className="input-flat max-w-[140px]" value={cost.tax_pct ?? 0} disabled={readOnly}
                   onChange={(e) => update({ cost: { ...cost, tax_pct: Number(e.target.value) || 0 } })} data-testid="fee-gst" />
          </Field>
          {problems.length > 0 && (
            <ul className="text-sm text-[#8F3B00] list-disc ml-5" role="status">
              {problems.map((m) => <li key={m}>{m}</li>)}
            </ul>
          )}
        </Section>

        <Section title={`Payment schedule${schedule.length ? ` · ${schedule.length} payments` : ""}`}
                 hint="Worked out from the fee above. The last instalment takes whatever remains, so the total always matches.">
          {schedule.length === 0 ? (
            <p className="text-sm text-[#6E6A63]">Enter the total fee to see the schedule.</p>
          ) : (
            <div className="overflow-x-auto max-h-[360px] overflow-y-auto border border-[#F0EEE9] rounded">
              <table className="w-full text-sm" data-testid="fee-schedule">
                <thead className="sticky top-0 bg-[#FAF9F6]">
                  <tr className="text-left border-b border-[#E8E6E1]">
                    <th className="py-2 px-3 overline">Payment</th>
                    <th className="py-2 px-3 overline">When</th>
                    <th className="py-2 px-3 overline text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.map((r) => (
                    <tr key={r.label} className="border-b border-[#F5F4F0]">
                      <td className="py-1.5 px-3">{r.label}</td>
                      <td className="py-1.5 px-3 text-[#6E6A63]">
                        {r.month === 0 ? "On confirmation" : r.month ? `Month ${r.month}` : "As agreed"}
                      </td>
                      <td className="py-1.5 px-3 text-right font-mono">{formatINR(r.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
      <FeeSummaryCard q={q} />
    </div>
  );
}

function FeeSummaryCard({ q }) {
  const fee = q.proposal?.fee || {};
  const schedule = feeSchedule(fee);
  const total = Number(fee.total_fee) || 0;
  const tax = Number(q.cost?.tax_pct) || 0;
  const instalments = schedule.filter((r) => r.label.startsWith("Instalment"));
  const lastMonth = schedule.reduce((m, r) => Math.max(m, r.month || 0), 0);
  return (
    <div className="card-flat h-fit" data-testid="fee-summary">
      <div className="overline mb-3">FEE SUMMARY</div>
      <Line label="Total design fee" value={formatINR(total)} strong />
      {Number(fee.advance_amount) > 0 && <Line label="Advance" value={formatINR(fee.advance_amount)} />}
      {instalments.length > 0 && (
        <Line label={`${instalments.length} instalment${instalments.length > 1 ? "s" : ""}`}
              value={`${formatINR(fee.instalment_amount)} each`} />
      )}
      {lastMonth > 0 && <Line label="Fully paid by" value={`Month ${lastMonth}`} />}
      {tax > 0 && <Line label={`GST ${tax}%`} value={formatINR(Math.round(total * tax) / 100)} />}
      {q.proposal?.site_coordinator?.enabled && Number(q.proposal.site_coordinator.monthly_fee) > 0 && (
        <Line label="Site coordinator (optional)" value={`${formatINR(q.proposal.site_coordinator.monthly_fee)}/month`} />
      )}
      <p className="text-xs text-[#6E6A63] mt-3">Save to update the quotation total and the PDF.</p>
    </div>
  );
}

function Line({ label, value, strong }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-[#5C5C5C]">{label}</span>
      <span className={`font-mono text-right ${strong ? "font-semibold text-base text-[#1A1A1A]" : ""}`}>{value}</span>
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <section className="card-flat space-y-3">
      <div>
        <h3 className="font-display font-bold text-lg">{title}</h3>
        {hint && <p className="text-xs text-[#6E6A63] mt-0.5">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block text-xs font-semibold text-[#5C5C5C]">
      <span className="block mb-1">{label}</span>
      <span className="block font-normal text-sm text-[#1A1A1A]">{children}</span>
    </label>
  );
}

function ListEditor({ items, onChange, placeholder, multiline, readOnly, testid }) {
  const set = (i, v) => onChange(items.map((x, j) => (j === i ? v : x)));
  const remove = (i) => onChange(items.filter((_, j) => j !== i));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  return (
    <div className="space-y-2" data-testid={`list-${testid}`}>
      {items.map((it, i) => (
        <div key={i} className="flex items-start gap-2">
          <span className="text-xs text-[#6E6A63] w-5 pt-2.5 text-right shrink-0">{i + 1}.</span>
          {multiline ? (
            <textarea rows={Math.min(8, Math.max(3, Math.ceil((it || "").length / 70)))} className="input-flat flex-1" value={it} disabled={readOnly}
                      aria-label={`Item ${i + 1}`} onChange={(e) => set(i, e.target.value)} />
          ) : (
            <input className="input-flat flex-1" value={it} disabled={readOnly}
                   aria-label={`Item ${i + 1}`} onChange={(e) => set(i, e.target.value)} />
          )}
          {!readOnly && (
            <div className="flex items-center gap-0.5 pt-1 shrink-0">
              <button type="button" className="btn-icon" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move item ${i + 1} up`}>
                <ArrowUp size={14} />
              </button>
              <button type="button" className="btn-icon" onClick={() => move(i, 1)} disabled={i === items.length - 1} aria-label={`Move item ${i + 1} down`}>
                <ArrowDown size={14} />
              </button>
              <button type="button" className="btn-icon text-[#B22B22]" onClick={() => remove(i)} aria-label={`Remove item ${i + 1}`}>
                <Trash size={14} />
              </button>
            </div>
          )}
        </div>
      ))}
      {!readOnly && (
        <button type="button" className="btn-ghost text-xs" onClick={() => onChange([...items, ""])}
                data-testid={`add-${testid}`}>
          <Plus size={12} /> {placeholder || "Add"}
        </button>
      )}
    </div>
  );
}
