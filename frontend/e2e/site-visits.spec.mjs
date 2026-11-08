// Phase 3: site visit from a project (geofence + pin, photos, notes, timeline,
// attendance link) and the live check-in map for admins, on desktop and phone.
import { test, expect, request as pwRequest } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { api, json, uid, authFile, baseURL } from "./helpers.mjs";

const SITE = { latitude: 23.0225, longitude: 72.5714, accuracy: 10 };
const FAR = { latitude: 23.0725, longitude: 72.6414, accuracy: 10 };
const LOGO = fs.readFileSync(fileURLToPath(new URL("./fixtures/qa-test-logo.png", import.meta.url)));
// 1x1 transparent PNG for map tiles, so tests never call tile servers.
const TILE = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");

test.beforeEach(async ({ context }, testInfo) => {
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
  for (const role of ["admin", "employee"]) await (await api(role)).dispose();
  await context.route(/tile\.openstreetmap\.org|arcgisonline\.com/, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: TILE }));
});

/** Project with a site fence and the QA employee on its team (idempotent per run). */
async function setUpProject() {
  const admin = await api("admin");
  const employee = await api("employee");
  const me = await json(employee.get("/api/auth/me"));
  const staff = await json(admin.get("/api/employees"));
  const rows = Array.isArray(staff) ? staff : staff.employees || staff.items || [];
  let emp = rows.find((e) => (e.email || "").toLowerCase() === me.email.toLowerCase());
  if (!emp) {
    emp = await json(admin.post("/api/employees", { data: {
      first_name: "Site", last_name: `Visitor${uid()}`, email: me.email, user_id: me.user_id,
      designation: "Architect",
    } }));
  }
  const project = await json(admin.post("/api/projects", { data: {
    name: `Site QA ${uid()}`, engagement_type: "turnkey",
  } }));
  await json(admin.patch(`/api/projects/${project.id}`, { data: { team_ids: [emp.id] } }));
  await json(admin.post("/api/attendance/locations", { data: {
    name: `${project.name} site`, kind: "site", project_id: project.id,
    lat: SITE.latitude, lng: SITE.longitude, radius_m: 150,
  } }));
  // Leave no visit open from an earlier test in this run.
  const mine = await json(employee.get("/api/site-visits"));
  for (const v of mine.visits.filter((x) => x.status === "open")) {
    await json(employee.post(`/api/site-visits/${v.id}/check-out`, { data: {} }));
  }
  return { admin, employee, project, emp };
}

test.describe("site visit as staff", () => {
  test.use({ storageState: authFile("employee"), permissions: ["geolocation"], geolocation: SITE });

  test("check in on site, add a photo and notes, finish, see it on the timeline", async ({ page }, testInfo) => {
    const { admin, employee, project } = await setUpProject();
    await page.goto(`/projects/${project.id}`);
    await page.getByTestId("tab-Site visits").click();
    await expect(page.getByTestId("site-visit-start")).toBeVisible();
    await page.getByTestId("site-visit-checkin").click();

    const open = page.getByTestId("site-visit-open");
    await expect(open).toBeVisible();
    await expect(open).toContainText("Inside site fence");

    // Photo: the file picker is the same input on desktop and phone (camera input on phones).
    if (testInfo.project.name === "mobile") await expect(page.getByTestId("site-photo-take")).toBeVisible();
    await page.getByTestId("site-photo-input").setInputFiles({ name: "site.png", mimeType: "image/png", buffer: LOGO });
    const thumb = page.getByTestId("site-photo-thumb").first();
    await expect(thumb).toBeVisible();
    await expect(thumb.locator("img")).toHaveAttribute("src", /^blob:/);

    await page.getByTestId("site-visit-notes").fill("Checked slab shuttering; plumbing sleeves pending.");
    await page.getByTestId("site-visit-save-notes").click();
    await expect(page.getByText("Notes saved")).toBeVisible();

    // Photo viewer shows the server time and GPS distance.
    await thumb.click();
    const viewer = page.getByTestId("site-photo-viewer");
    await expect(viewer).toContainText(/m from site/);
    await expect(viewer.getByTestId("site-photo-large")).toHaveAttribute("src", /^blob:/);
    await viewer.getByRole("button", { name: "Close photo" }).click();

    if (testInfo.project.name === "desktop") {
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"])
        .include('[data-testid="site-visits"]').exclude(".leaflet-container").analyze();
      expect(axe.violations.map((v) => v.id)).toEqual([]);
    }

    await page.getByTestId("site-visit-checkout").click();
    await page.getByTestId("confirm-ok").click();
    await expect(page.getByTestId("site-visit-start")).toBeVisible();

    // API: the visit is stored with its photo, linked to today's attendance.
    const { visits } = await json(employee.get(`/api/projects/${project.id}/site-visits`));
    expect(visits).toHaveLength(1);
    const [visit] = visits;
    expect(visit.status).toBe("closed");
    expect(visit.geo_status).toBe("inside");
    expect(visit.notes).toContain("plumbing sleeves");
    expect(visit.photos).toHaveLength(1);
    expect(JSON.stringify(visit)).not.toContain("storage_key");
    expect(visit.photos[0].content_type).toBe("image/jpeg"); // resized to JPEG on the device
    expect(visit.photos[0].distance_m).toBeLessThan(150);
    const today = await json(employee.get("/api/attendance/me/today"));
    expect(today.record.id).toBe(visit.attendance_id);
    expect((today.record.site_visits || []).map((s) => s.id)).toContain(visit.id);

    // Photos are private: no session, no photo.
    const photoPath = `/api/site-visits/${visit.id}/photos/${visit.photos[0].id}`;
    expect((await employee.get(photoPath)).status()).toBe(200);
    // This describe block has an employee storageState. Explicitly override it
    // so the privacy assertion is truly anonymous instead of inheriting the
    // project's authenticated request defaults.
    const anon = await pwRequest.newContext({
      baseURL,
      storageState: { cookies: [], origins: [] },
      extraHTTPHeaders: { Origin: baseURL },
    });
    expect((await anon.get(photoPath)).status()).toBe(401);
    await anon.dispose();

    // Project timeline.
    await page.getByTestId("tab-Activity").click();
    await expect(page.getByTestId("activity-timeline")).toContainText("checked in on site");
    await expect(page.getByTestId("activity-timeline")).toContainText("finished a site visit");

    // Staff cannot open the live map.
    expect((await employee.get("/api/site-visits/live-map")).status()).toBe(403);
    await expect(page.getByRole("link", { name: "Live map" })).toHaveCount(0);
    await Promise.all([admin.dispose(), employee.dispose()]);
  });

  test("outside the fence: visit is recorded only after asking for approval", async ({ page, context }) => {
    const { admin, employee, project } = await setUpProject();
    await context.setGeolocation(FAR);
    await page.goto(`/projects/${project.id}`);
    await page.getByTestId("tab-Site visits").click();
    await page.getByTestId("site-visit-checkin").click();
    const blocked = page.getByTestId("site-visit-blocked");
    await expect(blocked).toBeVisible();
    await expect(blocked).toContainText(/m from/);
    expect((await json(employee.get(`/api/projects/${project.id}/site-visits`))).visits).toHaveLength(0);

    await page.getByTestId("site-visit-force").click();
    await expect(page.getByTestId("site-visit-open")).toContainText("Outside site fence");
    const { visits } = await json(employee.get(`/api/projects/${project.id}/site-visits`));
    expect(visits[0].geo_status).toBe("outside");
    await json(employee.post(`/api/site-visits/${visits[0].id}/check-out`, { data: {} }));
    await Promise.all([admin.dispose(), employee.dispose()]);
  });
});

test.describe("live map as admin", () => {
  test.use({ storageState: authFile("admin") });

  test("shows today's visit pin, fences and the list; phone layout does not scroll sideways", async ({ page }) => {
    const { admin, employee, project } = await setUpProject();
    const visit = await json(employee.post(`/api/projects/${project.id}/site-visits`, { data: {
      lat: SITE.latitude + 0.0002, lng: SITE.longitude, accuracy_m: 9,
    } }));

    // Admin sees everyone's visits on the project tab too.
    const listed = await json(admin.get(`/api/projects/${project.id}/site-visits`));
    expect(listed.scope).toBe("all");
    expect(listed.visits.map((v) => v.id)).toContain(visit.id);

    await page.goto("/live-map");
    await expect(page.getByTestId("live-map-page")).toBeVisible();
    await expect(page.getByTestId("live-map")).toBeVisible();
    const row = page.getByTestId("live-map-row").filter({ hasText: project.name });
    await expect(row).toBeVisible();
    await expect(row).toContainText("On site");
    await expect(page.locator(".checkin-pin").first()).toBeVisible();
    await expect(page.locator(".leaflet-interactive").first()).toBeAttached(); // fence circles

    await page.getByTestId("live-map-filter-on_site").click();
    await expect(row).toBeVisible();
    await page.getByTestId("live-map-filter-office").click();
    await expect(page.getByTestId("live-map-row").filter({ hasText: project.name })).toHaveCount(0);

    const data = await json(admin.get("/api/site-visits/live-map"));
    expect(data.scope).toBe("all");
    expect(data.pins.find((p) => p.id === visit.id)).toMatchObject({ type: "site_visit", open: true, geo_status: "inside" });
    expect(data.fences.some((f) => f.project_id === project.id)).toBe(true);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, "no sideways scroll").toBeLessThanOrEqual(1);

    await json(employee.post(`/api/site-visits/${visit.id}/check-out`, { data: {} }));
    await Promise.all([admin.dispose(), employee.dispose()]);
  });

  test("admin sets a project's site location from the project tab", async ({ page, context }) => {
    const admin = await api("admin");
    const project = await json(admin.post("/api/projects", { data: { name: `Fence QA ${uid()}`, engagement_type: "turnkey" } }));
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation(SITE);
    await page.goto(`/projects/${project.id}`);
    await page.getByTestId("tab-Site visits").click();
    await page.getByTestId("site-fence-set").click();
    await expect(page.getByTestId("site-fence-editor")).toBeVisible();
    await page.getByTestId("site-fence-radius").fill("120");
    await page.getByTestId("site-fence-save").click();
    await expect(page.getByTestId("site-fence-editor")).toHaveCount(0);
    const body = await json(admin.get(`/api/projects/${project.id}/site-visits`));
    expect(body.site_fences).toHaveLength(1);
    expect(body.site_fences[0]).toMatchObject({ radius_m: 120 });
    expect(Math.abs(body.site_fences[0].lat - SITE.latitude)).toBeLessThan(0.0001);
    await admin.dispose();
  });
});
