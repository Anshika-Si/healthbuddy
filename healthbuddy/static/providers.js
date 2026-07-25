/* HealthBuddy providers.js — cross-platform device-data adapters.
   =================================================================
   The rest of the app NEVER asks "which OS is this?" — it asks
   Providers.activity.isAvailable() / .getDailySteps() and gets honest
   answers. Each platform implements the same interface:

     ActivityDataProvider:  isAvailable, requestPermission, getDailySteps
     DeviceWellbeingProvider: isAvailable, requestPermission, getScreenMinutes

   Current adapters:
   - WebActivityProvider: honest — browsers CANNOT read system-wide step
     counts, so isAvailable() is false. No fake data, ever.
   - ManualActivityProvider: always available; the user types the number
     (typing it is the consent).
   - AndroidActivityProvider / IOSActivityProvider: STUBS with clearly
     marked integration points. They activate when the app is wrapped with
     Capacitor (see BEGINNER_GUIDE Part 6): Android → Health Connect plugin,
     iOS → HealthKit plugin. Until then isAvailable() is false and the UI
     falls back to Manual — exactly as the product spec requires.
   ================================================================= */
"use strict";

/* Resolve a native plugin across Capacitor versions/injection modes:
   1) window.Capacitor.Plugins.Name (auto-populated from native registration)
   2) window.Capacitor.registerPlugin('Name') (proxy construction)
   Exposed globally so the diagnostic line can use it too. */
window.__hbPlugin = function (name) {
  const C = window.Capacitor;
  if (!C) return null;
  if (C.Plugins && C.Plugins[name]) return C.Plugins[name];
  if (typeof C.registerPlugin === "function") {
    try { return C.registerPlugin(name); } catch (_) { /* not registered */ }
  }
  return null;
};

const Providers = (() => {
  /* Detect a native wrapper (Capacitor injects window.Capacitor). */
  const native = () => window.Capacitor?.getPlatform?.() || null; // 'android' | 'ios' | null
  const plug = window.__hbPlugin;

  /* ---------- Activity (steps) ---------- */
  const HB = () => window.Capacitor?.Plugins?.HBHealth; // our native plugin
  const AndroidActivityProvider = {
    name: "health_connect",
    isAvailable: () => native() === "android" && !!HB(),
    requestPermission: async () => (await HB().requestStepPermission()).granted,
    getDailySteps: async () => (await HB().getTodaySteps()).steps,
  };
  const IOSActivityProvider = {
    name: "healthkit",
    isAvailable: () => native() === "ios" && !!HB(),
    requestPermission: async () => (await HB().requestStepPermission()).granted,
    getDailySteps: async () => (await HB().getTodaySteps()).steps,
  };
  const WebActivityProvider = {
    name: "web",
    isAvailable: () => false, // browsers cannot read system step counts — honest no.
    requestPermission: async () => false,
    getDailySteps: async () => null,
  };
  const ManualActivityProvider = {
    name: "manual",
    isAvailable: () => true,
    requestPermission: async () => true, // typing the number IS the permission
    async submit(steps) {
      return api("/activity/manual", { method: "POST", body: { steps } });
    },
  };

  /* ---------- Screen time ---------- */
  const AndroidWellbeingProvider = {
    name: "android_usage",
    isAvailable: () => native() === "android" && !!HB(),
    requestPermission: async () => {
      const { granted } = await HB().hasUsagePermission();
      if (granted) return true;
      await HB().openUsageAccessSettings(); // one system toggle, then back
      return false; // re-checked on next app open
    },
    getScreenMinutes: async () => {
      const { granted } = await HB().hasUsagePermission();
      if (!granted) return null;
      return (await HB().getTodayScreenTimeMinutes()).minutes;
    },
  };
  const IOSWellbeingProvider = {
    name: "ios_screentime",
    // Apple's Screen Time API is not readable by third-party apps in a way
    // that fits here — honest unavailability, per product spec.
    isAvailable: () => false,
    requestPermission: async () => false,
    getScreenMinutes: async () => null,
  };
  const WebWellbeingProvider = { name: "web", isAvailable: () => false,
    requestPermission: async () => false, getScreenMinutes: async () => null };
  const ManualWellbeingProvider = {
    name: "manual", isAvailable: () => true, requestPermission: async () => true,
    async submit(minutes) {
      return api("/wellbeing/manual", { method: "POST", body: { screen_time_minutes: minutes } });
    },
  };

  /* Pick the best available adapter for this device, manual as universal fallback. */
  const pick = (chain) => chain.find((p) => p.isAvailable());
  return {
    activity: {
      auto: () => pick([AndroidActivityProvider, IOSActivityProvider, WebActivityProvider]),
      manual: ManualActivityProvider,
      autoAvailable: () => !!pick([AndroidActivityProvider, IOSActivityProvider]),
    },
    wellbeing: {
      auto: () => pick([AndroidWellbeingProvider, IOSWellbeingProvider, WebWellbeingProvider]),
      manual: ManualWellbeingProvider,
      autoAvailable: () => !!pick([AndroidWellbeingProvider]),
    },
    platform: () => native() || "web",
    /* Auto-sync: called on app open + every home visit. Reads whatever the
       device allows and pushes it to the server in the normalized format.
       Silent, permission-gated, and a no-op on plain web. */
    async syncDeviceData() {
      const act = pick([AndroidActivityProvider, IOSActivityProvider]);
      if (act) {
        try {
          const steps = await act.getDailySteps();
          if (typeof steps === "number")
            await api("/activity/sync", { method: "POST",
              body: { steps, source: act.name } });
        } catch (_) { /* not granted yet — the UI offers the permission flow */ }
      }
      const wb = pick([AndroidWellbeingProvider]);
      if (wb) {
        try {
          const mins = await wb.getScreenMinutes();
          if (typeof mins === "number")
            await api("/wellbeing/sync", { method: "POST",
              body: { screen_time_minutes: mins, source: "android_usage" } });
        } catch (_) {}
      }
    },
  };
})();
