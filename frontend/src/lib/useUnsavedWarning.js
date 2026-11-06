import { useEffect } from "react";

/**
 * Warn before closing or reloading the tab while a form has unsaved changes.
 * (In-app navigation keeps state per page; the browser prompt covers the
 * case that actually loses work: closing, reloading or leaving the site.)
 */
export default function useUnsavedWarning(dirty) {
  useEffect(() => {
    if (!dirty) return undefined;
    const onBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
}
