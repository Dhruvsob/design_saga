import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

/* ---------- Crosshair cursor ------------------------------------------- */
function Crosshair() {
  const ref = useRef({ x: -999, y: -999 });
  const lineH = useRef(null);
  const lineV = useRef(null);
  const marker = useRef(null);

  useEffect(() => {
    const isTouch = window.matchMedia("(pointer: coarse)").matches;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (isTouch || prefersReduced) return;

    let raf = null;
    const move = (e) => {
      ref.current = { x: e.clientX, y: e.clientY };
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        const { x, y } = ref.current;
        if (lineH.current) lineH.current.style.transform = `translateY(${y}px)`;
        if (lineV.current) lineV.current.style.transform = `translateX(${x}px)`;
        if (marker.current) marker.current.style.transform = `translate(${x - 8}px, ${y - 8}px)`;
      });
    };
    window.addEventListener("mousemove", move, { passive: true });
    return () => window.removeEventListener("mousemove", move);
  }, []);

  return (
    <div className="crosshair-root" aria-hidden="true" style={{ pointerEvents: "none" }}>
      <div ref={lineH} className="ch-line ch-line-h" />
      <div ref={lineV} className="ch-line ch-line-v" />
      <div ref={marker} className="ch-marker">
        <div className="ch-dot" />
      </div>
    </div>
  );
}

/* ---------- Feature icon ------------------------------------------------ */
const FeatureIcon = ({ icon }) => (
  <div style={{
    width: 40, height: 40,
    background: "linear-gradient(145deg, rgba(139,127,106,0.12) 0%, rgba(118,112,94,0.18) 100%)",
    borderRadius: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 20, flexShrink: 0,
  }}>
    {icon}
  </div>
);

/* ---------- Feature card ------------------------------------------------ */
const FeatureCard = ({ icon, title, desc }) => (
  <div style={{
    background: "#fff",
    borderRadius: 14,
    border: "1px solid rgba(139,127,106,0.14)",
    padding: "1.25rem 1.5rem",
    display: "flex",
    gap: "1rem",
    alignItems: "flex-start",
    transition: "box-shadow 0.2s, transform 0.2s",
    cursor: "default",
  }}
    onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 8px 32px -8px rgba(118,112,94,0.18)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
    onMouseLeave={e => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.transform = "none"; }}
  >
    <FeatureIcon icon={icon} />
    <div>
      <div style={{ fontWeight: 600, fontSize: 15, color: "#2C2C2C", marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 13, color: "#6B6B6B", lineHeight: 1.5 }}>{desc}</div>
    </div>
  </div>
);

/* ---------- Feature groups ---------------------------------------------- */
const FEATURE_GROUPS = [
  {
    id: "projects", label: "Projects & Delivery", emoji: "🏛️",
    features: [
      { icon: "📐", title: "Project Management", desc: "Full lifecycle from concept to handover — phases, milestones, budgets, and site visits." },
      { icon: "📋", title: "Tasks & Workboard", desc: "Kanban or list view, assignees, due dates and progress tracking across your studio." },
      { icon: "📁", title: "Drawing Register", desc: "Version-controlled drawings, document uploads, and snag closures with photo evidence." },
      { icon: "📍", title: "Site Attendance", desc: "Geo-fenced check-in and check-out for site visits with live location map." },
    ],
  },
  {
    id: "clients", label: "Clients & Revenue", emoji: "💼",
    features: [
      { icon: "🤝", title: "CRM & Leads", desc: "Pipeline from inquiry to contract — track leads, convert clients, log every interaction." },
      { icon: "📄", title: "Quotations", desc: "Professional, branded quotation PDFs with BOQ, revision history, and client approval." },
      { icon: "🧾", title: "Invoices & Reminders", desc: "Issue invoices, track outstanding payments, and send automated reminders." },
      { icon: "💰", title: "Collections", desc: "Record collections against invoices, track overdue accounts, and get collection reports." },
    ],
  },
  {
    id: "people", label: "Team & HR", emoji: "👥",
    features: [
      { icon: "🧑‍💼", title: "Employee Records", desc: "Profiles, roles, documents, advances, and complete employment history." },
      { icon: "🕐", title: "Attendance & Leaves", desc: "Daily time-tracking, leave requests, holiday calendar, and approval workflows." },
      { icon: "💵", title: "Payroll", desc: "Monthly salary processing, deductions, advances recovery, and downloadable payslips." },
      { icon: "📊", title: "Expense Claims", desc: "Staff expense submissions with admin approval and reimbursement through payroll." },
    ],
  },
  {
    id: "finance", label: "Accounting & Finance", emoji: "📒",
    features: [
      { icon: "📔", title: "Double-Entry Books", desc: "Full chart of accounts, journal entries, daybook, and account ledgers." },
      { icon: "🏦", title: "Bank Reconciliation", desc: "Upload bank statements and reconcile transactions automatically." },
      { icon: "📈", title: "Financial Reports", desc: "P&L, Balance Sheet, Cash Flow, and Trial Balance — instantly available." },
      { icon: "🔒", title: "Period Close & Export", desc: "Lock accounting periods and export to Excel for CA review." },
    ],
  },
  {
    id: "procurement", label: "Procurement & Vendors", emoji: "🏗️",
    features: [
      { icon: "🛒", title: "Purchase Orders", desc: "Raise, approve, and track POs — convert to GRN on delivery." },
      { icon: "📦", title: "Vendor Bills & Payments", desc: "Bill matching, payment scheduling, and vendor account statements." },
      { icon: "🤑", title: "Vendor Incentives", desc: "Track and settle commission-based incentives with full audit trail." },
      { icon: "🏢", title: "Vendor 360", desc: "Complete vendor profile with transaction history, documents, and contacts." },
    ],
  },
];

/* ---------- Step -------------------------------------------------------- */
const Step = ({ num, title, desc }) => (
  <div style={{ display: "flex", gap: "1.25rem", alignItems: "flex-start" }}>
    <div style={{
      width: 44, height: 44, borderRadius: "50%", flexShrink: 0,
      background: "linear-gradient(145deg, #76705E, #5F5A4B)",
      display: "flex", alignItems: "center", justifyContent: "center",
      color: "#fff", fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 15,
    }}>
      {num}
    </div>
    <div style={{ paddingTop: 10 }}>
      <div style={{ fontWeight: 600, fontSize: 16, color: "#2C2C2C", marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 14, color: "#6B6B6B", lineHeight: 1.6 }}>{desc}</div>
    </div>
  </div>
);

/* ---------- Main landing page ------------------------------------------- */
export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [activeGroup, setActiveGroup] = useState("projects");
  const [formState, setFormState] = useState({ name: "", company: "", email: "", phone: "", type: "", message: "", website: "" });
  const [formStatus, setFormStatus] = useState(null); // null | "sending" | "sent" | "error"

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const handleForm = async (e) => {
    e.preventDefault();
    setFormStatus("sending");
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formState),
      });
      if (!response.ok) throw new Error(`Contact request failed (${response.status})`);
      setFormStatus("sent");
    } catch {
      setFormStatus("error");
    }
  };

  const currentGroup = FEATURE_GROUPS.find(g => g.id === activeGroup);

  return (
    <div style={{ fontFamily: "var(--font-body, 'Inter', sans-serif)", background: "#FAF9F6", color: "#2C2C2C", overflowX: "hidden" }}>
      <Crosshair />

      {/* ===== HEADER ===== */}
      <header style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        padding: "0 2rem",
        background: scrolled ? "rgba(250,249,246,0.95)" : "transparent",
        backdropFilter: scrolled ? "blur(12px)" : "none",
        borderBottom: scrolled ? "1px solid rgba(139,127,106,0.12)" : "none",
        transition: "all 0.3s",
        height: 68,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        {/* Logo */}
        <a href="#hero" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 10 }}
          onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10, flexShrink: 0,
            background: "linear-gradient(145deg, #9A8F7A 0%, #76705E 100%)",
            boxShadow: "0 4px 12px -4px rgba(91,78,58,0.4)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ color: "#fff", fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 14, userSelect: "none" }}>G</span>
          </div>
          <div>
            <div style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 17, letterSpacing: "-0.02em", color: "#2C2C2C", lineHeight: 1 }}>Gamaa</div>
            <div style={{ fontSize: 9, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "#8B7F6A", lineHeight: 1 }}>Architecture ERP</div>
          </div>
        </a>

        {/* Desktop nav */}
        <nav style={{ display: "flex", gap: "2rem", alignItems: "center" }} className="landing-desktop-nav">
          {["Features", "How it works", "Pricing", "Contact"].map(item => (
            <a key={item}
              href={`#${item.toLowerCase().replace(/ /g, "-")}`}
              style={{ fontSize: 14, color: "#6B6B6B", textDecoration: "none", fontWeight: 500, transition: "color 0.15s" }}
              onMouseEnter={e => e.target.style.color = "#2C2C2C"}
              onMouseLeave={e => e.target.style.color = "#6B6B6B"}
              onClick={e => {
                e.preventDefault();
                document.getElementById(item.toLowerCase().replace(/ /g, "-"))?.scrollIntoView({ behavior: "smooth" });
              }}
            >{item}</a>
          ))}
          <Link to="/login" style={{
            padding: "8px 20px", borderRadius: 8,
            background: "linear-gradient(145deg, #76705E, #5F5A4B)",
            color: "#fff", fontSize: 14, fontWeight: 600,
            textDecoration: "none", letterSpacing: "-0.01em",
            boxShadow: "0 2px 8px -2px rgba(91,78,58,0.4)",
            transition: "opacity 0.15s",
          }}
            onMouseEnter={e => e.currentTarget.style.opacity = "0.85"}
            onMouseLeave={e => e.currentTarget.style.opacity = "1"}
          >
            Sign in
          </Link>
        </nav>

        {/* Mobile menu button */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="landing-mobile-menu-btn"
          style={{ background: "none", border: "none", cursor: "pointer", color: "#2C2C2C", display: "none" }}
          aria-label="Open menu"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            {menuOpen
              ? <><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></>
              : <><line x1="3" y1="7" x2="21" y2="7"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="17" x2="21" y2="17"/></>}
          </svg>
        </button>
      </header>

      {/* Mobile menu drawer */}
      {menuOpen && (
        <div style={{
          position: "fixed", top: 68, left: 0, right: 0, zIndex: 99,
          background: "rgba(250,249,246,0.98)", backdropFilter: "blur(16px)",
          borderBottom: "1px solid rgba(139,127,106,0.14)",
          padding: "1.5rem 2rem 2rem",
          display: "flex", flexDirection: "column", gap: "1.25rem",
        }}>
          {["Features", "How it works", "Pricing", "Contact"].map(item => (
            <a key={item}
              href={`#${item.toLowerCase().replace(/ /g, "-")}`}
              style={{ fontSize: 16, color: "#2C2C2C", textDecoration: "none", fontWeight: 500 }}
              onClick={() => setMenuOpen(false)}
            >{item}</a>
          ))}
          <Link to="/login" style={{
            padding: "12px 24px", borderRadius: 10, textAlign: "center",
            background: "linear-gradient(145deg, #76705E, #5F5A4B)",
            color: "#fff", fontSize: 15, fontWeight: 600, textDecoration: "none",
          }}
            onClick={() => setMenuOpen(false)}
          >
            Sign in to your workspace
          </Link>
        </div>
      )}

      {/* ===== HERO ===== */}
      <section id="hero" style={{
        minHeight: "100vh", position: "relative",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "120px 2rem 80px",
        overflow: "hidden",
      }}>
        {/* Architectural grid background */}
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.045, pointerEvents: "none" }} xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="arch-grid" width="60" height="60" patternUnits="userSpaceOnUse">
              <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#76705E" strokeWidth="0.75"/>
            </pattern>
            <pattern id="arch-grid-lg" width="300" height="300" patternUnits="userSpaceOnUse">
              <path d="M 300 0 L 0 0 0 300" fill="none" stroke="#76705E" strokeWidth="1.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#arch-grid)" />
          <rect width="100%" height="100%" fill="url(#arch-grid-lg)" />
        </svg>

        {/* Gradient blob */}
        <div style={{
          position: "absolute", top: "15%", right: "5%", width: 480, height: 480,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(139,127,106,0.08) 0%, transparent 70%)",
          pointerEvents: "none",
        }} />
        <div style={{
          position: "absolute", bottom: "10%", left: "5%", width: 360, height: 360,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(118,112,94,0.06) 0%, transparent 70%)",
          pointerEvents: "none",
        }} />

        {/* Hero content */}
        <div style={{ maxWidth: 820, textAlign: "center", position: "relative", zIndex: 1 }}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "6px 14px", borderRadius: 100,
            border: "1px solid rgba(139,127,106,0.25)",
            background: "rgba(139,127,106,0.06)",
            marginBottom: "1.75rem",
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#76705E", animation: "pulse-dot 2s ease-in-out infinite", display: "inline-block" }} />
            <span style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "#8B7F6A" }}>
              Architecture & Interior Design ERP
            </span>
          </div>

          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontWeight: 700, fontSize: "clamp(2.8rem, 7vw, 5.5rem)",
            lineHeight: 1.08, letterSpacing: "-0.025em",
            color: "#2C2C2C",
            marginBottom: "1.5rem",
          }}>
            One intelligent<br />workspace for every<br />
            <span style={{ color: "#76705E" }}>architecture studio.</span>
          </h1>

          <p style={{
            fontSize: "clamp(1rem, 2vw, 1.2rem)", color: "#6B6B6B",
            lineHeight: 1.65, maxWidth: 540, margin: "0 auto 2.5rem",
          }}>
            From first client inquiry to final handover — projects, people, finances, and vendors, managed in one calm, connected system.
          </p>

          <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
            <a href="#contact"
              style={{
                padding: "14px 32px", borderRadius: 10,
                background: "linear-gradient(145deg, #76705E, #5F5A4B)",
                color: "#fff", fontSize: 15, fontWeight: 600,
                textDecoration: "none", letterSpacing: "-0.01em",
                boxShadow: "0 4px 20px -4px rgba(91,78,58,0.45)",
                transition: "opacity 0.15s, transform 0.15s",
              }}
              onClick={e => { e.preventDefault(); document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" }); }}
              onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; e.currentTarget.style.transform = "translateY(-1px)"; }}
              onMouseLeave={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "none"; }}
            >
              Book a Demo
            </a>
            <Link to="/login"
              style={{
                padding: "14px 32px", borderRadius: 10,
                border: "1.5px solid rgba(139,127,106,0.35)",
                background: "rgba(255,255,255,0.7)",
                color: "#2C2C2C", fontSize: 15, fontWeight: 600,
                textDecoration: "none", letterSpacing: "-0.01em",
                backdropFilter: "blur(4px)",
                transition: "background 0.15s, transform 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.95)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.7)"; e.currentTarget.style.transform = "none"; }}
            >
              Sign in →
            </Link>
          </div>

          {/* Floating ERP preview cards */}
          <div style={{ position: "relative", marginTop: "4rem", height: 180, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {[
              { left: "2%", top: "0%", delay: "0s", label: "Invoice Raised", value: "₹2,40,000", badge: "Paid", color: "#22c55e" },
              { left: "30%", top: "10%", delay: "0.4s", label: "Active Projects", value: "12", badge: "On track", color: "#76705E" },
              { left: "58%", top: "0%", delay: "0.8s", label: "Team Present", value: "18 / 21", badge: "Today", color: "#8B7F6A" },
              { left: "80%", top: "10%", delay: "1.2s", label: "P&L (Month)", value: "₹8.4L", badge: "↑ 14%", color: "#22c55e" },
            ].map((card, i) => (
              <div key={i} style={{
                position: "absolute",
                left: card.left, top: card.top,
                background: "#fff",
                border: "1px solid rgba(139,127,106,0.14)",
                borderRadius: 12,
                padding: "12px 16px",
                minWidth: 130,
                boxShadow: "0 8px 32px -8px rgba(44,44,44,0.12)",
                animation: `float-card 4s ease-in-out infinite`,
                animationDelay: card.delay,
              }}>
                <div style={{ fontSize: 10, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", marginBottom: 4 }}>{card.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "#2C2C2C", letterSpacing: "-0.02em", fontFamily: "'Playfair Display', serif" }}>{card.value}</div>
                <div style={{ marginTop: 4, display: "inline-block", padding: "2px 8px", borderRadius: 100, background: `${card.color}18`, color: card.color, fontSize: 10, fontWeight: 600 }}>{card.badge}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FEATURES ===== */}
      <section id="features" style={{ padding: "6rem 2rem", background: "#F5F4F0" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          {/* Header */}
          <div style={{ textAlign: "center", marginBottom: "3.5rem" }}>
            <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.16em", textTransform: "uppercase", color: "#8B7F6A", marginBottom: 12 }}>Everything you need</div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: "clamp(2rem, 4vw, 3.2rem)", letterSpacing: "-0.02em", color: "#2C2C2C", margin: "0 0 1rem" }}>
              A complete ERP, built for<br />how studios actually work.
            </h2>
            <p style={{ color: "#6B6B6B", fontSize: 16, maxWidth: 520, margin: "0 auto" }}>
              Every module connects to the others — no duplicate data entry, no fragmented workflows.
            </p>
          </div>

          {/* Group tabs */}
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center", marginBottom: "2.5rem" }}>
            {FEATURE_GROUPS.map(g => (
              <button key={g.id}
                onClick={() => setActiveGroup(g.id)}
                style={{
                  padding: "8px 18px", borderRadius: 100,
                  border: `1.5px solid ${activeGroup === g.id ? "#76705E" : "rgba(139,127,106,0.2)"}`,
                  background: activeGroup === g.id ? "linear-gradient(145deg, #76705E, #5F5A4B)" : "rgba(255,255,255,0.7)",
                  color: activeGroup === g.id ? "#fff" : "#2C2C2C",
                  fontSize: 13, fontWeight: 600, cursor: "pointer",
                  transition: "all 0.2s",
                }}
              >
                {g.emoji} {g.label}
              </button>
            ))}
          </div>

          {/* Feature cards grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
            {currentGroup?.features.map(f => <FeatureCard key={f.title} {...f} />)}
          </div>
        </div>
      </section>

      {/* ===== HOW IT WORKS ===== */}
      <section id="how-it-works" style={{ padding: "6rem 2rem" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "5rem", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.16em", textTransform: "uppercase", color: "#8B7F6A", marginBottom: 12 }}>Getting started</div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: "clamp(1.8rem, 3vw, 2.6rem)", letterSpacing: "-0.02em", color: "#2C2C2C", marginBottom: "1rem" }}>
              Up and running<br />in one day.
            </h2>
            <p style={{ color: "#6B6B6B", fontSize: 15, lineHeight: 1.7, marginBottom: "2rem" }}>
              No complex implementation. No IT team required. Gamaa provisions your workspace, you fill in your team, and operations start immediately.
            </p>
            <a href="#contact"
              style={{
                display: "inline-flex", padding: "11px 24px", borderRadius: 8,
                border: "1.5px solid rgba(139,127,106,0.35)",
                color: "#76705E", fontSize: 14, fontWeight: 600,
                textDecoration: "none",
                transition: "all 0.15s",
              }}
              onClick={e => { e.preventDefault(); document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" }); }}
              onMouseEnter={e => { e.currentTarget.style.background = "rgba(139,127,106,0.08)"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
            >
              Contact us to get started →
            </a>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
            <Step num="1" title="Book a demo or contact us" desc="Tell us about your studio — size, type of work, and what you need most." />
            <Step num="2" title="We set up your workspace" desc="Gamaa creates a private tenant with your company name and branding." />
            <Step num="3" title="Add your team" desc="Invite employees and assign roles — Admins, Project Managers, Site Staff, Accounts." />
            <Step num="4" title="Go live on day one" desc="Start logging projects, attendance, invoices, and expenses from day one." />
            <Step num="5" title="Everything connects automatically" desc="Invoices post to accounting. Payroll hits the books. Payments close out jobs." />
          </div>
        </div>
      </section>

      {/* ===== PRICING ===== */}
      <section id="pricing" style={{ padding: "6rem 2rem", background: "#F5F4F0" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", textAlign: "center" }}>
          <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.16em", textTransform: "uppercase", color: "#8B7F6A", marginBottom: 12 }}>Pricing</div>
          <h2 style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: "clamp(2rem, 4vw, 3rem)", letterSpacing: "-0.02em", color: "#2C2C2C", marginBottom: "1rem" }}>
            Simple, studio-sized pricing.
          </h2>
          <p style={{ color: "#6B6B6B", fontSize: 16, maxWidth: 480, margin: "0 auto 3rem" }}>
            Pricing is tailored to your studio size and selected modules. Contact us for a quote.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1.5rem", marginBottom: "2.5rem" }}>
            {[
              {
                name: "Studio",
                for: "Small studios · up to 10 users",
                features: ["Core project management", "CRM & invoicing", "Attendance & payroll", "Accounting basics"],
              },
              {
                name: "Professional",
                for: "Growing firms · up to 30 users",
                features: ["Everything in Studio", "Full accounting suite", "Vendor & procurement", "Drawing register"],
                highlight: true,
              },
              {
                name: "Enterprise",
                for: "Large studios · unlimited users",
                features: ["Everything in Professional", "Custom module access", "Priority support", "Dedicated onboarding"],
              },
            ].map(plan => (
              <div key={plan.name} style={{
                background: plan.highlight ? "linear-gradient(145deg, #76705E, #5F5A4B)" : "#fff",
                borderRadius: 16,
                border: `1.5px solid ${plan.highlight ? "transparent" : "rgba(139,127,106,0.14)"}`,
                padding: "2rem 1.75rem",
                textAlign: "left",
                position: "relative",
                boxShadow: plan.highlight ? "0 12px 40px -12px rgba(91,78,58,0.45)" : "none",
              }}>
                {plan.highlight && <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)", background: "#8B7F6A", color: "#fff", fontSize: 10, fontFamily: "monospace", letterSpacing: "0.12em", textTransform: "uppercase", padding: "4px 12px", borderRadius: 100 }}>Most popular</div>}
                <div style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 22, color: plan.highlight ? "#fff" : "#2C2C2C", marginBottom: 4 }}>{plan.name}</div>
                <div style={{ fontSize: 12, color: plan.highlight ? "rgba(255,255,255,0.65)" : "#8B7F6A", marginBottom: 20 }}>{plan.for}</div>
                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: 10 }}>
                  {plan.features.map(f => (
                    <li key={f} style={{ fontSize: 13.5, color: plan.highlight ? "rgba(255,255,255,0.88)" : "#2C2C2C", display: "flex", gap: 8, alignItems: "flex-start" }}>
                      <span style={{ color: plan.highlight ? "rgba(255,255,255,0.6)" : "#8B7F6A", fontWeight: 700, flexShrink: 0 }}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <a href="#contact"
                  style={{
                    display: "block", padding: "10px 0", borderRadius: 8, textAlign: "center",
                    background: plan.highlight ? "rgba(255,255,255,0.14)" : "rgba(139,127,106,0.1)",
                    border: `1.5px solid ${plan.highlight ? "rgba(255,255,255,0.25)" : "rgba(139,127,106,0.25)"}`,
                    color: plan.highlight ? "#fff" : "#76705E",
                    fontSize: 13, fontWeight: 600, textDecoration: "none",
                    transition: "all 0.15s",
                  }}
                  onClick={e => { e.preventDefault(); document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" }); }}
                  onMouseEnter={e => e.currentTarget.style.opacity = "0.8"}
                  onMouseLeave={e => e.currentTarget.style.opacity = "1"}
                >
                  Contact Sales
                </a>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13, color: "#8B7F6A" }}>
            All plans include free setup, training, and ongoing support. Monthly or yearly billing available.
          </p>
        </div>
      </section>

      {/* ===== CONTACT / DEMO ===== */}
      <section id="contact" style={{ padding: "6rem 2rem" }}>
        <div style={{ maxWidth: 820, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "5rem", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.16em", textTransform: "uppercase", color: "#8B7F6A", marginBottom: 12 }}>Contact us</div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: "clamp(1.8rem, 3vw, 2.6rem)", letterSpacing: "-0.02em", color: "#2C2C2C", marginBottom: "1rem" }}>
              Let's talk about<br />your studio.
            </h2>
            <p style={{ color: "#6B6B6B", fontSize: 15, lineHeight: 1.7, marginBottom: "2rem" }}>
              Fill in the form and our team will reach out within 24 hours to understand your studio's needs and arrange a demo.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                { icon: "📧", label: "Email", value: "hello@gamaa.in" },
                { icon: "🕐", label: "Response", value: "Within 24 hours" },
                { icon: "🌏", label: "Serving", value: "Architecture studios across India" },
              ].map(item => (
                <div key={item.label} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 18 }}>{item.icon}</span>
                  <div>
                    <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A" }}>{item.label}</div>
                    <div style={{ fontSize: 14, color: "#2C2C2C", marginTop: 2 }}>{item.value}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Contact form */}
          <div style={{
            background: "#fff",
            borderRadius: 16,
            border: "1px solid rgba(139,127,106,0.14)",
            padding: "2rem",
            boxShadow: "0 8px 40px -12px rgba(44,44,44,0.1)",
          }}>
            {formStatus === "sent" ? (
              <div style={{ textAlign: "center", padding: "2rem 0" }}>
                <div style={{ fontSize: 40, marginBottom: 16 }}>✅</div>
                <h3 style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 22, color: "#2C2C2C", marginBottom: 8 }}>We'll be in touch!</h3>
                <p style={{ color: "#6B6B6B", fontSize: 14, lineHeight: 1.6 }}>Thanks for your interest in Gamaa. Our team will reach out within 24 hours.</p>
              </div>
            ) : (
              <form onSubmit={handleForm} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div className="landing-two-col" style={{ display: "grid", gap: "0.75rem" }}>
                  <div>
                    <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-name">Your name *</label>
                    <input required minLength={2} maxLength={120} id="lp-name" autoComplete="name" value={formState.name} onChange={e => setFormState(s => ({...s, name: e.target.value}))}
                      placeholder="e.g. Arjun Sharma"
                      className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: "#2C2C2C", boxSizing: "border-box" }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-company">Studio name *</label>
                    <input required minLength={2} maxLength={160} id="lp-company" autoComplete="organization" value={formState.company} onChange={e => setFormState(s => ({...s, company: e.target.value}))}
                      placeholder="e.g. Studio 23"
                      className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: "#2C2C2C", boxSizing: "border-box" }} />
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-email">Email *</label>
                  <input required type="email" maxLength={254} id="lp-email" autoComplete="email" value={formState.email} onChange={e => setFormState(s => ({...s, email: e.target.value}))}
                    placeholder="arjun@studio23.in"
                    className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: "#2C2C2C", boxSizing: "border-box" }} />
                </div>
                <div className="landing-two-col" style={{ display: "grid", gap: "0.75rem" }}>
                  <div>
                    <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-phone">Phone</label>
                    <input type="tel" maxLength={40} id="lp-phone" autoComplete="tel" value={formState.phone} onChange={e => setFormState(s => ({...s, phone: e.target.value}))}
                      placeholder="+91 98765 43210"
                      className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: "#2C2C2C", boxSizing: "border-box" }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-type">Studio type</label>
                    <select id="lp-type" value={formState.type} onChange={e => setFormState(s => ({...s, type: e.target.value}))}
                      className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: formState.type ? "#2C2C2C" : "#8B7F6A", boxSizing: "border-box" }}>
                      <option value="">Select…</option>
                      <option value="architecture">Architecture Studio</option>
                      <option value="interior">Interior Design</option>
                      <option value="consultancy">Consultancy</option>
                      <option value="turnkey">Turnkey / PMC</option>
                      <option value="hybrid">Architecture + Interior</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase", color: "#8B7F6A", display: "block", marginBottom: 6 }} htmlFor="lp-message">Message</label>
                  <textarea maxLength={2000} id="lp-message" value={formState.message} onChange={e => setFormState(s => ({...s, message: e.target.value}))}
                    placeholder="Tell us about your studio size, current tools, and what you're looking to improve."
                    rows={3}
                    className="landing-field" style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(139,127,106,0.25)", background: "#FAF9F6", fontSize: 13, color: "#2C2C2C", boxSizing: "border-box", resize: "vertical", fontFamily: "inherit" }} />
                </div>
                <input type="text" name="website" value={formState.website}
                  onChange={e => setFormState(s => ({...s, website: e.target.value}))}
                  tabIndex={-1} autoComplete="off" aria-hidden="true"
                  style={{ position: "absolute", left: "-10000px", width: 1, height: 1, opacity: 0 }} />
                {formStatus === "error" && (
                  <div role="alert" style={{ fontSize: 12, color: "#B22B22", lineHeight: 1.5 }}>
                    We could not send your request. Please try again, or email hello@gamaa.in.
                  </div>
                )}
                <button type="submit" disabled={formStatus === "sending"}
                  style={{
                    width: "100%", padding: "12px", borderRadius: 8,
                    background: "linear-gradient(145deg, #76705E, #5F5A4B)",
                    color: "#fff", fontSize: 14, fontWeight: 600, border: "none", cursor: formStatus === "sending" ? "wait" : "pointer",
                    boxShadow: "0 4px 16px -4px rgba(91,78,58,0.4)",
                    opacity: formStatus === "sending" ? 0.7 : 1,
                    transition: "opacity 0.15s",
                  }}
                >
                  {formStatus === "sending" ? "Sending…" : "Request a Demo"}
                </button>
              </form>
            )}
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer style={{
        background: "linear-gradient(150deg, #76705E 0%, #5F5A4B 45%, #2C2820 100%)",
        padding: "4rem 2rem 2.5rem",
        color: "rgba(255,255,255,0.75)",
      }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: "3rem", marginBottom: "3rem" }}>
            {/* Brand */}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(255,255,255,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ color: "#fff", fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 15 }}>G</span>
                </div>
                <div>
                  <div style={{ fontFamily: "'Playfair Display', serif", fontWeight: 700, fontSize: 17, color: "#fff" }}>Gamaa</div>
                  <div style={{ fontSize: 9, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)" }}>Architecture ERP</div>
                </div>
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.7, color: "rgba(255,255,255,0.55)", maxWidth: 260 }}>
                One intelligent workspace for architecture &amp; interior design studios. Projects, people, finances — all connected.
              </p>
            </div>
            {/* Links */}
            <div>
              <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 14 }}>Product</div>
              {["Features", "How it works", "Pricing", "Sign in"].map(link => (
                <div key={link} style={{ marginBottom: 10 }}>
                  {link === "Sign in" ? (
                    <Link to="/login" style={{ fontSize: 13.5, color: "rgba(255,255,255,0.65)", textDecoration: "none" }}>{link}</Link>
                  ) : (
                    <a href={`#${link.toLowerCase().replace(/ /g, "-")}`}
                      style={{ fontSize: 13.5, color: "rgba(255,255,255,0.65)", textDecoration: "none" }}
                      onClick={e => { e.preventDefault(); document.getElementById(link.toLowerCase().replace(/ /g, "-"))?.scrollIntoView({ behavior: "smooth" }); }}
                    >{link}</a>
                  )}
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 14 }}>Solutions</div>
              {["Architecture Studio", "Interior Design", "Turnkey / PMC", "Consultancy"].map(link => (
                <div key={link} style={{ marginBottom: 10 }}>
                  <span style={{ fontSize: 13.5, color: "rgba(255,255,255,0.65)" }}>{link}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 14 }}>Legal</div>
              {[{ label: "Privacy Policy", to: "/privacy" }, { label: "Terms of Use", to: "/privacy" }, { label: "Contact", href: "#contact" }].map(link => (
                <div key={link.label} style={{ marginBottom: 10 }}>
                  {link.to ? (
                    <Link to={link.to} style={{ fontSize: 13.5, color: "rgba(255,255,255,0.65)", textDecoration: "none" }}>{link.label}</Link>
                  ) : (
                    <a href={link.href} style={{ fontSize: 13.5, color: "rgba(255,255,255,0.65)", textDecoration: "none" }}
                      onClick={e => { e.preventDefault(); document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" }); }}
                    >{link.label}</a>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "1.5rem", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <div style={{ fontSize: 12, fontFamily: "monospace", color: "rgba(255,255,255,0.3)" }}>
              © {new Date().getFullYear()} Gamaa. All rights reserved.
            </div>
            <div style={{ fontSize: 12, fontFamily: "monospace", color: "rgba(255,255,255,0.3)" }}>
              Made for India's architecture & design studios.
            </div>
          </div>
        </div>
      </footer>

      {/* ===== INLINE STYLES for crosshair + animation ===== */}
      <style>{`
        .crosshair-root {
          position: fixed;
          inset: 0;
          z-index: 9999;
          pointer-events: none;
          overflow: hidden;
        }
        .ch-line {
          position: absolute;
          background: rgba(118,112,94,0.18);
          transition: transform 0.08s linear;
          will-change: transform;
        }
        .ch-line-h {
          left: 0; right: 0;
          height: 1px;
          top: 0;
        }
        .ch-line-v {
          top: 0; bottom: 0;
          width: 1px;
          left: 0;
        }
        .ch-marker {
          position: absolute;
          width: 16px; height: 16px;
          border: 1.5px solid rgba(118,112,94,0.4);
          top: 0; left: 0;
          display: flex; align-items: center; justify-content: center;
          transition: transform 0.08s linear;
          will-change: transform;
        }
        .ch-dot {
          width: 4px; height: 4px;
          border-radius: 50%;
          background: rgba(118,112,94,0.5);
        }

        .landing-two-col { grid-template-columns: 1fr 1fr; }
        @media (max-width: 520px) {
          .landing-two-col { grid-template-columns: 1fr; }
        }
        .landing-field:focus-visible {
          outline: 2px solid #8B7F6A;
          outline-offset: 1px;
        }

        @keyframes float-card {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-8px); }
        }

        @media (max-width: 768px) {
          .landing-desktop-nav { display: none !important; }
          .landing-mobile-menu-btn { display: flex !important; }
        }

        @media (max-width: 768px) {
          #how-it-works > div,
          #contact > div {
            grid-template-columns: 1fr !important;
            gap: 2.5rem !important;
          }
        }

        @media (max-width: 600px) {
          #hero > div > div:last-child {
            display: none !important;
          }
        }
      `}</style>
    </div>
  );
}
