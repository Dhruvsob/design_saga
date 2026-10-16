import { Link } from "react-router-dom";

const sections = [
  {
    title: "Information we process",
    body: [
      "Design Saga ERP processes account and organization details, employee records, project and task data, attendance records, uploaded business documents, and finance records entered by authorized users.",
      "Attendance features may process a device's location when a user explicitly checks in or checks out. Location is used to validate the attendance event and is not collected continuously by the ERP.",
    ],
  },
  {
    title: "Google Calendar data",
    body: [
      "A tenant administrator may optionally connect a Google account. The integration uses the account identity to identify the connected calendar and uses Google Calendar event access to create, update, or remove events generated from ERP calendar items and task dates.",
      "When an administrator tags employees, their work email addresses may be added as event attendees so Google can deliver invitations and reminders. The ERP does not sell Google user data, use it for advertising, or use it to train general-purpose AI models.",
      "OAuth refresh and access tokens are encrypted at rest. Disconnecting Google Calendar removes the stored connection and tokens from the ERP. Events already created in Google Calendar remain there until a calendar owner removes them.",
    ],
  },
  {
    title: "Use and sharing",
    body: [
      "Information is used to provide ERP functions requested by the tenant, including authentication, projects, tasks, attendance, accounting, notifications, and calendar synchronization.",
      "Data is shared only with service providers needed to operate the ERP, with integrations an authorized tenant administrator enables, or when required by law. Each tenant's records are separated from other tenants and access is limited by roles and permissions.",
    ],
  },
  {
    title: "Security and retention",
    body: [
      "The service uses access controls, encrypted network connections, password hashing, audit records, and encrypted integration credentials. No online service can guarantee absolute security.",
      "Business records are retained while the tenant account is active and as required for operational, legal, backup, and audit purposes. Authorized administrators may correct or remove records subject to applicable retention obligations.",
    ],
  },
  {
    title: "Your choices",
    body: [
      "Users can decline optional Google Calendar access. A tenant administrator can disconnect the integration from the ERP Calendar page and can revoke access at any time from the Google Account security settings.",
      "For access, correction, deletion, or privacy questions, contact your tenant administrator or use the support contact shown on the Google authorization screen.",
    ],
  },
];

export default function PrivacyPolicy() {
  return (
    <main className="min-h-screen bg-[#FAF9F6] text-[#2C2C2C]">
      <header className="border-b border-[#E8E6E1] bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-5">
          <Link to="/" className="font-display text-xl font-semibold text-[#2C2C2C]">
            Design Saga ERP
          </Link>
          <Link to="/" className="text-sm font-medium text-[#76705E] hover:text-[#2C2C2C]">
            Return to sign in
          </Link>
        </div>
      </header>

      <article className="mx-auto max-w-4xl px-6 py-12 sm:py-16">
        <div className="mb-10 border-b border-[#E8E6E1] pb-8">
          <p className="overline mb-3">LEGAL</p>
          <h1 className="font-display text-4xl font-semibold sm:text-5xl">Privacy Policy</h1>
          <p className="mt-4 text-sm text-[#6B6B6B]">Last updated: 16 October 2026</p>
          <p className="mt-6 max-w-3xl leading-7 text-[#5C5C5C]">
            This policy explains how Design Saga ERP handles information when organizations and
            their authorized users use the service at gamaa.in.
          </p>
        </div>

        <div className="space-y-10">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="font-display text-2xl font-semibold">{section.title}</h2>
              <div className="mt-3 space-y-3 leading-7 text-[#5C5C5C]">
                {section.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              </div>
            </section>
          ))}
        </div>

        <footer className="mt-14 border-t border-[#E8E6E1] pt-6 text-sm text-[#6B6B6B]">
          This policy applies to Design Saga ERP at gamaa.in and its optional Google Calendar
          integration.
        </footer>
      </article>
    </main>
  );
}
