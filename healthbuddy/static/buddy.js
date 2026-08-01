/* HealthBuddy buddy.js — the living companion on the dashboard.
   =========================================================================
   Everything here is drawn as inline SVG + CSS animation, so it's tiny, works
   offline inside the APK, and needs no image assets or animation library.

   The Buddy's look is a pure function of state:
       mood     ← today's score (+ the last logged mood, which wins if recent)
       gear     ← level (2 = sneakers, 3 = headband, 5 = cape)
       aura     ← longest active streak (3+ days = flames)
   So it can never drift out of sync with the data — re-render and it's right.
   ========================================================================= */
"use strict";

const BUDDY_MOODS = {
  sleepy:    { eyes: "sleepy",  mouth: "small",  line: "Still booting up… 🥱" },
  neutral:   { eyes: "open",    mouth: "small",  line: "Ready when you are!" },
  happy:     { eyes: "open",    mouth: "smile",  line: "This is going well 😊" },
  energetic: { eyes: "star",    mouth: "grin",   line: "LOOK AT US GO! 🔥" },
  calm:      { eyes: "closed",  mouth: "smile",  line: "Nice and peaceful 🌿" },
  cool:      { eyes: "shades",  mouth: "grin",   line: "Feeling unstoppable 😎" },
  sad:       { eyes: "open",    mouth: "frown",  line: "Rough day? I'm here. 💜" },
};

/* Level unlocks — kept small and clearly worth reaching. */
const BUDDY_GEAR = [
  { level: 2, key: "sneakers", emoji: "👟", name: "Fresh sneakers" },
  { level: 3, key: "headband", emoji: "🎽", name: "Sport headband" },
  { level: 5, key: "cape",     emoji: "🦸", name: "Hero cape" },
];

function buddyMood({ score = 0, mood = null, hour = new Date().getHours() }) {
  if (mood != null) {                    // an explicit mood log wins for the day
    if (mood >= 5) return "cool";
    if (mood === 4) return "happy";
    if (mood === 3) return "calm";
    if (mood <= 2) return "sad";
  }
  if (score >= 70) return "energetic";
  if (score >= 40) return "happy";
  if (score >= 15) return "neutral";
  return hour < 10 ? "sleepy" : "neutral";
}

/* ---------- the avatar itself ---------- */
function buddySVG(state) {
  const m = BUDDY_MOODS[state.mood] || BUDDY_MOODS.neutral;
  const gear = BUDDY_GEAR.filter((g) => (state.level || 1) >= g.level).map((g) => g.key);

  const eyes = {
    open:   `<circle cx="-15" cy="-6" r="5.5" fill="#241028"/><circle cx="15" cy="-6" r="5.5" fill="#241028"/>
             <circle cx="-13" cy="-8" r="2" fill="#fff"/><circle cx="17" cy="-8" r="2" fill="#fff"/>`,
    sleepy: `<path d="M-21-6q6 5 12 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>
             <path d="M9-6q6 5 12 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>`,
    closed: `<path d="M-21-4q6-6 12 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>
             <path d="M9-4q6-6 12 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>`,
    star:   `<text x="-15" y="1" font-size="16" text-anchor="middle">✨</text>
             <text x="15" y="1" font-size="16" text-anchor="middle">✨</text>`,
    shades: `<rect x="-26" y="-14" width="52" height="16" rx="7" fill="#241028"/>
             <rect x="-23" y="-12" width="18" height="11" rx="5" fill="#4a3a63"/>
             <rect x="5" y="-12" width="18" height="11" rx="5" fill="#4a3a63"/>`,
  }[m.eyes];

  const mouth = {
    small: `<path d="M-6 12q6 4 12 0" stroke="#241028" stroke-width="3" fill="none" stroke-linecap="round"/>`,
    smile: `<path d="M-12 10q12 12 24 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>`,
    grin:  `<path d="M-14 8q14 16 28 0z" fill="#241028"/><path d="M-8 15q8 6 16 0z" fill="#FF7A9B"/>`,
    frown: `<path d="M-11 16q11-10 22 0" stroke="#241028" stroke-width="3.5" fill="none" stroke-linecap="round"/>`,
  }[m.mouth];

  return `
  <svg class="buddy-svg" viewBox="-100 -110 200 220" role="img"
       aria-label="Your buddy looks ${state.mood}">
    <defs>
      <radialGradient id="bdyBody" cx="35%" cy="30%">
        <stop offset="0" stop-color="#9BE86F"/><stop offset="1" stop-color="#5FC93F"/>
      </radialGradient>
      <linearGradient id="bdyAura" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0" stop-color="#FF8A5C"/><stop offset="1" stop-color="#FFD166"/>
      </linearGradient>
    </defs>

    ${state.aura ? `<g class="buddy-flames" aria-hidden="true">
      ${[-46, -16, 16, 46].map((x, i) => `
        <path class="flame f${i}" d="M${x} 66 q-13-24 0-44 q13 20 0 44z" fill="url(#bdyAura)" opacity=".85"/>`).join("")}
    </g>` : ""}

    <g class="buddy-body">
      ${gear.includes("cape") ? `<path class="buddy-cape" d="M-34-16 C-70 20 -60 62 -30 66 L30 66 C60 62 70 20 34-16z"
           fill="#FF5C8A" opacity=".9"/>` : ""}
      <!-- leaf sprout on the head: the brand mark, alive -->
      <path class="buddy-leaf" d="M4-72 q26-10 34-34 q-28 2-36 26z" fill="#7ED957"/>
      <path d="M2-74 q-2-16 2-24" stroke="#5FC93F" stroke-width="5" fill="none" stroke-linecap="round"/>
      <!-- body -->
      <ellipse cx="0" cy="6" rx="60" ry="62" fill="url(#bdyBody)"/>
      <ellipse cx="0" cy="24" rx="42" ry="34" fill="#EAFBE0" opacity=".55"/>
      ${gear.includes("headband") ? `<path d="M-58-26q58-26 116 0" stroke="#FF5C8A" stroke-width="11"
           fill="none" stroke-linecap="round"/>` : ""}
      <!-- face -->
      <g transform="translate(0,4)">${eyes}${mouth}</g>
      <!-- cheeks -->
      <circle cx="-38" cy="14" r="8" fill="#FF9BB5" opacity=".55"/>
      <circle cx="38" cy="14" r="8" fill="#FF9BB5" opacity=".55"/>
      <!-- arms -->
      <path class="buddy-arm-l" d="M-58 14 q-26 6 -30 26" stroke="#5FC93F" stroke-width="12"
            fill="none" stroke-linecap="round"/>
      <path class="buddy-arm-r" d="M58 14 q26 6 30 26" stroke="#5FC93F" stroke-width="12"
            fill="none" stroke-linecap="round"/>
      <!-- feet / sneakers -->
      ${gear.includes("sneakers")
        ? `<ellipse cx="-24" cy="72" rx="20" ry="11" fill="#F4EDE4"/><ellipse cx="24" cy="72" rx="20" ry="11" fill="#F4EDE4"/>
           <path d="M-42 74h36M6 74h36" stroke="#FF5C8A" stroke-width="4" stroke-linecap="round"/>`
        : `<ellipse cx="-22" cy="70" rx="16" ry="9" fill="#5FC93F"/><ellipse cx="22" cy="70" rx="16" ry="9" fill="#5FC93F"/>`}
    </g>
  </svg>`;
}

/* ---------- dashboard hero: buddy inside the score ring ---------- */
function buddyHeroHTML(d) {
  const score = d.score.score;
  /* today's mood: the API gives count + summed value per habit, so the
     average is the mood the buddy should wear. */
  const md = d.score.today.mood || {};
  const moodLog = md.count ? Math.round((md.total || 0) / md.count) : null;
  const streaks = d.streaks || {};
  const best = Math.max(0, ...Object.values(streaks));
  const state = { mood: buddyMood({ score, mood: moodLog }), level: d.level, aura: best >= 3 };
  const C = 2 * Math.PI * 88;
  return `
    <div class="buddy-stage" id="buddy-stage">
      <svg class="buddy-ring" viewBox="0 0 200 200" aria-label="Today's score: ${score} of 100">
        <defs><linearGradient id="bRing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#FF8A5C"/><stop offset="1" stop-color="#FF5C8A"/></linearGradient></defs>
        <circle class="track" cx="100" cy="100" r="88" fill="none" stroke-width="9"/>
        <circle class="arc" cx="100" cy="100" r="88" fill="none" stroke-width="9"
          stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - score / 100)}"/>
      </svg>
      <button class="buddy-tap ${state.aura ? "is-fired" : ""}" id="buddy-tap"
              aria-label="Say hi to your buddy">${buddySVG(state)}</button>
      <div class="buddy-caption">
        <span class="buddy-score">${score}</span>
        <span class="muted small" id="buddy-line">${esc(BUDDY_MOODS[state.mood].line)}</span>
        ${best >= 3 ? `<span class="chip done">🔥 ${best}-day streak — on fire!</span>` : ""}
      </div>
    </div>`;
}

/* Tap → wave + a random encouraging line. Pure delight, no data change. */
const BUDDY_TAPS = [
  "Hey! 👋", "You're doing better than you think.", "Water break? I'll wait. 💧",
  "One tiny thing counts. Promise.", "I'm basically your hype squad. 📣",
  "Stretch with me? 🙆", "Look at that streak energy 🔥",
];
function wireBuddyTap() {
  const btn = document.getElementById("buddy-tap");
  if (!btn) return;
  btn.onclick = () => {
    btn.classList.remove("is-waving");
    void btn.offsetWidth;                    // restart the CSS animation
    btn.classList.add("is-waving");
    const line = document.getElementById("buddy-line");
    if (line) line.textContent = BUDDY_TAPS[Math.floor(Math.random() * BUDDY_TAPS.length)];
    buddyBurst(btn, ["💚", "✨"], 8);
  };
}

/* ---------- micro-animations for logging ---------- */
function buddyBurst(anchor, emojis, count = 10) {
  const host = anchor.closest(".check-row, .card, .buddy-stage") || anchor;
  host.style.position = host.style.position || "relative";
  for (let i = 0; i < count; i++) {
    const s = document.createElement("span");
    s.className = "hb-particle";
    s.textContent = emojis[i % emojis.length];
    s.style.left = 30 + Math.random() * 40 + "%";
    s.style.animationDelay = (i * 45) + "ms";
    s.style.setProperty("--dx", (Math.random() * 80 - 40) + "px");
    host.appendChild(s);
    setTimeout(() => s.remove(), 1400);
  }
}

/* Each habit gets its own little celebration, per the design brief. */
function habitAnimation(type, rowEl) {
  if (!rowEl) return;
  switch (type) {
    case "water":
      rowEl.classList.add("fx-splash");
      buddyBurst(rowEl, ["💧", "🫧"], 8);
      break;
    case "meal":
      rowEl.classList.add("fx-pop");
      buddyBurst(rowEl, ["🥗", "💚", "✨"], 9);
      break;
    case "sleep":
      rowEl.classList.add("fx-night");
      buddyBurst(rowEl, ["🌙", "💤", "⭐"], 7);
      break;
    case "mood":
      rowEl.classList.add("fx-pop");
      break;
    default:
      rowEl.classList.add("fx-pop");
  }
  setTimeout(() => rowEl.classList.remove("fx-splash", "fx-pop"), 1200);
  setTimeout(() => rowEl.classList.remove("fx-night"), 2600);
}

/* Mood gets the emoji-rain treatment using the emoji the user picked. */
const MOOD_FACES = { 1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄" };
function moodBurst(rowEl, value) {
  const face = MOOD_FACES[Math.round(value)] || "🙂";
  if (rowEl) buddyBurst(rowEl, [face], 12);
}

/* Steps: mini buddy jogs along the progress bar; finish-line tape at goal. */
function stepsTrackHTML(steps, goal) {
  const pct = Math.max(0, Math.min(100, Math.round((steps / goal) * 100)));
  const done = steps >= goal;
  return `<div class="steps-track ${done ? "is-done" : ""}">
      <div class="steps-fill" style="width:${pct}%"></div>
      <span class="steps-runner" style="left:calc(${pct}% - 12px)">${done ? "🏃‍♀️" : "🚶"}</span>
      <span class="steps-flag">${done ? "🎉" : "🏁"}</span>
    </div>`;
}

/* Level-up: a small unboxing moment that names the unlock. */
function celebrateLevelUp(level) {
  const unlock = BUDDY_GEAR.find((g) => g.level === level);
  modal(`<div style="text-align:center">
      <div class="levelup-burst" aria-hidden="true">🎁</div>
      <h2>Level ${level}!</h2>
      ${unlock
        ? `<p class="muted">Your buddy unlocked <strong>${unlock.emoji} ${esc(unlock.name)}</strong>.</p>
           <div class="levelup-buddy">${buddySVG({ mood: "energetic", level, aura: false })}</div>`
        : `<p class="muted">Your buddy is looking prouder already.</p>`}
      <button class="btn btn-primary btn-block section-gap" data-close>Nice!</button>
    </div>`);
  const host = document.querySelector(".modal-card") || document.body;
  buddyBurst(host, ["🎉", "✨", "🎊"], 14);
}
