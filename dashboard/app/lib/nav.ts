// Every page of the dashboard, in the order of the left bar. `step` is the build step in
// PLAN-DASHBOARD.md that makes the page; `will` is what it shows once built.

export type Page = { slug: string; name: string; icon: string; built?: boolean; step?: string; will?: string };

export const GROUPS: { title: string; pages: Page[] }[] = [
  {
    title: "Run",
    pages: [
      { slug: "", name: "Home", icon: "home", built: true },
      {
        slug: "live", name: "Live call", icon: "phone", step: "D3",
        will: "The Call my phone button for real, the call as a back and forth while it happens, what the engine has learned so far, and a free typed test call.",
      },
      {
        slug: "calls", name: "Calls", icon: "list", step: "D2",
        will: "A table of every call with filters, and each call opened as a back and forth with times, the judge's reason, and your own verdict.",
      },
    ],
  },
  {
    title: "Content",
    pages: [
      {
        slug: "schemes", name: "Schemes", icon: "book", step: "S1",
        will: "A table of all chosen schemes with their state per language, the spoken card and clips for each, and the way to add a new scheme stage by stage.",
      },
      {
        slug: "lines", name: "Voice lines", icon: "wave", step: "S1",
        will: "The fixed lines the AI can say, in Hindi, Marathi and English, each with a play button.",
      },
    ],
  },
  {
    title: "Watch",
    pages: [
      {
        slug: "usage", name: "Usage and money", icon: "coin", step: "D4",
        will: "One card per service: Muse in rupees against its caps, Sarvam, Groq and Twilio in units, with a chart per day.",
      },
      {
        slug: "quality", name: "Quality", icon: "gauge", step: "D4",
        will: "Judge pass rate, reply times, how often a caller was not understood, and how often voice fell back to keypad.",
      },
    ],
  },
  {
    title: "Know",
    pages: [
      {
        slug: "plan", name: "Plan and architecture", icon: "map", step: "D5",
        will: "How a call flows, the phases done and left, the project log, and your to-do list as a checklist.",
      },
      {
        slug: "system", name: "System", icon: "chip", step: "D5",
        will: "The smoke checks, the code version, the last restarts, and the tail of the server log.",
      },
    ],
  },
  {
    title: "",
    pages: [
      {
        slug: "settings", name: "Settings", icon: "gear", step: "D6",
        will: "API keys with a Test button (values are never shown), the phone the button rings, the Muse guard, and the engine's numbers.",
      },
    ],
  },
];

export const PAGES: Page[] = GROUPS.flatMap((g) => g.pages);
