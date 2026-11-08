import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Camera, Images, MapPin, SignIn, SignOut, Trash, ArrowsClockwise, X, Crosshair,
  NotePencil, CheckCircle, WarningCircle,
} from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate, formatDateTime, formatTime } from "../lib/format";
import { confirmAction } from "../lib/confirm";
import { useAuth } from "../context/AuthContext";
import RowActions from "./RowActions";
import CheckInMap, { MapLegend } from "./CheckInMap";
import GeoFenceMap from "./GeoFenceMap";

// ------------------------------------------------------------------ helpers
export function getGPS() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("This browser cannot share your location."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({
        lat: Number(p.coords.latitude.toFixed(6)),
        lng: Number(p.coords.longitude.toFixed(6)),
        accuracy_m: Math.round(p.coords.accuracy || 0),
      }),
      (err) => reject(new Error(err?.code === 1
        ? "Location permission is off. Allow location for this site in your browser and try again."
        : "Could not read your location. Step outdoors and try again.")),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    );
  });
}

export function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d) && d.message) return d.message;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg;
  return fallback;
}

export function fmtDuration(min) {
  if (min === null || min === undefined) return "";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function deviceLabel() {
  const ua = navigator.userAgent || "";
  const browser = /Edg/.test(ua) ? "Edge" : /Chrome/.test(ua) ? "Chrome"
    : /Firefox/.test(ua) ? "Firefox" : /Safari/.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS"
    : /Windows/.test(ua) ? "Windows" : /Mac/.test(ua) ? "Mac" : "device";
  return `${browser} / ${os}`;
}

// Phone photos are 3-12 MB; send a 1600 px JPEG instead (also normalises HEIC
// from the camera on browsers that can decode it). Falls back to the original.
async function shrinkPhoto(file, maxSide = 1600) {
  const toJpeg = (source, w, h) => new Promise((resolve) => {
    const scale = Math.min(1, maxSide / Math.max(w, h));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.82);
  });
  try {
    let blob = null;
    if (typeof window.createImageBitmap === "function") {
      const bmp = await window.createImageBitmap(file);
      blob = await toJpeg(bmp, bmp.width, bmp.height);
      if (bmp.close) bmp.close();
    } else {
      const url = URL.createObjectURL(file);
      try {
        const img = await new Promise((res, rej) => {
          const i = new Image();
          i.onload = () => res(i);
          i.onerror = rej;
          i.src = url;
        });
        blob = await toJpeg(img, img.naturalWidth, img.naturalHeight);
      } finally {
        URL.revokeObjectURL(url);
      }
    }
    if (blob) return new File([blob], "site-photo.jpg", { type: "image/jpeg", lastModified: file.lastModified || Date.now() });
  } catch {
    /* fall back to the original file */
  }
  return file;
}

export const GEO_LABEL = {
  inside: { label: "Inside site fence", cls: "chip-approved" },
  outside: { label: "Outside site fence", cls: "chip-pending" },
  no_fence: { label: "Site location not set", cls: "chip-pending" },
};

/** Private photo: fetched with the session and shown from a blob: URL. */
export function AuthImage({ src, alt, className = "", testid }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let objectUrl = null;
    setUrl(null);
    setFailed(false);
    api.get(src, { responseType: "blob" })
      .then((r) => {
        objectUrl = URL.createObjectURL(r.data);
        if (alive) setUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(() => { if (alive) setFailed(true); });
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);
  if (failed) {
    return <div className={`flex items-center justify-center bg-[var(--surface-2)] text-xs text-[var(--ink-3)] ${className}`}>Photo unavailable</div>;
  }
  if (!url) return <div className={`bg-[var(--surface-2)] animate-pulse ${className}`} aria-label="Loading photo" />;
  return <img src={url} alt={alt} className={className} data-testid={testid} />;
}

// The device time is shown only when it differs from the upload time (photo
// taken earlier and uploaded later, e.g. after the network came back).
function takenNote(p) {
  return p.client_taken_at && Math.abs(new Date(p.client_taken_at) - new Date(p.captured_at)) > 15 * 60 * 1000
    ? ` (taken ${formatTime(p.client_taken_at)})` : "";
}

function photoWhere(p) {
  if (p.distance_m === null || p.distance_m === undefined) return "No location";
  const from = p.distance_from === "site" ? "from site" : "from check-in point";
  return `${Math.round(p.distance_m)} m ${from}`;
}

// ------------------------------------------------------------------ component
export default function ProjectSiteVisits({ projectId, projectName }) {
  const { hasPerm } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");
  const [blocked, setBlocked] = useState(null);
  const [notes, setNotes] = useState("");
  const [viewer, setViewer] = useState(null);
  const [fence, setFence] = useState(null);
  const [focusId, setFocusId] = useState(null);
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);
  const photoTarget = useRef(null);
  const canRemoveAny = hasPerm("attendance.update") || hasPerm("employees.update");
  const isPhone = typeof window !== "undefined" && window.matchMedia
    && window.matchMedia("(pointer: coarse)").matches;

  const load = useCallback(async () => {
    try {
      const { data: body } = await api.get(`/projects/${projectId}/site-visits`);
      setData(body);
      setLoadError("");
      setNotes(body.my_open_visit?.project_id === projectId ? (body.my_open_visit.notes || "") : "");
      return body;
    } catch (e) {
      setLoadError(errText(e, "Could not load site visits"));
      return null;
    } finally {
      setLoading(false);
    }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const open = data?.my_open_visit || null;
  const openHere = open && open.project_id === projectId ? open : null;
  const openElsewhere = open && open.project_id !== projectId ? open : null;
  const visits = useMemo(() => data?.visits || [], [data]);
  const fences = useMemo(() => (data?.site_fences || []).map((f) => ({ ...f, kind: "site" })), [data]);

  const pins = useMemo(() => visits.filter((v) => v.lat != null && v.lng != null).map((v) => ({
    id: v.id, lat: v.lat, lng: v.lng, inside: v.geo_status === "inside", shape: "square",
    faded: v.status !== "open", title: v.employee_name,
    lines: [
      v.employee_name,
      `${formatDate(v.date)} · ${formatTime(v.check_in_at)}${v.check_out_at ? ` – ${formatTime(v.check_out_at)}` : v.status === "open" ? " · on site now" : ""}`,
      GEO_LABEL[v.geo_status]?.label,
      v.photo_count ? `${v.photo_count} photo${v.photo_count === 1 ? "" : "s"}` : null,
    ],
  })), [visits]);

  const checkIn = async (force = false, knownGps = null) => {
    setBusy("checkin");
    let gps = knownGps;
    try {
      if (!gps) gps = await getGPS();
    } catch (ge) {
      toast.error(ge.message);
      setBusy("");
      return;
    }
    try {
      await api.post(`/projects/${projectId}/site-visits`, {
        ...gps, notes: "", force_outside: force, device_label: deviceLabel(),
      });
      setBlocked(null);
      toast.success(force ? "Visit recorded and sent for approval" : "Checked in on site");
      await load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d && typeof d === "object" && ["outside_geofence", "no_site_fence", "gps_accuracy_low"].includes(d.code)) {
        setBlocked({ ...d, gps });
      } else {
        toast.error(errText(e, "Could not check in"));
        if (d?.code === "visit_open") await load();
      }
    } finally {
      setBusy("");
    }
  };

  const checkOut = async () => {
    if (!openHere) return;
    const ok = await confirmAction({
      title: "Finish this site visit?",
      body: "You can still add photos and notes until the end of today. Your working day continues — check out from Attendance when you leave work.",
      confirmLabel: "Finish visit",
    });
    if (!ok) return;
    setBusy("checkout");
    let gps = {};
    try { gps = await getGPS(); } catch { /* location at check-out is optional */ }
    try {
      await api.post(`/site-visits/${openHere.id}/check-out`, { ...gps, notes });
      toast.success("Visit finished");
      await load();
    } catch (e) {
      toast.error(errText(e, "Could not finish the visit"));
    } finally {
      setBusy("");
    }
  };

  const saveNotes = async (visitId, value) => {
    setBusy("notes");
    try {
      await api.patch(`/site-visits/${visitId}`, { notes: value });
      toast.success("Notes saved");
      await load();
    } catch (e) {
      toast.error(errText(e, "Could not save the notes"));
    } finally {
      setBusy("");
    }
  };

  const pickPhotos = (visitId, camera) => {
    photoTarget.current = visitId;
    const input = camera ? cameraRef.current : galleryRef.current;
    if (input) { input.value = ""; input.click(); }
  };

  const uploadPhotos = async (fileList) => {
    // The open visit is the safe default for keyboard/assistive activation and
    // automated file-picker flows where the hidden input changes directly.
    const visitId = photoTarget.current || openHere?.id;
    const visit = visits.find((v) => v.id === visitId) || openHere;
    const room = Math.max(0, (data?.max_photos || 20) - (visit?.photo_count || 0));
    const files = Array.from(fileList || []).slice(0, room);
    if (!visitId || files.length === 0) {
      if (fileList?.length && room === 0) toast.error("This visit already has the maximum number of photos");
      return;
    }
    setBusy("photo");
    let gps = null;
    try { gps = await getGPS(); } catch { gps = null; }
    let saved = 0;
    for (const original of files) {
      const file = await shrinkPhoto(original);
      const form = new FormData();
      form.append("upload", file, file.name || "site-photo.jpg");
      if (gps) {
        form.append("lat", String(gps.lat));
        form.append("lng", String(gps.lng));
        form.append("accuracy_m", String(gps.accuracy_m));
      }
      if (original.lastModified) form.append("taken_at", new Date(original.lastModified).toISOString());
      try {
        await api.post(`/site-visits/${visitId}/photos`, form);
        saved += 1;
      } catch (e) {
        toast.error(errText(e, "Could not upload the photo"));
        break;
      }
    }
    if (saved) {
      toast.success(saved === 1 ? "Photo added" : `${saved} photos added`);
      if (!gps) toast("Saved without location — location permission is off.");
    }
    setBusy("");
    await load();
  };

  const removePhoto = async (visit, photo) => {
    if (!await confirmAction("Remove this photo?\nThe photo is deleted from the visit and cannot be recovered.")) return;
    try {
      await api.delete(`/site-visits/${visit.id}/photos/${photo.id}`);
      toast.success("Photo removed");
      setViewer(null);
      await load();
    } catch (e) {
      toast.error(errText(e, "Could not remove the photo"));
    }
  };

  const startFence = async () => {
    setFence({ lat: "", lng: "", radius_m: 100 });
    try {
      const gps = await getGPS();
      setFence((f) => ({ ...(f || {}), lat: gps.lat, lng: gps.lng }));
    } catch {
      /* pick on the map instead */
    }
  };

  const saveFence = async () => {
    if (fence?.lat === "" || fence?.lng === "" || fence?.lat == null) {
      toast.error("Tap the map to place the site pin");
      return;
    }
    setBusy("fence");
    try {
      await api.post("/attendance/locations", {
        name: `${projectName || "Project"} site`.slice(0, 120), kind: "site", project_id: projectId,
        lat: Number(fence.lat), lng: Number(fence.lng), radius_m: Number(fence.radius_m) || 100, is_active: true,
      });
      toast.success("Site location saved");
      setFence(null);
      setBlocked(null);
      await load();
    } catch (e) {
      toast.error(errText(e, "Could not save the site location"));
    } finally {
      setBusy("");
    }
  };

  if (loading) return <div className="card-flat text-sm text-[var(--ink-3)]" data-testid="site-visits-loading">Loading site visits…</div>;
  if (loadError) {
    return (
      <div className="card-flat flex items-center justify-between gap-3" role="alert">
        <span className="text-sm text-[var(--danger)]">{loadError}</span>
        <button type="button" className="btn-ghost text-xs" onClick={load}><ArrowsClockwise size={14} /> Retry</button>
      </div>
    );
  }

  const scopeTitle = { all: "All visits", team: "Team visits", own: "Your visits" }[data.scope] || "Visits";

  return (
    <div className="space-y-6" data-testid="site-visits">
      {/* hidden pickers: camera (phone) and gallery/files */}
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
             aria-hidden="true" tabIndex={-1} onChange={(e) => uploadPhotos(e.target.files)} data-testid="site-photo-camera" />
      <input ref={galleryRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" multiple className="hidden"
             aria-hidden="true" tabIndex={-1} onChange={(e) => uploadPhotos(e.target.files)} data-testid="site-photo-input" />

      {/* ---------------- my visit ---------------- */}
      {openHere ? (
        <div className="card-flat space-y-4 border-[var(--accent)]" data-testid="site-visit-open">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="overline mb-1">YOU ARE ON SITE</div>
              <div className="font-semibold text-lg">Since {formatTime(openHere.check_in_at)}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--ink-2)]">
                <span className={`status-chip ${GEO_LABEL[openHere.geo_status]?.cls || ""}`}>{GEO_LABEL[openHere.geo_status]?.label}</span>
                {openHere.geo_distance_m != null && <span>{Math.round(openHere.geo_distance_m)} m from the site pin</span>}
                {openHere.attendance_created && openHere.geo_status !== "inside" && <span>Attendance sent for approval</span>}
              </div>
            </div>
            <button type="button" className="btn-primary w-full sm:w-auto" onClick={checkOut} disabled={!!busy}
                    data-testid="site-visit-checkout">
              <SignOut size={16} /> {busy === "checkout" ? "Finishing…" : "Finish visit"}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {isPhone && (
              <button type="button" className="btn-primary flex-1 sm:flex-none" onClick={() => pickPhotos(openHere.id, true)}
                      disabled={!!busy} data-testid="site-photo-take">
                <Camera size={16} /> Take photo
              </button>
            )}
            <button type="button" className={`${isPhone ? "btn-ghost" : "btn-primary"} flex-1 sm:flex-none`}
                    onClick={() => pickPhotos(openHere.id, false)} disabled={!!busy} data-testid="site-photo-upload">
              <Images size={16} /> {busy === "photo" ? "Uploading…" : isPhone ? "From gallery" : "Add photos"}
            </button>
            <span className="text-xs text-[var(--ink-3)] self-center">
              {openHere.photo_count}/{data.max_photos} photos · time and location are recorded with each photo
            </span>
          </div>
          <div>
            <label htmlFor="site-visit-notes" className="text-sm font-semibold">Visit notes</label>
            <textarea id="site-visit-notes" className="input-flat w-full mt-1" rows={3} maxLength={2000}
                      placeholder="What did you check? Issues, measurements, instructions given…"
                      value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="site-visit-notes" />
            <div className="flex justify-end mt-2">
              <button type="button" className="btn-ghost text-xs" disabled={!!busy || notes === (openHere.notes || "")}
                      onClick={() => saveNotes(openHere.id, notes)} data-testid="site-visit-save-notes">
                <NotePencil size={14} /> Save notes
              </button>
            </div>
          </div>
          {openHere.photos?.length > 0 && (
            <PhotoGrid visit={openHere} onOpen={(p) => setViewer({ visit: openHere, photo: p })} />
          )}
        </div>
      ) : openElsewhere ? (
        <div className="card-flat flex items-center justify-between gap-3 flex-wrap" data-testid="site-visit-elsewhere">
          <div className="text-sm">
            You are checked in at <strong>{openElsewhere.project_name}</strong> since {formatTime(openElsewhere.check_in_at)}.
            Finish that visit before starting one here.
          </div>
          <Link to={`/projects/${openElsewhere.project_id}`} className="btn-ghost text-xs">Open that project</Link>
        </div>
      ) : data.can_check_in ? (
        <div className="card-flat space-y-3" data-testid="site-visit-start">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="font-semibold">Visiting the site?</div>
              <p className="text-sm text-[var(--ink-2)] mt-0.5 max-w-xl">
                Check in when you reach the site. Your location is checked against the site fence;
                if this is your first check-in today it also marks your attendance.
              </p>
            </div>
            <button type="button" className="btn-primary w-full sm:w-auto" onClick={() => checkIn(false)}
                    disabled={!!busy} data-testid="site-visit-checkin">
              <SignIn size={16} /> {busy === "checkin" ? "Reading location…" : "Check in on site"}
            </button>
          </div>
          {blocked && (
            <div className="border border-[var(--line-strong)] bg-[var(--warning-soft)] p-3 space-y-3 rounded-[var(--radius)]"
                 role="alert" data-testid="site-visit-blocked">
              <div className="flex items-start gap-2 text-sm">
                <WarningCircle size={18} className="shrink-0 text-[var(--warning)]" aria-hidden="true" />
                <span>{blocked.message}</span>
              </div>
              {blocked.code !== "gps_accuracy_low" && blocked.gps && (
                <CheckInMap height={220} testid="site-visit-blocked-map" fences={fences}
                            pins={[{ id: "me", lat: blocked.gps.lat, lng: blocked.gps.lng, inside: false, shape: "square", title: "You", lines: ["You are here", `±${blocked.gps.accuracy_m} m`] }]} />
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-ghost text-xs" onClick={() => checkIn(false)} disabled={!!busy}>
                  <ArrowsClockwise size={14} /> Try again
                </button>
                {blocked.code !== "gps_accuracy_low" && (
                  <button type="button" className="btn-primary text-xs" onClick={() => checkIn(true, blocked.gps)}
                          disabled={!!busy} data-testid="site-visit-force">
                    <MapPin size={14} /> Record visit &amp; send for approval
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card-flat text-sm text-[var(--ink-2)]" data-testid="site-visit-cannot">
          {data.has_employee_profile
            ? "You can view visits on this project, but site check-in is not available for your role."
            : "Site check-in needs an employee profile linked to your login. Ask HR to link it."}
        </div>
      )}

      {/* ---------------- site location ---------------- */}
      {fences.length === 0 && data.can_manage_fence && !fence && (
        <div className="card-flat flex items-center justify-between gap-3 flex-wrap" data-testid="site-fence-missing">
          <div className="text-sm text-[var(--ink-2)] max-w-xl">
            <strong className="text-[var(--ink)]">No site location yet.</strong> Set it so check-ins here are verified automatically
            instead of waiting for approval.
          </div>
          <button type="button" className="btn-ghost text-xs" onClick={startFence} data-testid="site-fence-set">
            <Crosshair size={14} /> Set site location
          </button>
        </div>
      )}
      {fence && (
        <div className="card-flat space-y-3" data-testid="site-fence-editor">
          <div className="flex items-center justify-between">
            <div className="font-semibold">Site location</div>
            <button type="button" className="btn-icon" aria-label="Close" onClick={() => setFence(null)}><X size={16} /></button>
          </div>
          <p className="text-sm text-[var(--ink-2)]">Tap the map or drag the pin to the site entrance. Your current location is used to start.</p>
          <GeoFenceMap lat={fence.lat} lng={fence.lng} radius={fence.radius_m} height={300}
                       onPick={(lat, lng) => setFence((f) => ({ ...(f || {}), lat, lng }))} />
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="font-semibold">Radius (m)</span>
              <input type="number" min="10" max="5000" className="input-flat mt-1 w-28 block" value={fence.radius_m}
                     onChange={(e) => setFence((f) => ({ ...f, radius_m: e.target.value }))} data-testid="site-fence-radius" />
            </label>
            <button type="button" className="btn-primary" onClick={saveFence} disabled={!!busy} data-testid="site-fence-save">
              <CheckCircle size={16} /> Save site location
            </button>
          </div>
        </div>
      )}

      {/* ---------------- visits ---------------- */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="overline">{scopeTitle.toUpperCase()} <span className="font-mono text-[var(--ink-3)]">{visits.length}</span></div>
          {(pins.length > 0 || fences.length > 0) && <MapLegend />}
        </div>
        {(pins.length > 0 || fences.length > 0) && (
          <CheckInMap pins={pins} fences={fences} height={300} focusId={focusId} testid="site-visits-map" />
        )}
        {visits.length === 0 && (
          <div className="card-flat text-sm text-[var(--ink-3)] text-center py-8" data-testid="site-visits-empty">
            No site visits recorded on this project yet.
          </div>
        )}
        {visits.map((v) => (
          <VisitCard key={v.id} v={v} busy={busy} maxPhotos={data.max_photos} isPhone={isPhone}
                     isOpenHere={openHere?.id === v.id}
                     onFocus={() => setFocusId(v.id)}
                     onPhoto={(camera) => pickPhotos(v.id, camera)}
                     onSaveNotes={(value) => saveNotes(v.id, value)}
                     onOpenPhoto={(p) => setViewer({ visit: v, photo: p })} />
        ))}
      </div>

      {viewer && (
        <PhotoViewer viewer={viewer} onClose={() => setViewer(null)}
                     canRemove={viewer.visit.can_edit || canRemoveAny}
                     onRemove={() => removePhoto(viewer.visit, viewer.photo)} />
      )}
    </div>
  );
}

function PhotoGrid({ visit, onOpen }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2" data-testid={`site-visit-photos-${visit.id}`}>
      {visit.photos.map((p) => (
        <button key={p.id} type="button" onClick={() => onOpen(p)}
                className="relative aspect-square overflow-hidden rounded-[var(--radius-sm)] border border-[var(--line)] group"
                aria-label={`Open photo taken at ${formatTime(p.captured_at)}`} data-testid="site-photo-thumb">
          <AuthImage src={`/site-visits/${visit.id}/photos/${p.id}`} alt={p.caption || `Site photo ${formatTime(p.captured_at)}`}
                     className="w-full h-full object-cover" />
          <span className="absolute bottom-0 inset-x-0 bg-black/55 text-white text-[10px] px-1.5 py-0.5 text-left tabular-nums">
            {formatTime(p.captured_at)}{p.distance_m != null ? ` · ${Math.round(p.distance_m)} m` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

function VisitCard({ v, busy, maxPhotos, isPhone, isOpenHere, onFocus, onPhoto, onSaveNotes, onOpenPhoto }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(v.notes || "");
  useEffect(() => { setDraft(v.notes || ""); }, [v.notes]);
  const geo = GEO_LABEL[v.geo_status] || {};
  const canAddPhoto = v.can_edit && !isOpenHere && (v.photo_count || 0) < maxPhotos;
  return (
    <div className="card-flat space-y-3" data-testid={`site-visit-${v.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold">{v.employee_name}</span>
            <span className={`status-chip ${geo.cls || ""}`}>{geo.label}</span>
            {v.status === "open" && <span className="status-chip chip-sent">On site now</span>}
            {v.auto_closed && <span className="status-chip chip-draft">Not checked out</span>}
          </div>
          <div className="text-sm text-[var(--ink-2)] mt-1 tabular-nums">
            {formatDate(v.date)} · {formatTime(v.check_in_at)}
            {v.check_out_at ? ` – ${formatTime(v.check_out_at)}` : ""}
            {v.duration_minutes != null ? ` · ${fmtDuration(v.duration_minutes)}` : ""}
            {v.accuracy_m ? <span className="text-[var(--ink-3)]"> · GPS ±{Math.round(v.accuracy_m)} m</span> : null}
          </div>
        </div>
        <RowActions label={`visit by ${v.employee_name}`} testid={`site-visit-actions-${v.id}`} actions={[
          { label: "Show on map", icon: MapPin, onSelect: onFocus, hidden: v.lat == null },
          { label: "Add photos", icon: Images, onSelect: () => onPhoto(false), hidden: !canAddPhoto },
          { label: "Take photo", icon: Camera, onSelect: () => onPhoto(true), hidden: !canAddPhoto || !isPhone },
          { label: "Edit notes", icon: NotePencil, onSelect: () => setEditing(true), hidden: !v.can_edit || isOpenHere },
        ]} />
      </div>
      {editing ? (
        <div className="space-y-2">
          <label htmlFor={`notes-${v.id}`} className="sr-only">Visit notes</label>
          <textarea id={`notes-${v.id}`} className="input-flat w-full" rows={3} maxLength={2000}
                    value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-ghost text-xs" onClick={() => { setEditing(false); setDraft(v.notes || ""); }}>Cancel</button>
            <button type="button" className="btn-primary text-xs" disabled={!!busy}
                    onClick={async () => { await onSaveNotes(draft); setEditing(false); }}>Save notes</button>
          </div>
        </div>
      ) : v.notes ? (
        <p className="text-sm whitespace-pre-line text-[var(--ink)]">{v.notes}</p>
      ) : null}
      {/* the open visit's photos are already shown in the "on site" card above */}
      {!isOpenHere && v.photos?.length > 0 && <PhotoGrid visit={v} onOpen={onOpenPhoto} />}
    </div>
  );
}

function PhotoViewer({ viewer, onClose, canRemove, onRemove }) {
  const { visit, photo } = viewer;
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-3 sm:p-6"
         role="dialog" aria-modal="true" aria-label="Site photo"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} data-testid="site-photo-viewer">
      <div className="bg-white w-full max-w-3xl max-h-[92vh] overflow-auto rounded-[var(--radius-lg)]">
        <div className="flex items-center justify-between gap-2 p-3 border-b border-[var(--line)]">
          <div className="min-w-0 text-sm">
            <div className="font-semibold truncate">{visit.employee_name} · {visit.project_name}</div>
            <div className="text-[var(--ink-2)] tabular-nums">
              {formatDateTime(photo.captured_at)}{takenNote(photo)}
              {" · "}{photoWhere(photo)}{photo.accuracy_m != null ? ` · ±${Math.round(photo.accuracy_m)} m` : ""}
            </div>
          </div>
          <div className="flex items-center gap-1">
            {canRemove && (
              <button type="button" className="btn-ghost text-xs text-[var(--danger)]" onClick={onRemove} data-testid="site-photo-remove">
                <Trash size={14} /> Remove
              </button>
            )}
            <button type="button" className="btn-icon" aria-label="Close photo" onClick={onClose} autoFocus><X size={18} /></button>
          </div>
        </div>
        <AuthImage src={`/site-visits/${visit.id}/photos/${photo.id}`} alt={photo.caption || "Site photo"}
                   className="w-full h-auto max-h-[75vh] object-contain bg-[var(--surface-2)]" testid="site-photo-large" />
        {photo.caption && <div className="p-3 text-sm">{photo.caption}</div>}
      </div>
    </div>
  );
}
