import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError } from "./api";
import "./styles.css";

const ICONS = {
  arrow: "M5 12h14M13 6l6 6-6 6",
  book: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5V5.5Zm0 0A2.5 2.5 0 0 1 6.5 8H20",
  check: "m5 12 4 4L19 6",
  chat: "M20 15a3 3 0 0 1-3 3H9l-5 3v-6a3 3 0 0 1-1-2V7a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v8Z",
  chevron: "m7 10 5 5 5-5",
  clock: "M12 7v5l3 2m7-2a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  close: "M6 6l12 12M18 6 6 18",
  download: "M12 3v12m0 0 5-5m-5 5-5-5M5 21h14",
  external: "M14 4h6v6m0-6-9 9M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6",
  fullscreen: "M8 3H3v5m13-5h5v5m0 8v5h-5M8 21H3v-5",
  hand: "M7.5 11V7.5a1.5 1.5 0 0 1 3 0V10m0-4.5a1.5 1.5 0 0 1 3 0V10m0-3a1.5 1.5 0 0 1 3 0v4m0-2a1.5 1.5 0 0 1 3 0v4.5c0 4.1-2.6 7.5-7 7.5h-1.2a6 6 0 0 1-4.7-2.3L3.4 14.6a1.6 1.6 0 0 1 2.4-2.1L7.5 14V11Z",
  layers: "M12 3 3 8l9 5 9-5-9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5",
  logout: "M10 17l5-5-5-5m5 5H3m10-8V3a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v4m0 10v4a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-1",
  microphone: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm-7 9a7 7 0 0 0 14 0M12 18v4m-4 0h8",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",
  move: "M12 2v20m0-20L9 5m3-3 3 3M2 12h20M2 12l3-3m-3 3 3 3m17-3-3-3m3 3-3 3m-7 7-3-3m3 3 3-3",
  note: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6M8 13h8M8 17h6",
  plus: "M12 5v14M5 12h14",
  search: "m21 21-4.3-4.3m2.3-5.7a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  sparkle: "m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Zm7 13 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z",
  stop: "M6 6h12v12H6z",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  trash: "M4 7h16m-10 4v6m4-6v6M9 7V4h6v3m-9 0 1 14h10l1-14",
  upload: "M12 16V4m0 0L7 9m5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3",
};

function Icon({ name, size = 18 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name] || ICONS.sparkle} />
    </svg>
  );
}

function formatDate(date, options = { month: "short", day: "numeric" }) {
  if (!date) return "";
  return new Intl.DateTimeFormat("en", options).format(new Date(date));
}

function formatOverdue(days) {
  if (!days) return "due today";
  return `${days}d past due`;
}

function initials(name = "Student") {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function useResizablePanel({ storageKey, defaultWidth, minWidth, maxWidth, direction }) {
  const clampWidth = (value) => Math.min(maxWidth, Math.max(minWidth, value));
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(`${storageKey}_width`));
    return Number.isFinite(saved) && saved > 0 ? clampWidth(saved) : defaultWidth;
  });
  const [open, setOpen] = useState(() => localStorage.getItem(`${storageKey}_open`) !== "false");
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(`${storageKey}_width`, String(width));
  }, [storageKey, width]);

  useEffect(() => {
    localStorage.setItem(`${storageKey}_open`, String(open));
  }, [open, storageKey]);

  function startResize(event) {
    if (!open || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
    };
    setResizing(true);
  }

  function moveResize(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    setWidth(clampWidth(drag.startWidth + ((event.clientX - drag.startX) * direction)));
  }

  function stopResize(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setResizing(false);
  }

  function resizeWithKeyboard(event) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const screenDirection = event.key === "ArrowRight" ? 1 : -1;
    setWidth((current) => clampWidth(current + (screenDirection * direction * 16)));
  }

  function toggle() {
    setOpen((current) => !current);
  }

  function resetWidth() {
    setWidth(defaultWidth);
  }

  return {
    width,
    open,
    resizing,
    toggle,
    resetWidth,
    resizeHandleProps: {
      onPointerDown: startResize,
      onPointerMove: moveResize,
      onPointerUp: stopResize,
      onPointerCancel: stopResize,
      onDoubleClick: resetWidth,
      onKeyDown: resizeWithKeyboard,
    },
  };
}

function flattenNodes(nodes = []) {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);
}

function findNode(nodes, id) {
  return flattenNodes(nodes).find((node) => node.id === id);
}

// Bump the layout version whenever the automatic geometry changes so stale
// hand-arranged coordinates cannot pull a new map back into an old shape.
const MINDMAP_POSITIONS_KEY = "study_mindmap_node_positions_v3";
const MINDMAP_FULLSCREEN_REQUEST_KEY = "study_mindmap_open_fullscreen";

function loadMindMapPositions() {
  try {
    return JSON.parse(localStorage.getItem(MINDMAP_POSITIONS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveMindMapPositions(positions) {
  localStorage.setItem(MINDMAP_POSITIONS_KEY, JSON.stringify(positions));
}

function requestMindMapFullscreen() {
  sessionStorage.setItem(MINDMAP_FULLSCREEN_REQUEST_KEY, "1");
}

function consumeMindMapFullscreenRequest() {
  const requested = sessionStorage.getItem(MINDMAP_FULLSCREEN_REQUEST_KEY) === "1";
  sessionStorage.removeItem(MINDMAP_FULLSCREEN_REQUEST_KEY);
  return requested;
}

function studyNodeIdFromHash() {
  const match = window.location.hash.match(/^#(?:study-node|subtopic)-(\d+)$/);
  return match ? Number(match[1]) : null;
}

function pdfSourceFromHash() {
  const match = window.location.hash.match(/^#pdf-source-(\d+)-page-(\d+)$/);
  return match ? { documentId: Number(match[1]), pageNumber: Number(match[2]) } : null;
}

function pdfSourceHref(source) {
  return `#pdf-source-${source.document_id}-page-${source.page_number}`;
}

function studyNodeHref(node) {
  if (!node) return "#study-map";
  return node.node_type === "subtopic" ? `#subtopic-${node.id}` : `#study-node-${node.id}`;
}

function updateStudyHash(node, { replace = false } = {}) {
  const nextHash = studyNodeHref(node);
  if (window.location.hash === nextHash) return;
  const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
  window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
}

function shortLine(text = "", fallback = "No summary yet.") {
  if (!text) return fallback;
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 110 ? `${normalized.slice(0, 107)}...` : normalized;
}

function svgTitleLines(text = "") {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && candidate.length > 17) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  if (lines.length <= 2) return lines;
  return [lines[0], `${lines[1].slice(0, 14)}...`];
}

function buildVisualizationModel(detail, content) {
  if (!detail || !content) return null;

  const fallbackNodes = [
    {
      id: "main",
      label: detail.title,
      kind: "main",
      description: content.explanation,
      group: "main",
      order: 0,
    },
    ...(content.key_points || []).slice(0, 6).map((point, index) => ({
      id: `idea_${index}`,
      label: shortLine(point, "Key idea"),
      kind: "concept",
      description: point,
      group: "ideas",
      order: index + 1,
    })),
  ];
  const plan = content.visualization || {
    type: "concept_map",
    title: detail.title,
    main_idea: content.explanation,
    nodes: fallbackNodes,
    connections: fallbackNodes.slice(1).map((node) => ({
      source: "main",
      target: node.id,
      label: "explains",
    })),
  };
  const rawNodes = [...(plan.nodes || [])].sort((left, right) => (left.order || 0) - (right.order || 0));
  const root = rawNodes.find((node) => node.kind === "main" || node.kind === "root") || rawNodes[0];
  const children = rawNodes.filter((node) => node.id !== root?.id);
  const positions = new Map();
  const spread = (items, y, width = 360) => {
    if (!items.length) return;
    items.forEach((node, index) => {
      positions.set(node.id, {
        x: items.length === 1 ? 250 : 70 + (index * width) / (items.length - 1),
        y,
      });
    });
  };

  if (root) positions.set(root.id, { x: 250, y: 62 });
  if (plan.type === "process") {
    rawNodes.forEach((node, index) => positions.set(node.id, {
      x: rawNodes.length === 1 ? 250 : 54 + (index * 392) / (rawNodes.length - 1),
      y: 190,
    }));
  } else if (plan.type === "hierarchy") {
    spread(children.slice(0, 4), 170, 360);
    spread(children.slice(4), 285, 360);
  } else if (plan.type === "comparison") {
    const groups = [...new Set(children.map((node) => node.group || "side"))];
    children.forEach((node, index) => {
      const groupIndex = Math.max(0, groups.indexOf(node.group || "side"));
      const inGroup = children.filter((item) => (item.group || "side") === (node.group || "side"));
      const itemIndex = inGroup.findIndex((item) => item.id === node.id);
      positions.set(node.id, {
        x: groups.length > 1 ? (groupIndex % 2 ? 365 : 135) : 250,
        y: 145 + itemIndex * 72,
      });
    });
  } else if (plan.type === "cycle") {
    children.forEach((node, index) => {
      const angle = (index / Math.max(children.length, 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.id, { x: 250 + Math.cos(angle) * 145, y: 195 + Math.sin(angle) * 115 });
    });
  } else {
    spread(children.slice(0, 4), 175, 360);
    spread(children.slice(4), 290, 360);
  }

  const nodes = rawNodes.map((node) => ({
    id: node.id,
    title: node.label,
    kind: node.kind || "concept",
    summary: node.description || "",
    group: node.group || "main",
    shape: ["hierarchy", "process", "comparison", "system"].includes(plan.type) ? "box" : "circle",
    x: positions.get(node.id)?.x || 250,
    y: positions.get(node.id)?.y || 190,
  }));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = (plan.connections || [])
    .filter((connection) => nodeIds.has(connection.source) && nodeIds.has(connection.target))
    .map((connection) => [connection.source, connection.target, connection.label]);

  const facts = (detail.chunks || [])
    .flatMap((chunk) => chunk.chunk_text.split(/(?<=[.!?])\s+/))
    .map((line) => line.trim())
    .filter((line) => line.length > 40)
    .slice(0, 4);

  return { nodes, links, facts, type: plan.type, title: plan.title, mainIdea: plan.main_idea };
}

const DEMO_PIPELINE_STAGES = [
  {
    title: "Extract concepts",
    label: "Input",
    copy: "A learning subtopic is reduced into the key ideas, relationships and must-keep facts.",
  },
  {
    title: "Plan visualization",
    label: "OpenAI",
    copy: "The system decides what belongs in a concept map, what becomes callouts, and which facts need verification.",
  },
  {
    title: "Generate HTML / SVG / JS",
    label: "Coder-7B",
    copy: "A front-end model drafts the interactive lesson shell and the visual diagram for the selected subtopic.",
  },
  {
    title: "Run in sandbox",
    label: "Safety",
    copy: "The generated code executes in a restricted environment before anything is shown to the learner.",
  },
  {
    title: "Render screenshot",
    label: "Preview",
    copy: "The app captures a render so the output can be inspected before it becomes the live lesson.",
  },
  {
    title: "Verify against facts",
    label: "Check",
    copy: "Claims in the visual are compared against extracted document facts to catch drift or hallucinations.",
  },
  {
    title: "Deliver lesson",
    label: "Output",
    copy: "The learner gets an interactive explanation, a visual map, and a quick understanding check.",
  },
];

const DEMO_CONCEPTS = [
  {
    id: "retrieval",
    title: "Concept extraction",
    short: "Find the ideas that matter",
    color: "blue",
    x: 70,
    y: 86,
    detail: "The source material is summarized into concepts like topic, definition, examples and factual constraints.",
  },
  {
    id: "plan",
    title: "Visual planning",
    short: "Decide the teaching shape",
    color: "amber",
    x: 230,
    y: 56,
    detail: "The planner chooses what becomes a central node, what belongs on branches, and what the learner should interact with first.",
  },
  {
    id: "code",
    title: "UI generation",
    short: "Create HTML/SVG/JS",
    color: "coral",
    x: 392,
    y: 108,
    detail: "A coding model drafts the lesson interface, diagram structure, labels and small interactions for the selected subtopic.",
  },
  {
    id: "verify",
    title: "Fact verification",
    short: "Compare visual to source",
    color: "green",
    x: 280,
    y: 212,
    detail: "Rendered text and labels are checked against extracted facts so the learner sees a trustworthy map.",
  },
];

const DEMO_FACTS = [
  "The visualization is generated after concept extraction and planning.",
  "Generated lesson code runs inside a restricted sandbox before release.",
  "A render preview is checked against document facts before the learner sees it.",
];

const DEMO_QUIZ = {
  question: "Why is the verification step important in this pipeline?",
  options: [
    "It compares the rendered lesson with extracted facts before showing it.",
    "It makes the sandbox less restricted so code can run faster.",
    "It replaces concept extraction with a manual design review.",
  ],
  answer: "It compares the rendered lesson with extracted facts before showing it.",
};

function DemoExperience() {
  const [activeConceptId, setActiveConceptId] = useState(DEMO_CONCEPTS[1].id);
  const [selectedAnswer, setSelectedAnswer] = useState("");
  const activeConcept = DEMO_CONCEPTS.find((item) => item.id === activeConceptId) || DEMO_CONCEPTS[0];
  const answeredCorrectly = selectedAnswer === DEMO_QUIZ.answer;

  return (
    <div className="demo-panel">
      <div className="demo-intro">
        <p className="eyebrow">Test mode</p>
        <h2>See the AI lesson pipeline in one screen.</h2>
        <p>
          This is a mock lesson for understanding the flow: extract a subtopic, plan a visual, generate UI code, render safely, verify it, then show the learner something interactive.
        </p>
      </div>

      <div className="demo-pipeline">
        {DEMO_PIPELINE_STAGES.map((stage, index) => (
          <div className="demo-stage" key={stage.title}>
            <div className="demo-stage-top">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <b>{stage.label}</b>
            </div>
            <strong>{stage.title}</strong>
            <p>{stage.copy}</p>
          </div>
        ))}
      </div>

      <div className="demo-grid">
        <section className="demo-visual-card">
          <div className="demo-card-head">
            <div>
              <span className="kicker">Generated visual</span>
              <h3>Pipeline concept map</h3>
            </div>
            <span className="demo-badge">SVG preview</span>
          </div>
          <svg className="demo-map" viewBox="0 0 470 270" role="img" aria-label="Concept map of the AI lesson pipeline">
            <defs>
              <linearGradient id="demoGlow" x1="0%" x2="100%">
                <stop offset="0%" stopColor="#f7f3e8" />
                <stop offset="100%" stopColor="#fffdf7" />
              </linearGradient>
            </defs>
            <rect x="14" y="14" width="442" height="242" rx="24" fill="url(#demoGlow)" stroke="#ddd9ce" />
            <path d="M110 88C152 62 181 56 228 58" fill="none" stroke="#d8c8ab" strokeWidth="2.5" />
            <path d="M258 72C312 79 340 94 389 108" fill="none" stroke="#e4c2b8" strokeWidth="2.5" />
            <path d="M394 118C373 163 349 188 301 210" fill="none" stroke="#cadccf" strokeWidth="2.5" />
            <path d="M266 211C192 229 138 188 94 102" fill="none" stroke="#cfd8df" strokeWidth="2.5" />
            {DEMO_CONCEPTS.map((concept) => (
              <g key={concept.id} transform={`translate(${concept.x}, ${concept.y})`}>
                <circle
                  r="38"
                  className={`demo-node-ring ${concept.id === activeConceptId ? "active" : ""}`}
                  onClick={() => setActiveConceptId(concept.id)}
                />
                <circle
                  r="28"
                  className={`demo-node-fill ${concept.color} ${concept.id === activeConceptId ? "active" : ""}`}
                  onClick={() => setActiveConceptId(concept.id)}
                />
                <text textAnchor="middle" y="-3" className="demo-node-title">{concept.title}</text>
                <text textAnchor="middle" y="15" className="demo-node-copy">{concept.short}</text>
              </g>
            ))}
          </svg>
          <div className="demo-concept-tabs">
            {DEMO_CONCEPTS.map((concept) => (
              <button
                key={concept.id}
                className={activeConceptId === concept.id ? "active" : ""}
                onClick={() => setActiveConceptId(concept.id)}
              >
                {concept.title}
              </button>
            ))}
          </div>
        </section>

        <section className="demo-detail-card">
          <div className="demo-card-head">
            <div>
              <span className="kicker">Interactive lesson</span>
              <h3>{activeConcept.title}</h3>
            </div>
            <span className={`demo-badge tone-${activeConcept.color}`}>focus</span>
          </div>
          <p>{activeConcept.detail}</p>
          <div className="demo-checklist">
            <div className="demo-checklist-head">
              <span className="signal green" />
              Verification checklist
            </div>
            {DEMO_FACTS.map((fact) => (
              <div className="demo-fact" key={fact}>
                <Icon name="check" size={14} />
                <span>{fact}</span>
              </div>
            ))}
          </div>
          <div className="demo-sandbox-note">
            <Icon name="layers" size={16} />
            <span>Generated output is treated as untrusted until sandbox render and fact-check steps finish.</span>
          </div>
        </section>
      </div>

      <section className="demo-quiz-card">
        <div className="demo-card-head">
          <div>
            <span className="kicker">Quick understanding check</span>
            <h3>Mini quiz</h3>
          </div>
          <span className="demo-badge">1 question</span>
        </div>
        <p className="demo-quiz-question">{DEMO_QUIZ.question}</p>
        <div className="demo-quiz-options">
          {DEMO_QUIZ.options.map((option) => (
            <button
              key={option}
              className={`demo-option ${selectedAnswer === option ? "selected" : ""} ${selectedAnswer && option === DEMO_QUIZ.answer ? "correct" : ""} ${selectedAnswer === option && option !== DEMO_QUIZ.answer ? "incorrect" : ""}`}
              onClick={() => setSelectedAnswer(option)}
            >
              {option}
            </button>
          ))}
        </div>
        {selectedAnswer && (
          <div className={`demo-feedback ${answeredCorrectly ? "success" : "warning"}`}>
            <Icon name={answeredCorrectly ? "check" : "sparkle"} size={15} />
            <span>{answeredCorrectly ? "Correct: verification protects the learner from inaccurate generated visuals." : "Close: the key idea is that verification compares the rendered lesson to extracted facts before release."}</span>
          </div>
        )}
      </section>
    </div>
  );
}

let googleIdentityLoader;

const PASSWORD_RULES = [
  { id: "length", label: "8–72 characters", test: (value) => value.length >= 8 && value.length <= 72 },
  { id: "lowercase", label: "One lowercase letter", test: (value) => /[a-z]/.test(value) },
  { id: "uppercase", label: "One capital letter", test: (value) => /[A-Z]/.test(value) },
  { id: "number", label: "One number", test: (value) => /\d/.test(value) },
  { id: "special", label: "One special character", test: (value) => /[^A-Za-z0-9\s]/.test(value) },
];

function loadGoogleIdentity() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google);
  if (googleIdentityLoader) return googleIdentityLoader;

  googleIdentityLoader = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-study-google-identity="true"]');
    const script = existing || document.createElement("script");
    const handleLoad = () => window.google?.accounts?.id
      ? resolve(window.google)
      : reject(new Error("Google Sign-In did not initialize"));
    script.addEventListener("load", handleLoad, { once: true });
    script.addEventListener("error", () => reject(new Error("Google Sign-In could not be loaded")), { once: true });
    if (!existing) {
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.dataset.studyGoogleIdentity = "true";
      document.head.appendChild(script);
    }
  });
  return googleIdentityLoader;
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("demo");
  const [accountType, setAccountType] = useState("student");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [googleReady, setGoogleReady] = useState(false);
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationMessage, setVerificationMessage] = useState("");
  const [verifyingLink, setVerifyingLink] = useState(false);
  const [error, setError] = useState("");
  const googleButtonRef = useRef(null);
  const googleHandlerRef = useRef(null);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const passwordChecks = PASSWORD_RULES.map((rule) => ({
    ...rule,
    passed: rule.test(form.password),
  }));
  const passwordMeetsPolicy = passwordChecks.every((rule) => rule.passed);

  function selectMode(nextMode) {
    setMode(nextMode);
    setError("");
    setVerificationEmail("");
    setVerificationMessage("");
  }

  function finishAuthentication(result) {
    onAuthenticated({ token: result.access_token, user: result.user });
  }

  googleHandlerRef.current = async (credential) => {
    setBusy(true);
    setError("");
    try {
      const result = await api.googleAuth({
        credential,
        account_type: accountType,
        create_account: mode === "register",
      });
      finishAuthentication(result);
    } catch (err) {
      setError(err.message || "Unable to continue with Google");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("verify_email");
    if (!token) return;

    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("verify_email");
    window.history.replaceState(
      null,
      "",
      `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`
    );
    setMode("login");
    setVerifyingLink(true);
    setError("");
    api.verifyEmail(token)
      .then((result) => {
        finishAuthentication(result);
      })
      .catch((err) => setError(err.message || "This verification link could not be used"))
      .finally(() => setVerifyingLink(false));
  }, []);

  useEffect(() => {
    if (!googleClientId) return undefined;
    let cancelled = false;
    loadGoogleIdentity()
      .then((google) => {
        if (cancelled) return;
        google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => googleHandlerRef.current?.(response.credential),
          ux_mode: "popup",
          auto_select: false,
        });
        setGoogleReady(true);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => { cancelled = true; };
  }, [googleClientId]);

  useEffect(() => {
    if (!googleReady || mode === "demo" || !googleButtonRef.current) return;
    googleButtonRef.current.replaceChildren();
    window.google.accounts.id.renderButton(googleButtonRef.current, {
      type: "standard",
      theme: document.documentElement.dataset.theme === "dark" ? "filled_black" : "outline",
      size: "large",
      shape: "rectangular",
      text: mode === "register" ? "signup_with" : "signin_with",
      logo_alignment: "left",
      width: Math.min(400, Math.max(240, googleButtonRef.current.clientWidth || 400)),
    });
  }, [accountType, googleReady, mode]);

  async function submit(event) {
    event.preventDefault();
    if (mode === "register" && !passwordMeetsPolicy) {
      setError("Use every password requirement shown below.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (mode === "register") {
        const result = await api.register({ ...form, account_type: accountType });
        setVerificationEmail(form.email);
        setVerificationMessage(result.message);
        return;
      }
      const result = await api.login({ email: form.email, password: form.password });
      finishAuthentication(result);
    } catch (err) {
      if (mode === "login" && err instanceof ApiError && err.status === 401) {
        setVerificationEmail(form.email);
        setVerificationMessage(
          "Sign-in failed. If this is an unverified email account, you can request another verification link."
        );
        setError(err.message);
      } else {
        setError(err.message || "Unable to sign in");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resendVerification() {
    setBusy(true);
    setError("");
    try {
      const result = await api.resendVerification(verificationEmail);
      setVerificationMessage(result.message);
    } catch (err) {
      setError(err.message || "Unable to resend the verification email");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-art">
        <div className="auth-orbit orbit-one" />
        <div className="auth-orbit orbit-two" />
        <div className="auth-copy">
          <div className="brand-mark large"><span>◒</span> study / os</div>
          <p className="eyebrow">A calmer way to learn</p>
          <h1>Make the whole subject feel <em>navigable.</em></h1>
          <p className="auth-intro">Your PDFs become living maps of concepts, source-backed notes, and clear paths through complex material.</p>
          <div className="auth-stamp"><span>01</span><span>tree your thinking</span></div>
        </div>
      </section>
      <section className="auth-card-wrap">
        <div className="auth-card">
          <div className="auth-tabs">
            <button className={mode === "demo" ? "active" : ""} onClick={() => selectMode("demo")}>Preview demo</button>
            <button className={mode === "login" ? "active" : ""} onClick={() => selectMode("login")}>Sign in</button>
            <button className={mode === "register" ? "active" : ""} onClick={() => selectMode("register")}>Create account</button>
          </div>
          {mode === "demo" ? (
            <DemoExperience />
          ) : verifyingLink ? (
            <div className="auth-verification" aria-live="polite">
              <span className="spinner" />
              <p className="eyebrow">Verifying email</p>
              <h2>Opening your workspace…</h2>
              <p>We are checking the secure link.</p>
              {error && <div className="form-error">{error}</div>}
            </div>
          ) : (
            <>
              <div className="auth-heading">
                <p className="eyebrow">{mode === "login" ? "Welcome back" : accountType === "professional" ? "Professional workspace" : "Student workspace"}</p>
                <h2>{mode === "login" ? "Pick up where you left off." : accountType === "professional" ? "Turn your reference PDFs into a working map." : "Start your study space."}</h2>
                <p>{mode === "login" ? "Your account type and workspace will open automatically." : accountType === "professional" ? "Organize PDFs in folders, then learn, map, annotate, and ask questions." : "Build a focused home for every subject."}</p>
              </div>
              {verificationEmail ? (
                <div className="auth-verification" aria-live="polite">
                  <div className="auth-verification-icon"><Icon name="check" size={24} /></div>
                  <p className="eyebrow">Check your inbox</p>
                  <h2>Verify your email.</h2>
                  <p>{verificationMessage}</p>
                  {error && <div className="form-error">{error}</div>}
                  <button className="primary-button full" type="button" disabled={busy} onClick={resendVerification}>
                    {busy ? "Sending…" : "Resend verification email"}
                    <Icon name="arrow" size={17} />
                  </button>
                  <button className="auth-text-button" type="button" onClick={() => { setVerificationEmail(""); setVerificationMessage(""); }}>
                    Back to sign in
                  </button>
                </div>
              ) : (
                <>
                  {mode === "register" && <div className="auth-account-types" role="group" aria-label="Choose account type">
                    <button type="button" className={accountType === "student" ? "active" : ""} onClick={() => setAccountType("student")}>
                      <span><Icon name="book" size={17} />Student</span>
                      <small>Semesters, subjects, assignments, practice, and revision.</small>
                    </button>
                    <button type="button" className={accountType === "professional" ? "active" : ""} onClick={() => setAccountType("professional")}>
                      <span><Icon name="layers" size={17} />Professional</span>
                      <small>Folders, PDFs, global maps, learning, notes, and AI tutor.</small>
                    </button>
                  </div>}
                  {googleClientId && (
                    <>
                      <div className="google-signin-wrap" aria-busy={busy}>
                        <div ref={googleButtonRef} className="google-signin-button" />
                      </div>
                      <div className="auth-divider"><span>or use email</span></div>
                    </>
                  )}
                  <form onSubmit={submit} className="stack-form">
                    {mode === "register" && <label>Full name<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Your name" autoComplete="name" /></label>}
                    <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" autoComplete="email" /></label>
                    <label>
                      Password
                      <input
                        required
                        minLength={mode === "register" ? 8 : 1}
                        maxLength="72"
                        type="password"
                        value={form.password}
                        onChange={(e) => setForm({ ...form, password: e.target.value })}
                        placeholder={mode === "register" ? "Create a strong password" : "Your password"}
                        autoComplete={mode === "register" ? "new-password" : "current-password"}
                      />
                    </label>
                    {mode === "register" && (
                      <div className="password-policy" aria-label="Password requirements">
                        {passwordChecks.map((rule) => (
                          <span key={rule.id} className={rule.passed ? "passed" : ""}>
                            <Icon name={rule.passed ? "check" : "close"} size={12} />
                            {rule.label}
                          </span>
                        ))}
                      </div>
                    )}
                    {error && <div className="form-error">{error}</div>}
                    <button className="primary-button full" disabled={busy || (mode === "register" && !passwordMeetsPolicy)}>{busy ? "Opening your space..." : mode === "login" ? "Enter study OS" : accountType === "professional" ? "Create professional space" : "Create study space"}<Icon name="arrow" size={17} /></button>
                  </form>
                </>
              )}
              <p className="auth-footnote">Email accounts must be verified. Google credentials are verified securely by the backend.</p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

function EmptyWorkspace({ token, semesters, onCreated, professionalMode = false }) {
  const [semesterName, setSemesterName] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function createWorkspace(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let semester = semesters[0];
      if (!semester) semester = await api.createSemester({ name: professionalMode ? "Professional library" : semesterName || "My semester", description: "" }, token);
      await api.createSubject({ name: subjectName || (professionalMode ? "New folder" : "New subject"), description: "", semester_id: semester.id }, token);
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="empty-workspace">
      <div className="empty-symbol"><Icon name="layers" size={34} /></div>
      <p className="eyebrow">{professionalMode ? "Your PDF library" : "First page"}</p>
      <h2>{professionalMode ? "Create your first folder." : "Give your learning a home."}</h2>
      <p>{professionalMode ? "Add a folder, upload reference PDFs, and we’ll build a navigable global map from them." : "Create a semester and subject, then upload the first chapter PDF. We’ll build the tree as you go."}</p>
      <form onSubmit={createWorkspace} className="empty-form">
        {!professionalMode && !semesters.length && <input value={semesterName} onChange={(e) => setSemesterName(e.target.value)} placeholder="Semester name" />}
        <input value={subjectName} onChange={(e) => setSubjectName(e.target.value)} placeholder={professionalMode ? "Folder name" : "Subject name"} />
        {error && <div className="form-error">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? "Creating..." : professionalMode ? "Create folder" : "Create study space"}<Icon name="arrow" size={17} /></button>
      </form>
    </div>
  );
}

function TreeNode({ node, selectedId, onSelect, progressMap, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children?.length > 0;
  const complete = progressMap[node.id]?.status === "completed";
  return (
    <div className="tree-item">
      <div className={`tree-row ${selectedId === node.id ? "selected" : ""}`} style={{ "--depth": depth }}>
        {hasChildren ? <button className={`tree-toggle ${open ? "open" : ""}`} onClick={() => setOpen(!open)}><Icon name="chevron" size={14} /></button> : <span className="tree-dot" />}
        <a className="tree-label" href={studyNodeHref(node)} onClick={(event) => { event.preventDefault(); updateStudyHash(node); onSelect(node.id); }}>
          <span className={`node-index level-${node.level}`}>{node.heading_number || (node.node_type === "chapter" ? "C" : "•")}</span>
          <span className="tree-title">{node.title}</span>
          {complete && <span className="tree-complete"><Icon name="check" size={13} /></span>}
        </a>
      </div>
      {hasChildren && open && <div className="tree-children">{node.children.map((child) => <TreeNode key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} progressMap={progressMap} depth={depth + 1} />)}</div>}
    </div>
  );
}

function Sidebar({ user, professionalMode = false, semesters, selectedSemester, subjects, selectedSubjectId, documents, lectures, lectureView, selectedLectureId, onSemester, onSubject, onAddSemester, onAddSubject, onDeleteSubject, onDocument, onDeleteDocument, tree, selectedNodeId, onNode, progressMap, onUpload, onLectures, onLecture, onStartLecture, onBilling, onLogout }) {
  const panel = useResizablePanel({
    storageKey: "study_left_panel",
    defaultWidth: 286,
    minWidth: 230,
    maxWidth: 460,
    direction: 1,
  });
  return (
    <aside className={`sidebar resizable-panel ${professionalMode ? "professional-sidebar" : ""} ${panel.open ? "" : "panel-collapsed"} ${panel.resizing ? "panel-resizing" : ""}`} style={{ "--panel-width": `${panel.width}px` }}>
      <button type="button" className="panel-edge-toggle left-panel-toggle" aria-expanded={panel.open} onClick={panel.toggle} title={panel.open ? "Close navigation panel" : "Open navigation panel"}><span aria-hidden="true">{panel.open ? "‹" : "›"}</span></button>
      <span className="panel-resize-handle left-panel-resize" role="separator" aria-label="Resize navigation panel" aria-orientation="vertical" tabIndex={panel.open ? 0 : -1} {...panel.resizeHandleProps} />
      <div className="sidebar-top">
        <div className="brand-mark"><span>◒</span> study / os</div>
        <button className="icon-button mobile-close"><Icon name="close" /></button>
      </div>
      {!professionalMode && <div className="semester-picker">
        <span className="mini-label">Workspace</span>
        <div className="semester-picker-row"><select value={selectedSemester?.id || ""} onChange={(e) => onSemester(Number(e.target.value))}>
          {semesters.map((semester) => <option value={semester.id} key={semester.id}>{semester.name}</option>)}
        </select><button className="tiny-action" onClick={onAddSemester} title="Add semester"><Icon name="plus" size={15} /></button></div>
        <Icon name="chevron" size={14} />
      </div>}
      <div className="sidebar-section">
        <div className="section-heading"><span>{professionalMode ? "Folders" : "Your subjects"}</span><button className="tiny-action" onClick={onAddSubject} title={professionalMode ? "Add folder" : "Add subject"}><Icon name="plus" size={15} /></button></div>
        <div className="subject-list">
          {subjects.map((subject) => <div key={subject.id} className={`subject-item-row ${selectedSubjectId === subject.id ? "active" : ""}`}><button className="subject-item" onClick={() => onSubject(subject.id)}><span className="subject-color" />{subject.name}<span className="subject-arrow">›</span></button><button className="subject-delete" onClick={() => onDeleteSubject(subject)} title={`Delete ${subject.name}`}><Icon name="trash" size={13} /></button></div>)}
          {!subjects.length && <p className="muted small">Create your first {professionalMode ? "folder" : "subject"} to begin.</p>}
        </div>
      </div>
      {!professionalMode && <div className={`sidebar-section lecture-section ${lectureView ? "active-section" : ""}`}>
        <div className="section-heading"><button className="section-link" onClick={onLectures}>Lectures</button><span className="tree-count">{lectures.length}</span><button className="tiny-action" onClick={onStartLecture} title="Start a lecture"><Icon name="plus" size={15} /></button></div>
        {lectures.length ? <div className="lecture-list">{lectures.map((lecture) => <button key={lecture.id} className={`lecture-row ${selectedLectureId === lecture.id ? "selected" : ""}`} onClick={() => onLecture(lecture.id)}><span className="lecture-number">{String(lecture.lecture_number).padStart(2, "0")}</span><span><strong>{lecture.title}</strong><small>{lecture.status === "ready" ? "Notes ready" : "Transcript in progress"}</small></span><span className={`lecture-status ${lecture.status}`} /></button>)}</div> : <button className="lecture-empty" onClick={onStartLecture}><Icon name="microphone" size={14} />Start your first lecture</button>}
      </div>}
      {documents.length > 0 && <div className="sidebar-section document-section"><div className="section-heading"><span>{professionalMode ? "PDFs" : "Study material"}</span><span className="tree-count">{documents.length} PDFs</span></div><div className="document-list">{documents.map((document) => <div className="document-row" key={document.id}><button className="document-open" onClick={() => onDocument(document)} title={`Open ${document.filename}`}><span className="document-icon"><Icon name="file" size={13} /></span><span className="document-copy"><strong>{document.filename}</strong><small>{document.description}</small></span></button><button className="document-delete" onClick={() => onDeleteDocument(document)} title={`Delete ${document.filename}`}><Icon name="trash" size={13} /></button></div>)}</div></div>}
      {tree.length > 0 && <div className="sidebar-section tree-section"><div className="section-heading"><button className="section-link map-home-link" onClick={() => { updateStudyHash(null); onNode(null); }}>{professionalMode ? "Global map" : "Study map"}</button><span className="tree-count">{flattenNodes(tree).filter((node) => node.node_type === "subtopic").length} nodes</span></div><div className="tree-list">{tree.map((node) => <TreeNode key={node.id} node={node} selectedId={selectedNodeId} onSelect={onNode} progressMap={progressMap} />)}</div></div>}
      <div className="sidebar-bottom">
        <button className="upload-side-button" onClick={onUpload}><Icon name="upload" size={16} /><span>{professionalMode ? "Upload PDF" : "Upload material"}</span><kbd>U</kbd></button>
        <button className="billing-button" onClick={onBilling}><Icon name="sparkle" size={15} /><span>{user?.subscription_plan === "free" ? "Upgrade plan" : "Manage subscription"}</span><small>{(user?.subscription_plan || "free").replace("_", " ")}</small></button>
        <div className="profile-row"><div className="avatar">{initials(user?.full_name || user?.email)}</div><div className="profile-copy"><strong>{user?.full_name || (professionalMode ? "Professional" : "Student")}</strong><span>{professionalMode ? "Professional account" : user?.email || "Your account"}</span></div><button className="icon-button" onClick={onLogout} title="Log out"><Icon name="logout" size={16} /></button></div>
      </div>
    </aside>
  );
}

function BillingModal({ user, token, onClose, onPlanChange }) {
  const [subscription, setSubscription] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const targetPlan = user?.account_type === "professional" ? "professional" : "student_pro";

  async function loadSubscription() {
    try {
      const current = await api.subscription(token);
      setSubscription(current);
      await onPlanChange?.();
    } catch (err) {
      setError(err.message || "Subscription status could not be loaded.");
    }
  }

  useEffect(() => { loadSubscription(); }, []);
  useEffect(() => {
    if (subscription?.status !== "pending") return undefined;
    const timer = window.setInterval(loadSubscription, 2500);
    return () => window.clearInterval(timer);
  }, [subscription?.status]);

  async function checkout() {
    setBusy(true);
    setError("");
    try {
      const { url } = await api.createCheckout(targetPlan, token);
      window.location.assign(url);
    } catch (err) {
      setError(err.message || "Checkout could not be opened.");
      setBusy(false);
    }
  }

  async function manage() {
    setBusy(true);
    setError("");
    try {
      const { url } = await api.createBillingPortal(token);
      window.location.assign(url);
    } catch (err) {
      setError(err.message || "The billing portal could not be opened.");
      setBusy(false);
    }
  }

  const active = ["active", "trialing"].includes(subscription?.status);
  const planLabel = targetPlan === "professional" ? "Professional" : "Student Pro";
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}><div className="modal-card billing-modal"><button className="modal-close" disabled={busy} onClick={onClose}><Icon name="close" size={18} /></button><div className="modal-icon"><Icon name="sparkle" size={23} /></div><p className="eyebrow">Stripe subscription</p><h2>{active ? `${planLabel} is active.` : `Upgrade to ${planLabel}.`}</h2><p className="modal-copy">{active ? "Your paid limits are active and renew through Stripe. Use the secure billing portal to update payment details or cancel." : "Checkout and card handling happen on Stripe. Your paid limits activate only after a signed Stripe webhook confirms the subscription."}</p>{subscription && <div className="billing-status"><span>Current plan</span><strong>{(subscription.plan || "free").replace("_", " ")}</strong><span>Status</span><strong>{subscription.status}</strong>{subscription.current_period_end && <><span>Current period ends</span><strong>{formatDate(subscription.current_period_end, { year: "numeric", month: "short", day: "numeric" })}</strong></>}</div>}{error && <div className="form-error">{error}</div>}<button className="primary-button full" disabled={busy || !subscription} onClick={subscription?.can_manage ? manage : checkout}>{busy ? "Opening Stripe..." : subscription?.can_manage ? "Manage billing" : `Choose ${planLabel}`}<Icon name="arrow" size={17} /></button><small className="billing-note">Access follows Stripe’s webhook-confirmed subscription status; a redirect alone never unlocks features.</small></div></div>;
}

function SearchMapModal({ tree, selectedId, progressMap = {}, onClose, onNode, professionalMode = false }) {
  const [query, setQuery] = useState("");
  const inputRef = useRef(null);
  const nodes = useMemo(() => flattenNodes(tree), [tree]);
  const normalizedQuery = query.trim().toLowerCase();
  const results = useMemo(() => {
    const terms = normalizedQuery.split(/\s+/).filter(Boolean);
    const scored = nodes.map((node) => {
      const title = (node.title || "").toLowerCase();
      const heading = (node.heading_number || "").toLowerCase();
      const type = (node.node_type || "").toLowerCase();
      const haystack = `${heading} ${title} ${type}`;
      if (!terms.length) return { node, score: node.id === selectedId ? 4 : node.node_type === "subtopic" ? 2 : 1 };
      if (!terms.every((term) => haystack.includes(term))) return null;
      let score = 1;
      if (title === normalizedQuery) score += 10;
      if (title.startsWith(normalizedQuery)) score += 6;
      if (heading === normalizedQuery) score += 5;
      if (node.node_type === "subtopic") score += 2;
      if (node.id === selectedId) score += 3;
      return { node, score };
    }).filter(Boolean);
    return scored.sort((a, b) => b.score - a.score || a.node.level - b.node.level).slice(0, 12).map((item) => item.node);
  }, [nodes, normalizedQuery, selectedId]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function openNode(node) {
    updateStudyHash(node);
    onNode(node.id);
    onClose();
  }

  function handleKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "Enter" && results[0]) {
      event.preventDefault();
      openNode(results[0]);
    }
  }

  return (
    <div className="search-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="search-modal" role="dialog" aria-modal="true" aria-label={professionalMode ? "Search global map" : "Search study map"}>
        <div className="search-modal-input">
          <Icon name="search" size={18} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={professionalMode ? "Search global map..." : "Search study map..."}
          />
          <button onClick={onClose} title="Close search"><Icon name="close" size={16} /></button>
        </div>
        <div className="search-results">
          {results.map((node) => {
            const completed = progressMap[node.id]?.status === "completed";
            return (
              <button key={node.id} className={`search-result ${selectedId === node.id ? "selected" : ""}`} onClick={() => openNode(node)}>
                <span className={`search-result-type ${node.node_type}`}>{node.heading_number || (node.node_type === "chapter" ? "C" : node.node_type === "topic" ? "T" : "S")}</span>
                <span className="search-result-copy">
                  <strong>{node.title}</strong>
                  <small>{node.node_type.replace("_", " ")}{node.children?.length ? ` / ${node.children.length} inside` : ""}</small>
                </span>
                {completed && <Icon name="check" size={14} />}
              </button>
            );
          })}
          {!results.length && <div className="search-empty"><Icon name="search" size={20} /><span>No matching map nodes.</span></div>}
        </div>
      </section>
    </div>
  );
}

function RevisionItem({ revision, subjectId, onNode, onRevision, onSubmitPractice }) {
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const questions = revision.practice_questions || [];

  async function submit(event) {
    event.preventDefault();
    if (!revision.practice_set_id) return;
    setBusy(true);
    try {
      const token = localStorage.getItem("study_token");
      const submitter = onSubmitPractice || (
        (practiceId, practiceAnswers) => api.submitPractice(subjectId, practiceId, practiceAnswers, token)
      );
      setResult(await submitter(revision.practice_set_id, answers));
    } finally {
      setBusy(false);
    }
  }

  return <article className={`revision-card ${open ? "open" : ""}`}>
    <button className="queue-item" onClick={() => setOpen(!open)}>
      <span className="queue-icon"><Icon name="clock" size={15} /></span>
      <span><strong>{revision.node_title}</strong><small>{revision.status === "overdue" ? formatOverdue(revision.days_overdue) : `review after ${revision.interval_days}d`}</small></span>
      <span className="queue-check" title="Mark revision complete" onClick={(event) => { event.stopPropagation(); onRevision(revision); }}><Icon name="check" size={14} /></span>
    </button>
    {open && <div className="revision-detail">
      {revision.revision_note && <p className="revision-note">{revision.revision_note}</p>}
      {revision.revision_points?.length > 0 && <ul className="revision-points">{revision.revision_points.map((point, index) => <li key={`${revision.id}-point-${index}`}>{point}</li>)}</ul>}
      {questions.length > 0 ? <form className="revision-quiz" onSubmit={submit}>
        <span className="kicker">Quick check</span>
        {questions.map((question, index) => <fieldset key={question.id}>
          <legend><span>{String(index + 1).padStart(2, "0")}</span>{question.question}</legend>
          <div className="revision-options">{question.options.map((option) => <label key={option} className={answers[question.id] === option ? "selected" : ""}><input required={!result} type="radio" name={`revision-${revision.id}-${question.id}`} value={option} checked={answers[question.id] === option} disabled={Boolean(result)} onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })} /><span>{option}</span></label>)}</div>
        </fieldset>)}
        {result && <div className="revision-result">{Math.round(result.percentage)}% · {result.score}/{result.max_score} correct</div>}
        {!result && <button className="secondary-button" disabled={busy}>{busy ? "Checking..." : "Check quiz"}</button>}
      </form> : <p className="revision-empty">No quick quiz is available for this node yet.</p>}
      <button className="revision-open" onClick={() => onNode(revision.node_id)}>Open full revision page <Icon name="arrow" size={14} /></button>
    </div>}
  </article>;
}

function TodayPanel({ subjectId, plan, progressRows, tree, onNode, onRevision, onTest, onSubmitPractice }) {
  const panel = useResizablePanel({
    storageKey: "study_today_panel",
    defaultWidth: 306,
    minWidth: 260,
    maxWidth: 520,
    direction: -1,
  });
  const leaves = flattenNodes(tree).filter((node) => node.node_type === "subtopic");
  const completed = progressRows.filter((row) => row.status === "completed").length;
  const percent = leaves.length ? Math.round((completed / leaves.length) * 100) : 0;
  return (
    <aside className={`today-panel resizable-panel ${panel.open ? "" : "panel-collapsed"} ${panel.resizing ? "panel-resizing" : ""}`} style={{ "--panel-width": `${panel.width}px` }}>
      <button type="button" className="panel-edge-toggle right-panel-toggle" aria-expanded={panel.open} onClick={panel.toggle} title={panel.open ? "Close Today panel" : "Open Today panel"}><span aria-hidden="true">{panel.open ? "›" : "‹"}</span></button>
      <span className="panel-resize-handle right-panel-resize" role="separator" aria-label="Resize Today panel" aria-orientation="vertical" tabIndex={panel.open ? 0 : -1} {...panel.resizeHandleProps} />
      <div className="today-heading"><div><p className="eyebrow">Your rhythm</p><h3>Today</h3></div><span className="date-stamp">{formatDate(new Date(), { weekday: "short", month: "short", day: "numeric" })}</span></div>
      <div className="progress-card"><div className="progress-card-top"><span>Subject progress</span><strong>{percent}%</strong></div><div className="progress-track"><span style={{ width: `${percent}%` }} /></div><p>{completed} of {leaves.length || "your"} subtopics completed</p></div>
      <div className="today-block"><div className="block-title"><span className="signal amber" />Revision queue <span>{plan?.revisions?.length || 0}</span></div>{plan?.revisions?.length ? plan.revisions.map((revision) => <RevisionItem key={revision.id} revision={revision} subjectId={subjectId} onNode={onNode} onRevision={onRevision} onSubmitPractice={onSubmitPractice} />) : <div className="empty-queue"><span>Nothing due today.</span><small>Finish a node and we’ll schedule the next revisit.</small></div>}</div>
      <div className="today-block"><div className="block-title"><span className="signal blue" />Assignments <span>{plan?.practice_sets?.length || 0}</span></div>{plan?.practice_sets?.length ? plan.practice_sets.map((practice) => <button className="test-queue" key={practice.id} onClick={() => onNode(practice.node_id)}><span className="test-number">{practice.questions.length}</span><span><strong>{practice.title}</strong><small>{practice.source_assignment_id ? "From uploaded assignment" : "Generated practice"}</small></span><Icon name="arrow" size={15} /></button>) : <div className="empty-queue"><span>No assignments generated yet.</span><small>Upload an assignment or complete a subtopic.</small></div>}</div>
      <div className="today-block"><div className="block-title"><span className="signal coral" />Topic tests <span>{plan?.topic_tests?.length || 0}</span></div>{plan?.topic_tests?.length ? plan.topic_tests.map((test) => <button className="test-queue" key={test.id} onClick={() => onTest(test)}><span className="test-number">{test.questions.length}</span><span><strong>{test.node_title}</strong><small>{test.status === "overdue" ? formatOverdue(test.days_overdue) : `due ${formatDate(test.due_at)}`}</small></span><Icon name="arrow" size={15} /></button>) : <div className="empty-queue"><span>No active tests yet.</span><small>Complete every subtopic in a topic to unlock one.</small></div>}</div>
      <div className="today-quote"><span>“</span><p>Small, repeated returns beat one heroic cram session.</p><small>study / os principle 04</small></div>
    </aside>
  );
}

function Breadcrumb({ detail, onNode, professionalMode = false }) {
  if (!detail) return null;
  return <nav className="breadcrumb" aria-label={`${professionalMode ? "Global" : "Study"} map breadcrumb`}><a href="#study-map" onClick={(event) => { event.preventDefault(); updateStudyHash(null); onNode(null); }}>{professionalMode ? "Global map" : "Study map"}</a><b> / </b>{detail.breadcrumb.map((item, index) => <span key={item.id}>{index === detail.breadcrumb.length - 1 ? <span className="current">{item.title}</span> : <a href={studyNodeHref(item)} onClick={(event) => { event.preventDefault(); updateStudyHash(item); onNode(item.id); }}>{item.title}</a>}{index < detail.breadcrumb.length - 1 && <b> / </b>}</span>)}</nav>;
}

function buildRadialMindMap(tree = [], rootTitle = "Study map") {
  const rawNodes = [{ id: "study-map-root", title: rootTitle, node_type: "root", depth: 0, angle: 0 }];
  const edges = [];
  const countLeaves = (node) => (node.children?.length ? node.children.reduce((sum, child) => sum + countLeaves(child), 0) : 1);
  const addBranch = (node, parentId, startAngle, endAngle, depth) => {
    const angle = (startAngle + endAngle) / 2;
    rawNodes.push({ ...node, depth, angle });
    edges.push({ source: parentId, target: node.id });
    const children = node.children || [];
    if (!children.length) return;
    const totalLeaves = children.reduce((sum, child) => sum + countLeaves(child), 0);
    let cursor = startAngle;
    children.forEach((child) => {
      const span = (endAngle - startAngle) * (countLeaves(child) / totalLeaves);
      addBranch(child, node.id, cursor, cursor + span, depth + 1);
      cursor += span;
    });
  };

  const totalLeaves = tree.reduce((sum, node) => sum + countLeaves(node), 0);
  const fullCircle = Math.PI * 2;
  const singleBranchSpan = Math.min(
    fullCircle - 0.7,
    Math.max(2.8, totalLeaves * 0.2),
  );
  const mapSpan = tree.length === 1 ? singleBranchSpan : fullCircle;

  if (tree.length) {
    // A single PDF still receives almost a complete orbit when it has lots of
    // content. Keeping the small opening at the bottom leaves a clean visual
    // route from the map root through the PDF and subtopic nodes.
    const start = tree.length === 1
      ? -Math.PI / 2 - mapSpan / 2
      : -Math.PI / 2;
    let cursor = start;
    tree.forEach((node) => {
      const branchSpan = mapSpan * (countLeaves(node) / totalLeaves);
      addBranch(node, "study-map-root", cursor, cursor + branchSpan, 1);
      cursor += branchSpan;
    });
  }

  const maxDepth = Math.max(...rawNodes.map((node) => node.depth), 1);
  const leafSpacing = 122;
  const minimumOuterRadius = totalLeaves > 1
    ? (totalLeaves * leafSpacing) / mapSpan
    : 210;
  const outerRadius = Math.max(maxDepth * 190, minimumOuterRadius);
  const innerLayerGap = Math.min(
    260,
    Math.max(180, outerRadius / (maxDepth + 0.6)),
  );
  const center = Math.max(460, outerRadius + 145);
  const nodes = rawNodes.map((node) => {
    const radius = node.depth === maxDepth || node.node_type === "subtopic"
      ? outerRadius
      : node.depth * innerLayerGap;
    return { ...node, x: center + Math.cos(node.angle) * radius, y: center + Math.sin(node.angle) * radius };
  });
  return { nodes, edges, size: center * 2 };
}

function globalMapTree(tree, expandedSubtopicId) {
  const mapNode = (node, mapDepth = 0) => {
    const originalChildren = node.children || [];
    const hasMapChildren = originalChildren.length > 0;
    const showChildren = mapDepth === 0 || node.id === expandedSubtopicId;
    return {
      ...node,
      mapDepth,
      hasMapChildren,
      children: showChildren
        ? originalChildren.map((child) => mapNode(child, mapDepth + 1))
        : [],
    };
  };
  return tree.map((node) => mapNode(node));
}

function RadialMindMapNode({ node, onNode, onSubtopicToggle, onMoveStart, selectedId, progressMap, dragging, expanded }) {
  const isRoot = node.node_type === "root";
  const isPdfTopic = !isRoot && node.mapDepth === 0;
  const isExpandableSubtopic = !isRoot && node.mapDepth >= 1 && node.hasMapChildren;
  const isContentTopic = !isRoot && !node.hasMapChildren;
  const completed = progressMap[node.id]?.status === "completed";
  const visualClass = isRoot
    ? "mindmap-radial-root"
    : isPdfTopic
      ? "mindmap-radial-chapter"
      : isExpandableSubtopic
        ? "mindmap-radial-topic"
        : "mindmap-radial-leaf";
  const className = `mindmap-radial-node ${visualClass} ${selectedId === node.id ? "selected" : ""} ${completed ? "completed" : ""} ${dragging ? "dragging" : ""} ${expanded ? "expanded" : ""}`;
  const mapLabel = isRoot
    ? "MAP"
    : isPdfTopic
      ? "TOPIC / PDF"
      : isExpandableSubtopic
        ? "SUBTOPIC"
        : "CONTENT TOPIC";
  const content = <><span className="mindmap-radial-label">{mapLabel}</span><strong title={node.title}>{node.title}</strong>{isPdfTopic && <small>Subtopics shown</small>}{isExpandableSubtopic && <small>{expanded ? "Hide content topics" : "Show content topics"}</small>}{isContentTopic && <small>{completed ? "Completed" : "Open Learn page"}</small>}</>;
  if (isRoot) return <a href="#study-map" draggable={false} className={className} style={{ left: node.x, top: node.y }} onPointerDown={(event) => onMoveStart(event, node)} onClick={(event) => { event.preventDefault(); updateStudyHash(null); onNode(null); }}>{content}</a>;
  if (isPdfTopic) return <div className={className} style={{ left: node.x, top: node.y }} onPointerDown={(event) => onMoveStart(event, node)}>{content}</div>;
  if (isExpandableSubtopic) return <a href={studyNodeHref(node)} draggable={false} className={className} style={{ left: node.x, top: node.y }} aria-expanded={expanded} onPointerDown={(event) => onMoveStart(event, node)} onClick={(event) => { event.preventDefault(); onSubtopicToggle(node.id); }}>{content}</a>;
  return <a href={studyNodeHref(node)} draggable={false} className={className} style={{ left: node.x, top: node.y }} onPointerDown={(event) => onMoveStart(event, node)} onClick={(event) => { event.preventDefault(); updateStudyHash(node); onNode(node.id); }}>{content}</a>;
}

function FullStudyMindMap({ tree, onNode, rootTitle, selectedId, progressMap = {}, startFullscreen = false, onFullscreenStarted, professionalMode = false }) {
  const minZoom = 0.35;
  const maxZoom = 1.6;
  const zoomStep = 0.1;
  const [expandedSubtopicId, setExpandedSubtopicId] = useState(null);
  const visibleTree = useMemo(() => globalMapTree(tree, expandedSubtopicId), [tree, expandedSubtopicId]);
  const layout = useMemo(() => buildRadialMindMap(visibleTree, rootTitle), [visibleTree, rootTitle]);
  const panelRef = useRef(null);
  const scrollRef = useRef(null);
  const panRef = useRef(null);
  const nodeDragRef = useRef(null);
  const draggedRef = useRef(false);
  const zoomAnchorRef = useRef(null);
  const positionsRef = useRef(loadMindMapPositions());
  const [handActive, setHandActive] = useState(true);
  const [arrangeActive, setArrangeActive] = useState(false);
  const [panning, setPanning] = useState(false);
  const [draggingNodeId, setDraggingNodeId] = useState(null);
  const [nodePositions, setNodePositions] = useState(positionsRef.current);
  const [zoom, setZoom] = useState(0.85);
  const [browserFullscreen, setBrowserFullscreen] = useState(false);
  const [fallbackFullscreen, setFallbackFullscreen] = useState(() => {
    const storedRequest = consumeMindMapFullscreenRequest();
    return Boolean(startFullscreen) || storedRequest;
  });
  const isFullscreen = browserFullscreen || fallbackFullscreen;
  const positionedNodes = useMemo(() => layout.nodes.map((node) => {
    const saved = nodePositions[node.id];
    if (!saved) return node;
    return {
      ...node,
      x: Math.min(layout.size - 55, Math.max(55, saved.x)),
      y: Math.min(layout.size - 55, Math.max(55, saved.y)),
    };
  }), [layout, nodePositions]);

  function centerMap() {
    const scroller = scrollRef.current;
    if (!scroller) return;
    scroller.scrollLeft = Math.max(0, (scroller.scrollWidth - scroller.clientWidth) / 2);
    scroller.scrollTop = Math.max(0, (scroller.scrollHeight - scroller.clientHeight) / 2);
  }

  function changeZoom(rawZoom, clientX = null, clientY = null) {
    const nextZoom = Math.min(maxZoom, Math.max(minZoom, Math.round(rawZoom * 20) / 20));
    if (nextZoom === zoom) return;
    const scroller = scrollRef.current;
    if (scroller) {
      const rect = scroller.getBoundingClientRect();
      const viewportX = clientX === null ? scroller.clientWidth / 2 : clientX - rect.left;
      const viewportY = clientY === null ? scroller.clientHeight / 2 : clientY - rect.top;
      const oldPaddingX = Math.max(0, (scroller.clientWidth - layout.size * zoom) / 2);
      const oldPaddingY = Math.max(0, (scroller.clientHeight - layout.size * zoom) / 2);
      zoomAnchorRef.current = {
        contentX: (scroller.scrollLeft + viewportX - oldPaddingX) / zoom,
        contentY: (scroller.scrollTop + viewportY - oldPaddingY) / zoom,
        viewportX,
        viewportY,
      };
    }
    setZoom(nextZoom);
  }

  useEffect(() => {
    const frame = window.requestAnimationFrame(centerMap);
    return () => window.cancelAnimationFrame(frame);
  }, [layout.size, isFullscreen, expandedSubtopicId]);

  useEffect(() => {
    const anchor = zoomAnchorRef.current;
    if (!anchor) return undefined;
    const frame = window.requestAnimationFrame(() => {
      const scroller = scrollRef.current;
      if (!scroller) return;
      const newPaddingX = Math.max(0, (scroller.clientWidth - layout.size * zoom) / 2);
      const newPaddingY = Math.max(0, (scroller.clientHeight - layout.size * zoom) / 2);
      scroller.scrollLeft = anchor.contentX * zoom + newPaddingX - anchor.viewportX;
      scroller.scrollTop = anchor.contentY * zoom + newPaddingY - anchor.viewportY;
      zoomAnchorRef.current = null;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [zoom, layout.size]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return undefined;
    const handleWheel = (event) => {
      event.preventDefault();
      const direction = event.deltaY < 0 ? 1 : -1;
      changeZoom(zoom + direction * zoomStep, event.clientX, event.clientY);
    };
    scroller.addEventListener("wheel", handleWheel, { passive: false });
    return () => scroller.removeEventListener("wheel", handleWheel);
  }, [zoom, layout.size]);

  useEffect(() => {
    const syncFullscreen = () => setBrowserFullscreen(document.fullscreenElement === panelRef.current);
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  useEffect(() => {
    if (!startFullscreen) return;
    setFallbackFullscreen(true);
    onFullscreenStarted?.();
  }, [startFullscreen, onFullscreenStarted]);

  useEffect(() => {
    if (!fallbackFullscreen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const exitOnEscape = (event) => {
      if (event.key === "Escape") setFallbackFullscreen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", exitOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", exitOnEscape);
    };
  }, [fallbackFullscreen]);

  async function toggleFullscreen() {
    if (fallbackFullscreen) {
      setFallbackFullscreen(false);
      return;
    }
    if (document.fullscreenElement === panelRef.current) {
      await document.exitFullscreen();
      return;
    }
    try {
      if (panelRef.current?.requestFullscreen) {
        await panelRef.current.requestFullscreen();
      } else {
        setFallbackFullscreen(true);
      }
    } catch {
      setFallbackFullscreen(true);
    }
  }

  function startNodeMove(event, node) {
    if (!arrangeActive || event.button !== 0) return;
    event.stopPropagation();
    draggedRef.current = false;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    nodeDragRef.current = {
      pointerId: event.pointerId,
      nodeId: node.id,
      captureElement: event.currentTarget,
      startX: event.clientX,
      startY: event.clientY,
      nodeX: node.x,
      nodeY: node.y,
      moved: false,
    };
  }

  function startPan(event) {
    if (!handActive || event.button !== 0) return;
    const scroller = scrollRef.current;
    if (!scroller) return;
    draggedRef.current = false;
    panRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: scroller.scrollLeft,
      scrollTop: scroller.scrollTop,
      moved: false,
    };
  }

  function movePan(event) {
    const pan = panRef.current;
    const scroller = scrollRef.current;
    if (!handActive || !pan || !scroller || pan.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - pan.startX;
    const deltaY = event.clientY - pan.startY;
    if (!pan.moved && Math.hypot(deltaX, deltaY) < 5) return;
    if (!pan.moved) {
      scroller.setPointerCapture?.(event.pointerId);
      setPanning(true);
    }
    pan.moved = true;
    draggedRef.current = true;
    event.preventDefault();
    scroller.scrollLeft = pan.scrollLeft - deltaX;
    scroller.scrollTop = pan.scrollTop - deltaY;
  }

  function moveNode(event) {
    const drag = nodeDragRef.current;
    const scroller = scrollRef.current;
    if (!arrangeActive || !drag || !scroller || drag.pointerId !== event.pointerId) return false;
    const screenDeltaX = event.clientX - drag.startX;
    const screenDeltaY = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(screenDeltaX, screenDeltaY) < 5) return true;
    const deltaX = screenDeltaX / zoom;
    const deltaY = screenDeltaY / zoom;
    if (!drag.moved) {
      setDraggingNodeId(drag.nodeId);
    }
    drag.moved = true;
    draggedRef.current = true;
    event.preventDefault();
    const margin = drag.nodeId === "study-map-root" ? 100 : 58;
    const nextPositions = {
      ...positionsRef.current,
      [drag.nodeId]: {
        x: Math.min(layout.size - margin, Math.max(margin, drag.nodeX + deltaX)),
        y: Math.min(layout.size - margin, Math.max(margin, drag.nodeY + deltaY)),
      },
    };
    positionsRef.current = nextPositions;
    setNodePositions(nextPositions);
    return true;
  }

  function stopPan(event) {
    const pan = panRef.current;
    const scroller = scrollRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;
    if (scroller?.hasPointerCapture?.(event.pointerId)) scroller.releasePointerCapture(event.pointerId);
    panRef.current = null;
    setPanning(false);
    if (pan.moved) window.setTimeout(() => { draggedRef.current = false; }, 0);
  }

  function movePointer(event) {
    if (moveNode(event)) return;
    movePan(event);
  }

  function stopPointer(event) {
    const drag = nodeDragRef.current;
    if (drag?.pointerId === event.pointerId) {
      if (drag.captureElement?.hasPointerCapture?.(event.pointerId)) drag.captureElement.releasePointerCapture(event.pointerId);
      nodeDragRef.current = null;
      setDraggingNodeId(null);
      if (drag.moved) {
        saveMindMapPositions(positionsRef.current);
        window.setTimeout(() => { draggedRef.current = false; }, 0);
      }
      return;
    }
    stopPan(event);
  }

  function blockDraggedNodeClick(event) {
    if (!draggedRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    draggedRef.current = false;
  }

  function toggleHandTool() {
    panRef.current = null;
    nodeDragRef.current = null;
    setPanning(false);
    setDraggingNodeId(null);
    const next = !handActive;
    setHandActive(next);
    if (next) setArrangeActive(false);
  }

  function toggleArrangeTool() {
    panRef.current = null;
    nodeDragRef.current = null;
    setPanning(false);
    setDraggingNodeId(null);
    const next = !arrangeActive;
    setArrangeActive(next);
    if (next) setHandActive(false);
  }

  function toggleSubtopicContent(subtopicId) {
    setExpandedSubtopicId((current) => current === subtopicId ? null : subtopicId);
  }

  function resetNodePositions() {
    const subjectNodeIds = new Set([
      "study-map-root",
      ...flattenNodes(tree).map((node) => String(node.id)),
    ]);
    const nextPositions = Object.fromEntries(
      Object.entries(positionsRef.current).filter(([nodeId]) => !subjectNodeIds.has(nodeId)),
    );
    positionsRef.current = nextPositions;
    setNodePositions(nextPositions);
    saveMindMapPositions(nextPositions);
  }

  if (!tree.length) return null;
  const byId = new Map(positionedNodes.map((node) => [node.id, node]));
  const allNodes = flattenNodes(tree);
  const topicCount = allNodes.filter((node) => node.node_type === "topic").length;
  const subtopicCount = allNodes.filter((node) => node.node_type === "subtopic").length;
  const hasCustomPositions = Boolean(
    nodePositions["study-map-root"] || allNodes.some((node) => nodePositions[node.id]),
  );
  return (
    <section ref={panelRef} className={`mindmap-panel ${fallbackFullscreen ? "fullscreen-fallback" : ""}`}>
      <div className="mindmap-header">
        <div>
          <span className="kicker">{professionalMode ? "Global PDF map" : "Full study map"}</span>
          <h3>{professionalMode ? "See the whole folder at once" : "See the whole subject at once"}</h3>
        </div>
        <div className="mindmap-header-side">
          <div className="mindmap-summary">
            <span><b>{topicCount}</b> topics</span>
            <span><b>{subtopicCount}</b> content pages</span>
          </div>
          <div className="mindmap-tools" aria-label="Mind map tools">
            <div className="mindmap-zoom-control" aria-label="Zoom controls">
              <button type="button" onClick={() => changeZoom(zoom - zoomStep)} disabled={zoom <= minZoom} aria-label="Zoom out">−</button>
              <input type="range" min={minZoom} max={maxZoom} step="0.05" value={zoom} onChange={(event) => changeZoom(Number(event.target.value))} aria-label="Mind map zoom" />
              <button type="button" onClick={() => changeZoom(zoom + zoomStep)} disabled={zoom >= maxZoom} aria-label="Zoom in">+</button>
              <output>{Math.round(zoom * 100)}%</output>
            </div>
            <button type="button" className={`mindmap-tool-button ${handActive ? "active" : ""}`} aria-pressed={handActive} onClick={toggleHandTool} title="Toggle hand tool">
              <Icon name="hand" size={15} />
              <span>Hand tool</span>
            </button>
            <button type="button" className={`mindmap-tool-button ${arrangeActive ? "active" : ""}`} aria-pressed={arrangeActive} onClick={toggleArrangeTool} title="Drag individual nodes">
              <Icon name="move" size={15} />
              <span>Arrange nodes</span>
            </button>
            <button type="button" className="mindmap-tool-button reset-layout-button" onClick={resetNodePositions} disabled={!hasCustomPositions} title="Restore automatic node positions">
              <Icon name="layers" size={15} />
              <span>Reset layout</span>
            </button>
            <button type="button" className="mindmap-tool-button" aria-pressed={isFullscreen} onClick={toggleFullscreen} title={isFullscreen ? "Exit full screen" : "Open full screen"}>
              <Icon name="fullscreen" size={15} />
              <span>{isFullscreen ? "Exit full screen" : "Full screen"}</span>
            </button>
          </div>
        </div>
      </div>
      <div className="mindmap-legend" aria-label="Mind map legend">
        <span><i className="legend-dot chapter" />Topic / PDF</span>
        <span><i className="legend-dot topic" />Subtopic · click to expand</span>
        <span><i className="legend-dot subtopic" />Content topic · opens Learn</span>
      </div>
      <div
        className={`mindmap-radial-scroll ${handActive ? "hand-tool" : ""} ${panning ? "panning" : ""} ${arrangeActive ? "arrange-tool" : ""} ${draggingNodeId !== null ? "dragging-node" : ""}`}
        ref={scrollRef}
        onPointerDown={startPan}
        onPointerMove={movePointer}
        onPointerUp={stopPointer}
        onPointerCancel={stopPointer}
        onClickCapture={blockDraggedNodeClick}
        onDragStart={(event) => { if (handActive || arrangeActive) event.preventDefault(); }}
      >
        <div className="mindmap-zoom-stage" style={{ width: layout.size * zoom, height: layout.size * zoom }}>
          <div className="mindmap-radial-canvas" style={{ width: layout.size, height: layout.size, transform: `translate(-50%, -50%) scale(${zoom})` }}>
            <svg className="mindmap-radial-lines" width={layout.size} height={layout.size} viewBox={`0 0 ${layout.size} ${layout.size}`} aria-hidden="true">
              {layout.edges.map((edge) => {
                const source = byId.get(edge.source);
                const target = byId.get(edge.target);
                return <line key={`${edge.source}-${edge.target}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} className={`mindmap-line mindmap-line-${target.node_type}`} />;
              })}
            </svg>
            {positionedNodes.map((node) => <RadialMindMapNode key={node.id} node={node} onNode={onNode} onSubtopicToggle={toggleSubtopicContent} onMoveStart={startNodeMove} selectedId={selectedId} progressMap={progressMap} dragging={draggingNodeId === node.id} expanded={expandedSubtopicId === node.id} />)}
          </div>
        </div>
      </div>
      <p className="mindmap-hint">{arrangeActive ? "Arrange mode · drag any circle to place it · PDF topics and subtopics stay visible" : expandedSubtopicId ? "Subtopic expanded · click a content topic to open its Learn page" : handActive ? "Global map · click a subtopic to reveal its content topics · drag to move the canvas" : "Global map · click a subtopic to reveal its content topics"}</p>
    </section>
  );
}

function Overview({ detail, tree, onNode, rootTitle, selectedId, progressMap, startFullscreen, onFullscreenStarted, professionalMode = false }) {
  const children = detail ? findNode(tree, detail.id)?.children || [] : tree;
  return <section className="overview-panel"><div className="overview-intro"><span className="kicker">{detail?.node_type === "chapter" ? "Chapter map" : professionalMode ? "Global PDF map" : "Topic map"}</span><h2>{detail?.title || (professionalMode ? "Your global map" : "Your study map")}</h2><p>{detail?.node_type === "chapter" ? `Move through the branches below. Each leaf opens into notes, visualization, and a source-grounded AI tutor${professionalMode ? "." : ", plus practice."}` : "Choose any node in the complete structure. Every subtopic opens its own learning page."}</p></div><FullStudyMindMap tree={tree} onNode={onNode} rootTitle={rootTitle || detail?.breadcrumb?.[0]?.title || (professionalMode ? "Global map" : "Study map")} selectedId={selectedId} progressMap={progressMap} startFullscreen={startFullscreen} onFullscreenStarted={onFullscreenStarted} professionalMode={professionalMode} /><div className="child-grid">{children.map((child) => <a href={studyNodeHref(child)} key={child.id} className="child-card" onClick={(event) => { event.preventDefault(); updateStudyHash(child); onNode(child.id); }}><span className="child-card-index">{child.heading_number || "→"}</span><span><strong>{child.title}</strong><small>{child.node_type === "subtopic" ? "Open learning page" : `${child.children?.length || 0} subtopics`}</small></span><Icon name="arrow" size={16} /></a>)}</div>{!children.length && <div className="no-content"><Icon name="file" size={22} /><span>Upload a PDF to draw the first branches.</span></div>}</section>;
}

function LearningPage({ detail, content, tab, setTab, notes, noteDocument, noteText, setNoteText, onSaveNote, onUpdateNote, onDeleteNote, onSaveNoteDocument, onComposeNotes, practice, onSubmitPractice, chatMessages, chatText, setChatText, onChat, chatBusy, professionalMode = false }) {
  if (!detail) return <div className="loading-state"><span className="spinner" />Loading your {professionalMode ? "global" : "study"} map...</div>;
  if (detail.node_type !== "subtopic") return <Overview detail={detail} tree={[]} onNode={() => {}} professionalMode={professionalMode} />;
  return (
    <section className="learning-page">
      <div className="learning-source-bar">
        <span><Icon name="file" size={14} />Original source</span>
        <div>
          {detail.source_pages?.length ? detail.source_pages.map((source) => (
            <a href={pdfSourceHref(source)} key={`${source.document_id}-${source.page_number}`} title={`Open ${source.filename} on page ${source.page_number}`}>
              <strong>{source.filename}</strong>
              <small>Page {source.page_number}</small>
              <Icon name="external" size={13} />
            </a>
          )) : <small>Source page unavailable</small>}
        </div>
      </div>
      <div className="learning-tabs"><button className={tab === "learn" ? "active" : ""} onClick={() => setTab("learn")}><Icon name="sparkle" size={15} />Learn</button><button className={tab === "visualize" ? "active" : ""} onClick={() => setTab("visualize")}><Icon name="layers" size={15} />Visualize</button>{!professionalMode && <button className={tab === "practice" ? "active" : ""} onClick={() => setTab("practice")}><Icon name="check" size={15} />Practice</button>}<button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}><Icon name="chat" size={15} />Ask tutor</button><button className={tab === "notes" ? "active" : ""} onClick={() => setTab("notes")}><Icon name="note" size={15} />My notes</button></div>
      {tab === "learn" && <LearnTab content={content} />}
      {tab === "visualize" && <VisualizationTab detail={detail} content={content} />}
      {!professionalMode && tab === "practice" && <PracticeTab practice={practice} onSubmit={onSubmitPractice} />}
      {tab === "chat" && <ChatTab messages={chatMessages} text={chatText} setText={setChatText} onSend={onChat} busy={chatBusy} />}
      <div className="notes-tab-state" hidden={tab !== "notes"}>
        <NotesTab notes={notes} noteDocument={noteDocument} text={noteText} setText={setNoteText} onSave={onSaveNote} onUpdate={onUpdateNote} onDelete={onDeleteNote} onSaveDocument={onSaveNoteDocument} onCompose={onComposeNotes} />
      </div>
    </section>
  );
}

function StructuredNotes({ sections, keyPoints }) {
  const visibleSections = sections?.length ? sections : [{ heading: "Key points", summary: "The most important ideas from this subtopic.", points: keyPoints || [] }];
  return <article className="lesson-card structured-notes-card">
    <div className="card-label"><span className="signal blue" />Structured notes</div>
    <div className="structured-note-sections">{visibleSections.map((section, index) => <section key={`${section.heading}-${index}`}>
      <h4>{section.heading}</h4>
      {section.summary && <p className="structured-note-summary">{section.summary}</p>}
      {section.points?.length > 0 && <ul>{section.points.map((point, pointIndex) => <li key={`${index}-${pointIndex}`}>{point}</li>)}</ul>}
    </section>)}</div>
  </article>;
}

function LearnTab({ content }) {
  if (!content) return <div className="no-content"><Icon name="sparkle" size={22} /><span>Learning content is still being prepared for this subtopic.</span></div>;
  return <div className="learn-grid"><article className="lesson-card hero-lesson"><div className="card-label"><span className="signal blue" />The idea</div><h3>{content.explanation}</h3><div className="lesson-footer"><span><Icon name="sparkle" size={14} />AI-generated from your material</span><span>v{content.version}</span></div></article><StructuredNotes sections={content.structured_sections} keyPoints={content.key_points} /><article className="lesson-card analogy-card"><div className="card-label"><span className="signal amber" />Make it stick</div><h3>Analogy</h3><p>{content.analogy}</p></article><article className="lesson-card example-card"><div className="card-label"><span className="signal coral" />Try the shape</div><h3>Worked example</h3><p>{content.worked_example}</p></article><article className="lesson-card real-life-card"><div className="card-label"><span className="signal green" />See it around you</div><h3>Real-life example</h3><p>{content.real_life_example || "Regenerate this learning page to add a real-life application."}</p></article>{content.formulas?.length > 0 && <article className="lesson-card formula-card"><div className="card-label"><span className="signal green" />Formula desk</div>{content.formulas.map((formula, index) => <div className="formula-row" key={`${formula.expression}-${index}`}><code>{formula.expression}</code><p>{formula.symbols || formula.use_case}</p></div>)}</article>}<article className="lesson-card key-card"><div className="card-label"><span className="signal ink" />Remember</div><ul>{content.key_points?.map((point, index) => <li key={index}>{point}</li>)}</ul></article><article className="lesson-card question-card"><div className="card-label"><span className="signal coral" />Check yourself</div>{content.conceptual_questions?.map((question, index) => <p key={index}><span>0{index + 1}</span>{question}</p>)}</article></div>;
}

function VisualizationTab({ detail, content }) {
  const model = useMemo(() => buildVisualizationModel(detail, content), [detail, content]);
  const [activeNodeId, setActiveNodeId] = useState("core");

  if (!content || !model) return <div className="no-content"><Icon name="layers" size={22} /><span>Visualization will appear after learning content is generated for this subtopic.</span></div>;

  const activeNode = model.nodes.find((node) => node.id === activeNodeId) || model.nodes[0];

  return (
    <div className="visualization-layout">
      <article className="visual-panel visual-canvas-card">
        <div className="visual-head">
          <div>
            <span className="kicker">Generated map</span>
            <h3>{detail.title}</h3>
          </div>
          <span className="visual-chip">Verified view</span>
        </div>
        <svg className="visual-map" viewBox="0 0 500 390" role="img" aria-label={`Concept visualization for ${detail.title}`}>
          <rect x="14" y="14" width="472" height="362" rx="30" fill="#fffdf7" stroke="#e2ddd2" />
          {model.links.map(([from, to]) => {
            const source = model.nodes.find((node) => node.id === from);
            const target = model.nodes.find((node) => node.id === to);
            if (!source || !target) return null;
            return <line key={`${from}-${to}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} className="visual-link" />;
          })}
          {model.nodes.map((node) => (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`} onClick={() => setActiveNodeId(node.id)} className="visual-node-group">
              {node.shape === "box" ? <>
                <rect x="-58" y="-31" width="116" height="62" rx="14" className={`visual-node-shell ${activeNodeId === node.id ? "active" : ""}`} />
                <rect x="-48" y="-22" width="96" height="44" rx="10" className={`visual-node-fill ${node.kind} ${activeNodeId === node.id ? "active" : ""}`} />
              </> : <>
                <circle r="44" className={`visual-node-shell ${activeNodeId === node.id ? "active" : ""}`} />
                <circle r="33" className={`visual-node-fill ${node.kind} ${activeNodeId === node.id ? "active" : ""}`} />
              </>}
              <title>{`${node.title}: ${node.summary}`}</title>
              <text
                textAnchor="middle"
                y={svgTitleLines(node.title).length > 1 ? -5 : 3}
                className="visual-node-title"
              >
                {svgTitleLines(node.title).map((line, index) => (
                  <tspan key={`${node.id}-${index}`} x="0" dy={index === 0 ? 0 : 13}>{line}</tspan>
                ))}
              </text>
            </g>
          ))}
        </svg>
        <div className="visual-node-list">
          {model.nodes.map((node) => (
            <button key={node.id} className={activeNodeId === node.id ? "active" : ""} onClick={() => setActiveNodeId(node.id)}>
              <strong>{node.title}</strong>
              <span>{node.summary}</span>
            </button>
          ))}
        </div>
      </article>

      <article className="visual-panel visual-detail-card">
        <div className="visual-head">
          <div>
            <span className="kicker">Focused branch</span>
            <h3>{activeNode.title}</h3>
          </div>
          <span className="visual-chip subtle">interactive</span>
        </div>
        <p className="visual-detail-copy">{activeNode.summary}</p>

        <div className="visual-verification">
          <div className="visual-verify-head">
            <span className="signal green" />
            Source-backed facts
          </div>
          {model.facts.length ? model.facts.map((fact, index) => (
            <div className="visual-fact" key={`${fact}-${index}`}>
              <span className="visual-fact-index">{String(index + 1).padStart(2, "0")}</span>
              <p>{fact}</p>
            </div>
          )) : <div className="empty-queue"><span>No chunk highlights yet.</span><small>Upload richer source text to make verification snippets more specific.</small></div>}
        </div>

        <div className="visual-status-grid">
          <div className="visual-status-card">
            <span className="kicker">Render</span>
            <strong>Sandbox-ready</strong>
            <p>The visualization is generated from structured lesson content before display.</p>
          </div>
          <div className="visual-status-card">
            <span className="kicker">Coverage</span>
            <strong>{model.nodes.length} visual nodes</strong>
            <p>Core idea, examples, memory anchors, self-checks, and formulas are mapped automatically.</p>
          </div>
        </div>
      </article>
    </div>
  );
}

function PracticeTab({ practice, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = practice?.[0];

  useEffect(() => {
    setAnswers({});
    setResult(null);
    setError("");
  }, [set?.id]);

  if (!set?.questions?.length) return <div className="no-content"><Icon name="layers" size={22} /><span>Practice will appear here after this subtopic is processed.</span></div>;

  const feedback = Object.fromEntries((result?.analytics?.question_feedback || []).map((item) => [item.question_id, item]));

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await onSubmit(set.id, answers));
    } catch (submitError) {
      setError(submitError.message || "Practice could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="practice-wrap"><div className="practice-heading"><div><span className="kicker">Practice set</span><h3>{set.title}</h3><p className="practice-instruction">Choose one answer for each question, then submit to see your score.</p></div><span className="question-count">{set.questions.length} questions</span></div>{result && <div className={`practice-result ${result.percentage >= 70 ? "success" : "needs-review"}`}><strong>{Math.round(result.percentage)}%</strong><span>{result.score} of {result.max_score} correct</span>{result.analytics?.weak_concepts?.length > 0 && <small>Review: {result.analytics.weak_concepts.join(", ")}</small>}</div>}<form className="practice-form" onSubmit={submit}>{set.questions.map((question, index) => { const item = feedback[question.id]; return <fieldset className={`practice-question ${item ? (item.correct ? "answered-correct" : "answered-wrong") : ""}`} key={question.id}><legend><span className="question-number">{String(index + 1).padStart(2, "0")}</span><strong>{question.question}</strong></legend><div className="option-list">{question.options.map((option) => <label className={answers[question.id] === option ? "selected" : ""} key={option}><input required={!result} type="radio" name={`practice-${set.id}-${question.id}`} value={option} checked={answers[question.id] === option} disabled={Boolean(result)} onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })} /><span>{option}</span></label>)}</div>{item && <div className={`practice-feedback ${item.correct ? "correct" : "incorrect"}`}><strong>{item.correct ? "Correct" : `Correct answer: ${item.correct_answer}`}</strong><span>{item.explanation}</span>{item.source_pages?.length > 0 && <div className="practice-sources"><small>Where to read</small>{item.source_pages.map((source) => <span key={`${source.filename}-${source.page_number}`}>{source.filename}, page {source.page_number}</span>)}</div>}</div>}</fieldset>;})}<div className="practice-actions">{error && <span className="practice-error">{error}</span>}{result ? <button type="button" className="secondary-button" onClick={() => { setAnswers({}); setResult(null); }}>Try again</button> : <button className="primary-button" disabled={busy}>{busy ? <span className="spinner small-spin" /> : <Icon name="check" size={16} />}{busy ? "Checking..." : "Submit practice"}</button>}</div></form></div>;
}

function ChatTab({ messages, text, setText, onSend, busy }) {
  return <div className="chat-panel"><div className="chat-intro"><div className="tutor-avatar"><Icon name="sparkle" size={20} /></div><div><span className="kicker">Node tutor</span><h3>Ask this subtopic anything.</h3><p>The tutor is scoped to this leaf, so the answer stays close to your uploaded material.</p></div></div><div className="chat-messages">{!messages.length && <div className="chat-empty"><span>Try asking</span><button onClick={() => setText("Explain this with a simple analogy")}>“Explain this with a simple analogy”</button><button onClick={() => setText("What formula should I remember here?")}>“What formula should I remember here?”</button></div>}{messages.map((message, index) => <div className={`message ${message.role}`} key={index}><span className="message-label">{message.role === "user" ? "You" : "Tutor"}</span><p>{message.content}</p></div>)}</div><form className="chat-input" onSubmit={(e) => { e.preventDefault(); onSend(); }}><input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about this subtopic..." /><button disabled={busy || !text.trim()}>{busy ? <span className="spinner small-spin" /> : <Icon name="arrow" size={17} />}</button></form></div>;
}

const EMPTY_PROMPT_NOTES = {
  overview: "",
  sections: [],
  key_points: [],
  questions: [],
};

function normalizePromptNotes(value) {
  return {
    overview: value?.overview || "",
    sections: (value?.sections || []).map((section) => ({
      heading: section?.heading || "",
      summary: section?.summary || "",
      points: [...(section?.points || [])],
    })),
    key_points: [...(value?.key_points || [])],
    questions: [...(value?.questions || [])],
  };
}

function listFromEditor(value) {
  return value.split("\n");
}

function cleanPromptNotes(value) {
  return {
    overview: value.overview.trim(),
    sections: value.sections.map((section, index) => ({
      heading: section.heading.trim() || `Section ${index + 1}`,
      summary: section.summary.trim(),
      points: section.points.map((item) => item.trim()).filter(Boolean),
    })),
    key_points: value.key_points.map((item) => item.trim()).filter(Boolean),
    questions: value.questions.map((item) => item.trim()).filter(Boolean),
  };
}

function StructuredNoteEditor({ value, onChange, disabled }) {
  function changeSection(index, field, nextValue) {
    const sections = value.sections.map((section, sectionIndex) => (
      sectionIndex === index ? { ...section, [field]: nextValue } : section
    ));
    onChange({ ...value, sections });
  }

  function removeSection(index) {
    onChange({ ...value, sections: value.sections.filter((_, sectionIndex) => sectionIndex !== index) });
  }

  function addSection() {
    onChange({
      ...value,
      sections: [...value.sections, { heading: "New section", summary: "", points: [] }],
    });
  }

  return (
    <div className="structured-note-editor">
      <label className="note-editor-field">
        <span>Overview</span>
        <textarea
          disabled={disabled}
          maxLength={8000}
          value={value.overview}
          onChange={(event) => onChange({ ...value, overview: event.target.value })}
          placeholder="A clear overview of this subtopic..."
        />
      </label>

      <div className="note-section-list">
        {value.sections.map((section, index) => (
          <article className="note-section-editor" key={`note-section-${index}`}>
            <div className="note-section-editor-head">
              <span>Section {String(index + 1).padStart(2, "0")}</span>
              <button type="button" disabled={disabled} onClick={() => removeSection(index)} title="Remove section">
                <Icon name="trash" size={14} />
              </button>
            </div>
            <input
              disabled={disabled}
              maxLength={240}
              aria-label={`Section ${index + 1} heading`}
              value={section.heading}
              onChange={(event) => changeSection(index, "heading", event.target.value)}
              placeholder="Section heading"
            />
            <textarea
              disabled={disabled}
              maxLength={4000}
              aria-label={`Section ${index + 1} summary`}
              value={section.summary}
              onChange={(event) => changeSection(index, "summary", event.target.value)}
              placeholder="Short explanation..."
            />
            <label className="note-editor-field compact">
              <span>Points · one per line</span>
              <textarea
                disabled={disabled}
                value={section.points.join("\n")}
                onChange={(event) => changeSection(index, "points", listFromEditor(event.target.value))}
                placeholder={"First important point\nSecond important point"}
              />
            </label>
          </article>
        ))}
      </div>

      <button className="note-add-section" type="button" disabled={disabled} onClick={addSection}>
        <Icon name="plus" size={14} />Add section
      </button>

      <div className="note-list-editors">
        <label className="note-editor-field">
          <span>Key points · one per line</span>
          <textarea
            disabled={disabled}
            value={value.key_points.join("\n")}
            onChange={(event) => onChange({ ...value, key_points: listFromEditor(event.target.value) })}
            placeholder="What must you remember?"
          />
        </label>
        <label className="note-editor-field">
          <span>Active-recall questions · one per line</span>
          <textarea
            disabled={disabled}
            value={value.questions.join("\n")}
            onChange={(event) => onChange({ ...value, questions: listFromEditor(event.target.value) })}
            placeholder="What should you be able to answer?"
          />
        </label>
      </div>
    </div>
  );
}

function NotesTab({ notes, noteDocument, text, setText, onSave, onUpdate, onDelete, onSaveDocument, onCompose }) {
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [draft, setDraft] = useState(() => normalizePromptNotes(noteDocument?.notes || EMPTY_PROMPT_NOTES));
  const [instruction, setInstruction] = useState("");
  const [composing, setComposing] = useState(false);
  const [savingDocument, setSavingDocument] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [previousDraft, setPreviousDraft] = useState(null);
  const [composerMessage, setComposerMessage] = useState("");
  const [composerHistory, setComposerHistory] = useState([]);
  const [documentError, setDocumentError] = useState("");

  useEffect(() => {
    setDraft(normalizePromptNotes(noteDocument?.notes || EMPTY_PROMPT_NOTES));
    setDirty(false);
    setPreviousDraft(null);
    setComposerMessage("");
    setDocumentError("");
  }, [noteDocument?.node_id, noteDocument?.version]);

  useEffect(() => {
    setComposerHistory([]);
  }, [noteDocument?.node_id]);

  function changeDraft(nextDraft) {
    setDraft(nextDraft);
    setDirty(true);
  }

  async function saveDocument() {
    setSavingDocument(true);
    setDocumentError("");
    try {
      const saved = await onSaveDocument(cleanPromptNotes(draft));
      setDraft(normalizePromptNotes(saved.notes));
      setDirty(false);
      setComposerMessage("Saved to this subtopic.");
    } catch (error) {
      setDocumentError(error.message || "Structured notes could not be saved.");
    } finally {
      setSavingDocument(false);
    }
  }

  async function composeDocument(event) {
    event.preventDefault();
    const prompt = instruction.trim();
    if (!prompt) return;
    setComposing(true);
    setDocumentError("");
    setComposerMessage("");
    try {
      const result = await onCompose(cleanPromptNotes(draft), prompt);
      setPreviousDraft(normalizePromptNotes(draft));
      setDraft(normalizePromptNotes(result.notes));
      setInstruction("");
      setDirty(true);
      setComposerMessage(result.message || "Notes reshaped. Review them, then save.");
      setComposerHistory((items) => [
        ...items,
        { role: "user", content: prompt },
        { role: "assistant", content: result.message || "Notes reshaped. Review them, then save." },
      ]);
    } catch (error) {
      setDocumentError(error.message || "The notes editor could not apply that prompt.");
    } finally {
      setComposing(false);
    }
  }

  function undoCompose() {
    if (!previousDraft) return;
    setDraft(previousDraft);
    setPreviousDraft(null);
    setDirty(true);
    setComposerMessage("Last AI edit undone.");
  }

  function beginEdit(note) {
    setEditingId(note.id);
    setEditingText(note.content);
  }

  async function saveEdit(noteId) {
    if (!editingText.trim()) return;
    setSavingId(noteId);
    try {
      await onUpdate(noteId, editingText.trim());
      setEditingId(null);
      setEditingText("");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="notes-studio">
      <div className="notes-studio-heading">
        <div>
          <span className="kicker">Prompt notes maker</span>
          <h3>Your structured notes</h3>
          <p>Edit directly or tell the AI how to reshape the same source-grounded notes.</p>
        </div>
        <div className="notes-document-actions">
          <span className={`note-save-state ${dirty ? "unsaved" : ""}`}>
            {dirty ? "Unsaved changes" : noteDocument?.saved ? `Saved · v${noteDocument.version}` : "Built from lesson"}
          </span>
          <button className="primary-button" disabled={savingDocument || !dirty} onClick={saveDocument}>
            {savingDocument ? <span className="spinner small-spin" /> : <Icon name="check" size={15} />}
            {savingDocument ? "Saving..." : "Save notes"}
          </button>
        </div>
      </div>

      <div className="notes-studio-grid">
        <section className="structured-note-workspace">
          <div className="notes-pane-label">
            <span><Icon name="note" size={15} />Notes document</span>
            <small>Everything here stays editable</small>
          </div>
          <StructuredNoteEditor value={draft} onChange={changeDraft} disabled={composing} />
        </section>

        <aside className="note-prompt-panel">
          <div className="note-prompt-topbar">
            <span><Icon name="sparkle" size={14} />AI notes editor</span>
            <small>Same model as Ask Tutor</small>
          </div>
          <div className="note-prompt-conversation">
            <div className="note-assistant-message">
              <div className="prompt-model-badge"><Icon name="sparkle" size={14} />Source-grounded</div>
              <p>I can reshape the structured notes on the left. Ask me to shorten them, change their format, simplify an explanation, or create revision questions.</p>
            </div>
            {composerHistory.map((message, index) => (
              <div className={`note-conversation-entry ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "user" ? "You" : "Notes editor"}</span>
                <p>{message.content}</p>
              </div>
            ))}
            {(documentError || (composerMessage && !composerHistory.length)) && (
              <div className={`note-composer-message ${documentError ? "error" : ""}`} aria-live="polite">
                {documentError || composerMessage}
              </div>
            )}
            <div className="note-prompt-examples">
              {[
                "Make this concise",
                "Turn this into exam notes",
                "Simplify the explanations",
                "Add active-recall questions",
              ].map((example) => (
                <button type="button" key={example} onClick={() => setInstruction(example)}>{example}</button>
              ))}
            </div>
          </div>
          <div className="note-prompt-composer">
            <form onSubmit={composeDocument}>
              <textarea
                value={instruction}
                disabled={composing}
                maxLength={4000}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Ask the notes editor..."
              />
              <div className="note-prompt-composer-actions">
                <span><Icon name="plus" size={15} />Prompt</span>
                <button className="prompt-apply-button" disabled={composing || !instruction.trim()} title="Apply prompt to notes">
                  {composing ? <span className="spinner small-spin" /> : <Icon name="arrow" size={16} />}
                </button>
              </div>
            </form>
            <div className="note-composer-footer">
              {previousDraft ? <button className="note-undo-button" type="button" onClick={undoCompose}>Undo last AI edit</button> : <span />}
              <span className="note-grounding-status"><span className="signal green" />This subtopic only</span>
            </div>
          </div>
        </aside>
      </div>

      <section className="notes-panel scratch-notes-panel">
        <div className="notes-heading">
          <div>
            <span className="kicker">Quick private notes</span>
            <h3>Scratchpad</h3>
            <p>Keep a memory hook, question, or personal connection outside the main notes document.</p>
          </div>
          <Icon name="note" size={22} />
        </div>
        <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Write a memory hook, question, or connection..." />
        <div className="notes-actions">
          <span>Only visible to you</span>
          <button className="secondary-button" disabled={!text.trim()} onClick={onSave}>
            <Icon name="check" size={15} />Save quick note
          </button>
        </div>
        <div className="saved-notes">
          {notes.map((note) => (
            <article className="saved-note" key={note.id}>
              {editingId === note.id ? (
                <textarea className="saved-note-editor" value={editingText} onChange={(event) => setEditingText(event.target.value)} />
              ) : (
                <p>{note.content}</p>
              )}
              {editingId === note.id ? (
                <div className="saved-note-actions">
                  <button disabled={savingId === note.id || !editingText.trim()} onClick={() => saveEdit(note.id)}>
                    {savingId === note.id ? "Saving..." : "Save"}
                  </button>
                  <button onClick={() => { setEditingId(null); setEditingText(""); }}>Cancel</button>
                </div>
              ) : (
                <div className="saved-note-actions">
                  <small>{formatDate(note.updated_at, { month: "short", day: "numeric", year: "numeric" })}</small>
                  <button onClick={() => beginEdit(note)}>Edit</button>
                  <button onClick={() => onDelete(note.id)}>Delete</button>
                </div>
              )}
            </article>
          ))}
          {!notes.length && <p className="muted">Your first quick note will appear here.</p>}
        </div>
      </section>
    </div>
  );
}

function UploadModal({ subject, token, onClose, onDone, professionalMode = false }) {
  const [kind, setKind] = useState("study");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("idle");
  const [error, setError] = useState("");
  const [jobProgress, setJobProgress] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => () => { mountedRef.current = false; }, []);

  async function waitForJob(jobId) {
    while (mountedRef.current) {
      const job = await api.uploadJob(jobId, token);
      if (!mountedRef.current) return null;
      setStage(job.stage);
      setJobProgress(job.progress);
      if (job.status === "completed") return job;
      if (job.status === "failed") {
        throw new Error(job.error_message || "The PDF could not be processed.");
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return null;
  }

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setStage("uploading");
    setJobProgress(2);
    setError("");
    try {
      const job = kind === "study"
        ? await api.uploadStudy(subject.id, file, token)
        : await api.uploadAssignment(subject.id, file, token);
      setStage("queued");
      setJobProgress(job.progress || 5);
      const completed = await waitForJob(job.id);
      if (!completed) return;
      setStage("complete");
      setJobProgress(100);
      setTimeout(() => onDone(kind === "study" ? "Study material processed" : "Assignment mapped to the study tree"), 900);
    } catch (err) {
      setStage("idle");
      setJobProgress(0);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  const statusText = {
    uploading: "Uploading PDF...",
    queued: "Queued for processing...",
    starting: "Starting the background job...",
    retrying: "Retrying safely...",
    extracting: "Extracting PDF text...",
    organizing: "Organizing the study map...",
    generating: "Generating learning material...",
    indexing: "Indexing chunks...",
    mapping: "Mapping assignment chunks...",
    complete: "Completed. Closing this window...",
  }[stage];
  const progressStage = jobProgress >= 100 ? 3 : jobProgress >= 30 ? 2 : jobProgress >= 5 ? 1 : 0;

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && stage !== "complete" && onClose()}><div className="modal-card upload-modal"><button className="modal-close" disabled={busy || stage === "complete"} onClick={onClose}><Icon name="close" size={18} /></button><div className={`modal-icon ${stage === "complete" ? "complete" : ""}`}><Icon name={stage === "complete" ? "check" : "upload"} size={24} /></div><p className="eyebrow">{professionalMode ? "Add reference" : "Add material"}</p><h2>{stage === "complete" ? "PDF is ready." : professionalMode ? `Add a PDF to ${subject?.name || "this folder"}.` : "Feed the subject."}</h2><p className="modal-copy">{stage === "complete" ? `Your ${professionalMode ? "folder" : "study space"} has been updated.` : professionalMode ? "The PDF will be indexed, added to the folder, and connected to its global knowledge map." : "Study PDFs grow the map. Assignment PDFs become scoped practice."}</p>{!professionalMode && <div className="upload-switch"><button type="button" disabled={busy || stage === "complete"} className={kind === "study" ? "active" : ""} onClick={() => setKind("study")}><Icon name="book" size={16} />Study PDF</button><button type="button" disabled={busy || stage === "complete"} className={kind === "assignment" ? "active" : ""} onClick={() => setKind("assignment")}><Icon name="file" size={16} />Assignment PDF</button></div>}<form onSubmit={upload}><label className={`dropzone ${file ? "has-file" : ""}`}><input disabled={busy || stage === "complete"} type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0])} />{file ? <><Icon name="check" size={26} /><strong>{file.name}</strong><span>{stage === "idle" ? "Ready to process" : statusText}</span></> : <><Icon name="upload" size={26} /><strong>Drop a PDF here</strong><span>or click to browse</span></>}</label>{(busy || stage === "complete") && <div className={`upload-status ${stage}`}><div className="upload-status-heading"><span className="spinner upload-spinner" />{statusText}</div><div className="upload-steps"><span className={progressStage >= 1 ? "done" : ""}>Upload</span><span className={progressStage >= 2 ? "done" : ""}>Process</span><span className={progressStage >= 3 ? "done" : ""}>Ready</span></div><small>The server is processing this as a background job with durable status.</small></div>}{error && <div className="form-error">{error}</div>}<button className="primary-button full" disabled={!file || busy || stage === "complete"}>{stage === "complete" ? "Completed" : busy ? statusText : "Process PDF"}{stage === "complete" ? <Icon name="check" size={17} /> : <Icon name="arrow" size={17} />}</button></form></div></div>;
}

function WorkspaceModal({ kind, semesters, selectedSemesterId, token, onClose, onCreated }) {
  const isFolder = kind === "folder";
  const isSubject = kind === "subject" || isFolder;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [semesterId, setSemesterId] = useState(String(selectedSemesterId || semesters[0]?.id || ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!name.trim()) return;
    if (isSubject && !semesterId) {
      setError("Create a semester first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = isSubject
        ? await api.createSubject({ name: name.trim(), description: description.trim(), semester_id: Number(semesterId) }, token)
        : await api.createSemester({ name: name.trim(), description: description.trim() }, token);
      onCreated(created, kind);
    } catch (err) {
      setError(err.message || "Could not create this workspace item.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal-card workspace-modal"><button className="modal-close" onClick={onClose}><Icon name="close" size={18} /></button><div className="modal-icon"><Icon name={isSubject ? "book" : "layers"} size={24} /></div><p className="eyebrow">New {isFolder ? "folder" : isSubject ? "subject" : "semester"}</p><h2>{isFolder ? "Create a PDF folder." : isSubject ? "Open a new subject." : "Set a new term."}</h2><p className="modal-copy">{isFolder ? "Group related professional references and their generated knowledge map." : isSubject ? "Give the subject a home before uploading its study material." : "Keep subjects and revision plans grouped by semester."}</p><form className="stack-form" onSubmit={submit}><label>Name<input required autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder={isFolder ? "e.g. Client research" : isSubject ? "e.g. Physics" : "e.g. Semester 2"} /></label>{isSubject && !isFolder && <label>Semester<select value={semesterId} onChange={(event) => setSemesterId(event.target.value)}>{semesters.map((semester) => <option value={semester.id} key={semester.id}>{semester.name}</option>)}</select></label>}<label>Description <span className="optional-label">optional</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows="3" placeholder="A short description" /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button full" disabled={busy}>{busy ? "Creating..." : `Create ${isFolder ? "folder" : isSubject ? "subject" : "semester"}`}<Icon name="arrow" size={17} /></button></form></div></div>;
}

function LectureWorkspace({ subjectId, token, lectures, selectedLectureId, onCreate, onSelect, onRefresh, onDelete, onNotify }) {
  const lecture = lectures.find((item) => item.id === selectedLectureId) || lectures[lectures.length - 1];
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [draftNotes, setDraftNotes] = useState(null);
  const [savingNotes, setSavingNotes] = useState(false);
  const [transcript, setTranscript] = useState(lecture?.transcript || "");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunkIndexRef = useRef(lecture?.transcript_segments?.length || 0);
  const startedAtRef = useRef(0);
  const uploadsRef = useRef([]);
  const stopRequestedRef = useRef(false);
  const ignoreStopRef = useRef(false);
  const pauseRequestedRef = useRef(false);
  const segmentTimerRef = useRef(null);

  useEffect(() => {
    setTranscript(lecture?.transcript || "");
    chunkIndexRef.current = lecture?.transcript_segments?.length || 0;
  }, [lecture?.id, lecture?.transcript]);

  useEffect(() => {
    setEditingNotes(false);
    setDraftNotes(null);
  }, [lecture?.id]);

  useEffect(() => () => {
    ignoreStopRef.current = true;
    clearTimeout(segmentTimerRef.current);
    if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  async function startRecording() {
    if (!lecture || lecture.status === "ready") return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onNotify("This browser does not support microphone recording.", true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      streamRef.current = stream;
      uploadsRef.current = [];
      stopRequestedRef.current = false;
      ignoreStopRef.current = false;
      pauseRequestedRef.current = false;
      startedAtRef.current = Date.now();
      stream.getAudioTracks().forEach((track) => track.addEventListener("ended", () => {
        if (!stopRequestedRef.current && !ignoreStopRef.current) {
          pauseRequestedRef.current = true;
          clearTimeout(segmentTimerRef.current);
          setRecording(false);
          onNotify("The microphone connection ended, so captions paused. Your saved captions are safe; press Start recording to continue.", true);
        }
      }));
      const startSegment = () => {
        if (ignoreStopRef.current || pauseRequestedRef.current || stopRequestedRef.current) return;

        const segmentRecorder = new MediaRecorder(stream, { mimeType });
        recorderRef.current = segmentRecorder;
        segmentRecorder.onerror = () => onNotify("The browser recorder encountered an error. Your saved captions are safe; press Start recording to continue.", true);
        segmentRecorder.ondataavailable = (event) => {
          if (!event.data.size) return;
          const chunkIndex = chunkIndexRef.current++;
          const offsetSeconds = (Date.now() - startedAtRef.current) / 1000;
          const upload = api.transcribeLectureChunk(subjectId, lecture.id, event.data, chunkIndex, offsetSeconds, token)
            .then((result) => setTranscript(result.transcript))
            .catch((error) => onNotify(error.message || "A caption chunk could not be transcribed.", true));
          uploadsRef.current.push(upload);
        };
        segmentRecorder.onstop = async () => {
          clearTimeout(segmentTimerRef.current);
          if (ignoreStopRef.current || pauseRequestedRef.current) {
            setBusy(false);
            stream.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
            recorderRef.current = null;
            return;
          }
          if (!stopRequestedRef.current) {
            startSegment();
            return;
          }
          setBusy(false);
          try {
            await Promise.all(uploadsRef.current);
            const finished = await api.finalizeLecture(subjectId, lecture.id, token);
            setTranscript(finished.transcript);
            onRefresh(finished);
            onNotify("Lecture captured and notes are ready.");
          } catch (error) {
            onNotify(error.message || "Lecture notes could not be generated.", true);
          } finally {
            setBusy(false);
            stream.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
            recorderRef.current = null;
          }
        };
        segmentRecorder.start();
        segmentTimerRef.current = setTimeout(() => {
          if (segmentRecorder.state === "recording") segmentRecorder.stop();
        }, 20000);
      };
      startSegment();
      setRecording(true);
      onNotify("Recording started. Audio is transcribed in temporary chunks.");
    } catch (error) {
      onNotify(error.message || "Microphone permission was not granted.", true);
    }
  }

  function stopRecording() {
    if (!recorderRef.current) return;
    stopRequestedRef.current = true;
    clearTimeout(segmentTimerRef.current);
    setRecording(false);
    setBusy(true);
    if (recorderRef.current.state !== "inactive") recorderRef.current.stop();
  }

  if (!lecture) {
    return <section className="lecture-page empty-lecture-page"><div className="lecture-hero"><span className="kicker">Lecture capture</span><h2>Keep the room, lose the scramble.</h2><p>Record a class, see captions as they arrive, and get structured notes after you stop. Audio is never saved.</p><button className="primary-button" onClick={onCreate}><Icon name="microphone" size={17} />Start Lecture 1</button></div></section>;
  }

  const notes = lecture.notes;
  function beginNotesEdit() {
    setDraftNotes({
      overview: notes?.overview || "",
      key_concepts: [...(notes?.key_concepts || [])],
      definitions: [...(notes?.definitions || [])],
      formulas: [...(notes?.formulas || [])],
      examples: [...(notes?.examples || [])],
      questions: [...(notes?.questions || [])],
      unclear_points: [...(notes?.unclear_points || [])],
      recap: notes?.recap || "",
    });
    setEditingNotes(true);
  }

  function updateDraft(field, value) {
    setDraftNotes((current) => ({ ...current, [field]: value }));
  }

  async function saveNotes() {
    setSavingNotes(true);
    try {
      const cleaned = Object.fromEntries(Object.entries(draftNotes).map(([field, value]) => [
        field,
        Array.isArray(value) ? value.map((item) => item.trim()).filter(Boolean) : value.trim(),
      ]));
      const updated = await api.updateLectureNotes(subjectId, lecture.id, cleaned, token);
      onRefresh(updated);
      setEditingNotes(false);
      setDraftNotes(null);
      onNotify("Lecture notes saved.");
    } catch (error) {
      onNotify(error.message || "Lecture notes could not be saved.", true);
    } finally {
      setSavingNotes(false);
    }
  }

  return <section className="lecture-page"><div className="lecture-page-head"><div><span className="kicker">Lecture {lecture.lecture_number}</span><h2>{lecture.title}</h2><p>{lecture.status === "ready" ? "Transcript and structured notes saved." : "Captions are captured temporarily and stored as text."}</p></div><div className="lecture-actions">{recording ? <button className="primary-button recording-button" onClick={stopRecording}><Icon name="stop" size={16} />Stop lecture</button> : <button className="primary-button" disabled={busy || lecture.status === "ready"} onClick={startRecording}>{busy ? <span className="spinner small-spin" /> : <Icon name="microphone" size={16} />}{busy ? "Preparing notes..." : lecture.status === "ready" ? "Notes saved" : "Start recording"}</button>}{lecture.status === "ready" && <button className="secondary-button" onClick={onCreate}><Icon name="plus" size={15} />New lecture</button>}<button className="danger-button" disabled={recording || busy} onClick={() => onDelete(lecture)}><Icon name="trash" size={15} />Delete lecture</button></div></div><div className="lecture-grid"><article className="transcript-card"><div className="lecture-card-head"><div><span className="card-label"><span className="signal coral" />Live captions</span><h3>{recording ? "Listening..." : "Transcript"}</h3></div>{recording && <span className="live-pill"><span />LIVE</span>}</div><div className="caption-stream">{transcript ? transcript.split("\n").map((line, index) => <p key={`${line}-${index}`}>{line}</p>) : <div className="caption-empty"><Icon name="microphone" size={25} /><span>Start recording to see the lecture appear here.</span></div>}</div><small className="privacy-note">Audio chunks are sent for transcription and discarded. Only captions are stored.</small></article><article className="lecture-notes-card"><div className="lecture-card-head"><div><span className="card-label"><span className="signal green" />Structured notes</span><h3>{notes ? (editingNotes ? "Edit notes" : "Ready to revise") : "After the lecture"}</h3></div>{notes && <div className="note-card-actions">{editingNotes ? <><button className="secondary-button" onClick={() => { setEditingNotes(false); setDraftNotes(null); }}>Cancel</button><button className="primary-button" disabled={savingNotes} onClick={saveNotes}>{savingNotes ? "Saving..." : "Save notes"}</button></> : <><span className="version-stamp">Saved notes</span><button className="secondary-button" onClick={beginNotesEdit}><Icon name="note" size={14} />Edit</button></>}</div>}</div>{notes ? editingNotes ? <LectureNotesEditor notes={draftNotes} onChange={updateDraft} /> : <div className="structured-notes"><section><h4>Overview</h4><p>{notes.overview}</p></section><NoteList title="Key concepts" items={notes.key_concepts} /><NoteList title="Definitions" items={notes.definitions} /><NoteList title="Formulas" items={notes.formulas} /><NoteList title="Examples" items={notes.examples} /><NoteList title="Questions" items={notes.questions} /><NoteList title="Unclear points" items={notes.unclear_points} warning /><section><h4>Quick recap</h4><p>{notes.recap}</p></section></div> : <div className="notes-placeholder"><Icon name="sparkle" size={24} /><p>When you stop recording, the full transcript is summarized once into concepts, definitions, formulas, examples, questions, and a recap.</p></div>}</article></div></section>;
}

function LectureNotesEditor({ notes, onChange }) {
  const listFields = [
    ["key_concepts", "Key concepts"],
    ["definitions", "Definitions"],
    ["formulas", "Formulas"],
    ["examples", "Examples"],
    ["questions", "Questions"],
    ["unclear_points", "Unclear points"],
  ];
  return <div className="structured-notes notes-editor"><label className="note-editor-field"><span>Overview</span><textarea value={notes.overview} onChange={(event) => onChange("overview", event.target.value)} /></label>{listFields.map(([field, label]) => <label className="note-editor-field" key={field}><span>{label}</span><textarea value={(notes[field] || []).join("\n")} onChange={(event) => onChange(field, event.target.value.split("\n"))} placeholder="One item per line" /><small>One item per line</small></label>)}<label className="note-editor-field"><span>Quick recap</span><textarea value={notes.recap} onChange={(event) => onChange("recap", event.target.value)} /></label></div>;
}

function NoteList({ title, items = [], warning = false }) {
  if (!items.length) return null;
  return <section className={warning ? "note-list warning" : "note-list"}><h4>{title}</h4><ul>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul></section>;
}

function TestModal({ test, subjectId, token, onClose, onSubmitted }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await api.submitTest(subjectId, test.id, answers, token);
      setResult(response);
      onSubmitted(response);
    } finally {
      setBusy(false);
    }
  }
  return <div className="modal-backdrop"><div className="modal-card test-modal"><button className="modal-close" onClick={onClose}><Icon name="close" size={18} /></button>{result ? <div className="result-view"><div className="result-ring"><strong>{Math.round(result.percentage)}%</strong><span>score</span></div><p className="eyebrow">Test submitted</p><h2>{result.percentage >= 70 ? "That knowledge is holding." : "A useful first signal."}</h2><p>You scored {result.score} out of {result.max_score}. {result.analytics?.weak_concepts?.length ? `Revisit: ${result.analytics.weak_concepts.join(", ")}.` : "No weak concepts detected."}</p><button className="primary-button" onClick={onClose}>Back to today <Icon name="arrow" size={17} /></button></div> : <><div className="test-modal-head"><div><span className="eyebrow">Proctored-style test</span><h2>{test.title || test.node_title}</h2></div><span className="test-deadline">{test.status === "overdue" ? formatOverdue(test.days_overdue) : `Due ${formatDate(test.due_at)}`}</span></div><form onSubmit={submit} className="test-form">{test.questions.map((question, index) => <fieldset key={question.id}><legend><span>{String(index + 1).padStart(2, "0")}</span>{question.question}</legend><div className="test-options">{question.options.map((option) => <label key={option} className={answers[question.id] === option ? "chosen" : ""}><input required name={`question-${question.id}`} type="radio" value={option} checked={answers[question.id] === option} onChange={(e) => setAnswers({ ...answers, [question.id]: e.target.value })} /><span>{option}</span></label>)}</div></fieldset>)}<button className="primary-button full" disabled={busy}>{busy ? "Scoring..." : "Submit test"}<Icon name="arrow" size={17} /></button></form></>}</div></div>;
}

function PdfViewer({ subjectId, documentItem, token, initialPage = 1, onClose }) {
  const viewerRef = useRef(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [loadError, setLoadError] = useState("");
  const [viewerFullscreen, setViewerFullscreen] = useState(() => Boolean(document.fullscreenElement));

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setPdfUrl("");
    setLoadError("");

    api.documentPdf(subjectId, documentItem.id, token)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setPdfUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.message || "The PDF could not be opened.");
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [subjectId, documentItem.id, token]);

  useEffect(() => {
    const syncFullscreen = () => setViewerFullscreen(Boolean(document.fullscreenElement));
    const handleKeyDown = (event) => {
      if (event.key === "Escape" && !document.fullscreenElement) onClose();
    };
    document.addEventListener("fullscreenchange", syncFullscreen);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreen);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  async function toggleViewerFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await viewerRef.current?.requestFullscreen();
      }
    } catch {
      setLoadError("Browser fullscreen was blocked. The PDF is still filling the app window.");
    }
  }

  const viewerUrl = pdfUrl ? `${pdfUrl}#page=${Math.max(1, initialPage)}&view=FitH` : "";

  return (
    <section className="pdf-viewer-shell" ref={viewerRef} aria-label={`PDF viewer for ${documentItem.filename}`}>
      <header className="pdf-viewer-bar">
        <button className="pdf-back-button" onClick={onClose} title="Back to Study OS">
          <Icon name="arrow" size={16} />
          <span>Back</span>
        </button>
        <div className="pdf-viewer-title">
          <Icon name="file" size={16} />
          <strong title={documentItem.filename}>{documentItem.filename}</strong>
          <span>Page {Math.max(1, initialPage)}</span>
        </div>
        <div className="pdf-viewer-actions">
          <button onClick={() => window.open(viewerUrl, "_blank", "noopener,noreferrer")} disabled={!viewerUrl} title="Open PDF in a new tab">
            <Icon name="external" size={16} />
            <span>Open</span>
          </button>
          <a className={!pdfUrl ? "disabled" : ""} href={pdfUrl || undefined} download={documentItem.filename} aria-disabled={!pdfUrl} title="Download PDF">
            <Icon name="download" size={16} />
            <span>Download</span>
          </a>
          <button className={viewerFullscreen ? "active" : ""} onClick={toggleViewerFullscreen} title={viewerFullscreen ? "Exit fullscreen" : "View PDF fullscreen"}>
            <Icon name="fullscreen" size={16} />
            <span>{viewerFullscreen ? "Exit" : "Fullscreen"}</span>
          </button>
        </div>
      </header>
      <div className="pdf-viewer-surface">
        {!pdfUrl && !loadError && <div className="pdf-viewer-state"><span className="spinner" />Opening PDF...</div>}
        {loadError && <div className="pdf-viewer-state error" role="alert"><Icon name="file" size={28} /><strong>PDF unavailable</strong><p>{loadError}</p><button onClick={onClose}>Back to Study OS</button></div>}
        {viewerUrl && <iframe className="pdf-frame" src={viewerUrl} title={`${documentItem.filename}, page ${Math.max(1, initialPage)}`} />}
      </div>
    </section>
  );
}

function App() {
  const [session, setSession] = useState(() => {
    const token = localStorage.getItem("study_token");
    const user = JSON.parse(localStorage.getItem("study_user") || "null");
    return token ? { token, user } : null;
  });
  const [semesters, setSemesters] = useState([]);
  const [selectedSemesterId, setSelectedSemesterId] = useState(Number(localStorage.getItem("study_semester")) || null);
  const [subjects, setSubjects] = useState([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState(Number(localStorage.getItem("study_subject")) || null);
  const [tree, setTree] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [content, setContent] = useState(null);
  const [notes, setNotes] = useState([]);
  const [noteDocument, setNoteDocument] = useState(null);
  const [practice, setPractice] = useState([]);
  const [progressRows, setProgressRows] = useState([]);
  const [plan, setPlan] = useState({ revisions: [], topic_tests: [], practice_sets: [] });
  const [assignments, setAssignments] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [selectedPdfPage, setSelectedPdfPage] = useState(1);
  const [lectures, setLectures] = useState([]);
  const [view, setView] = useState("map");
  const [selectedLectureId, setSelectedLectureId] = useState(null);
  const [tab, setTab] = useState("learn");
  const [noteText, setNoteText] = useState("");
  const [chatText, setChatText] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [billingOpen, setBillingOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [workspaceModal, setWorkspaceModal] = useState(null);
  const [activeTest, setActiveTest] = useState(null);
  const [llmProvider, setLlmProvider] = useState(() => localStorage.getItem("study_llm_provider") || "openai");
  const [darkMode, setDarkMode] = useState(() => {
    const savedTheme = localStorage.getItem("study_theme");
    return savedTheme ? savedTheme === "dark" : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  });
  const [appFullscreen, setAppFullscreen] = useState(() => document.fullscreenElement === document.documentElement);
  const [error, setError] = useState("");

  const selectedSemester = semesters.find((semester) => semester.id === selectedSemesterId);
  const selectedSubject = subjects.find((subject) => subject.id === selectedSubjectId);
  const selectedDocument = documents.find((item) => item.id === selectedDocumentId);
  const isProfessional = session?.user?.account_type === "professional";
  const progressMap = useMemo(() => Object.fromEntries(progressRows.map((row) => [row.node_id, row])), [progressRows]);

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
    localStorage.setItem("study_theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    const syncFullscreen = () => setAppFullscreen(document.fullscreenElement === document.documentElement);
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  useEffect(() => {
    if (!session?.token) return;
    let cancelled = false;
    api.me(session.token)
      .then((user) => {
        if (cancelled) return;
        localStorage.setItem("study_user", JSON.stringify(user));
        setSession((current) => current ? { ...current, user } : current);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [session?.token]);

  useEffect(() => {
    if (!session?.token) return;
    const url = new URL(window.location.href);
    const billingResult = url.searchParams.get("billing");
    if (!billingResult) return;
    url.searchParams.delete("billing");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    if (billingResult === "success") {
      setBillingOpen(true);
      notify("Payment received. Waiting for Stripe to confirm activation.");
    } else {
      notify("Checkout was cancelled. No subscription change was made.");
    }
  }, [session?.token]);

  useEffect(() => {
    if (!session?.token) return;
    function openSearchShortcut(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (tree.length) setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", openSearchShortcut);
    return () => window.removeEventListener("keydown", openSearchShortcut);
  }, [session?.token, tree.length]);

  function notify(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3600);
  }

  function logout() {
    localStorage.removeItem("study_token");
    localStorage.removeItem("study_user");
    setSession(null);
  }

  function changeLlmProvider(event) {
    const provider = event.target.value;
    setLlmProvider(provider);
    localStorage.setItem("study_llm_provider", provider);
    notify(`${provider === "deepseek" ? "DeepSeek V4 Flash" : "OpenAI"} selected.`);
  }

  async function toggleAppFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      notify("Browser fullscreen was blocked. The app is still using the full window.");
    }
  }

  async function handleWorkspaceCreated(item, kind) {
    setWorkspaceModal(null);
    if (kind === "semester") {
      setSemesters((items) => [...items, item]);
      setSelectedSemesterId(item.id);
      localStorage.setItem("study_semester", item.id);
      notify("Semester created.");
      return;
    }

    setSelectedSemesterId(item.semester_id);
    setSelectedSubjectId(item.id);
    localStorage.setItem("study_semester", item.semester_id);
    localStorage.setItem("study_subject", item.id);
    setView("map");
    setSubjects((items) => items.some((subject) => subject.id === item.id) ? items : [...items, item]);
    await loadSubject(item.id);
    notify(kind === "folder" ? "Folder created." : "Subject created.");
  }

  async function loadSemesters() {
    try {
      const result = await api.semesters(session.token);
      setSemesters(result);
      const nextId = result.some((item) => item.id === selectedSemesterId) ? selectedSemesterId : result[0]?.id || null;
      setSelectedSemesterId(nextId);
      if (nextId) localStorage.setItem("study_semester", nextId);
      return nextId;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  async function loadSubjects(semesterId = selectedSemesterId) {
    if (!semesterId) return;
    try {
      const result = await api.subjects(semesterId, session.token);
      setSubjects(result);
      const nextId = result.some((item) => item.id === selectedSubjectId) ? selectedSubjectId : result[0]?.id || null;
      setSelectedSubjectId(nextId);
      if (nextId) localStorage.setItem("study_subject", nextId);
    } catch (err) { setError(err.message); }
  }

  async function loadSubject(subjectId = selectedSubjectId) {
    if (!subjectId) return;
    setLoading(true);
    setError("");
    try {
      if (isProfessional) {
        const [treeResult, documentsResult] = await Promise.allSettled([
          api.tree(subjectId, session.token),
          api.documents(subjectId, session.token),
        ]);
        if (treeResult.status === "fulfilled") {
          const nextTree = treeResult.value;
          setTree(nextTree);
          const linkedNode = findNode(nextTree, studyNodeIdFromHash());
          const current = linkedNode || findNode(nextTree, selectedNodeId);
          setSelectedNodeId(current?.id || null);
        }
        if (documentsResult.status === "fulfilled") setDocuments(documentsResult.value);
        setPlan({ revisions: [], topic_tests: [], practice_sets: [] });
        setProgressRows([]);
        setAssignments([]);
        setLectures([]);
        setSelectedLectureId(null);
        const failedSections = [
          ["global map", treeResult],
          ["PDFs", documentsResult],
        ].filter(([, result]) => result.status === "rejected");
        if (failedSections.length) {
          setError(`Could not load ${failedSections.map(([name]) => name).join(", ")}.`);
        }
        return;
      }
      const results = await Promise.allSettled([
        api.tree(subjectId, session.token),
        api.dailyPlan(subjectId, session.token),
        api.progress(subjectId, session.token),
        api.assignments(subjectId, session.token),
        api.documents(subjectId, session.token),
        api.lectures(subjectId, session.token),
      ]);
      const [treeResult, planResult, progressResult, assignmentsResult, documentsResult, lecturesResult] = results;

      if (treeResult.status === "fulfilled") {
        const nextTree = treeResult.value;
        setTree(nextTree);
        const linkedNode = findNode(nextTree, studyNodeIdFromHash());
        const current = linkedNode || findNode(nextTree, selectedNodeId);
        setSelectedNodeId(current?.id || null);
      }
      if (planResult.status === "fulfilled") setPlan(planResult.value);
      if (progressResult.status === "fulfilled") setProgressRows(progressResult.value);
      if (assignmentsResult.status === "fulfilled") setAssignments(assignmentsResult.value);
      if (documentsResult.status === "fulfilled") setDocuments(documentsResult.value);
      if (lecturesResult.status === "fulfilled") {
        const nextLectures = lecturesResult.value;
        setLectures(nextLectures);
        const nextLectureId = nextLectures.some((item) => item.id === selectedLectureId)
          ? selectedLectureId
          : nextLectures[0]?.id || null;
        setSelectedLectureId(nextLectureId);
      }

      const failedSections = [
        ["study map", treeResult],
        ["daily plan", planResult],
        ["progress", progressResult],
        ["assignments", assignmentsResult],
        ["study material", documentsResult],
        ["lectures", lecturesResult],
      ].filter(([, result]) => result.status === "rejected");
      if (failedSections.length) {
        setError(`Could not load ${failedSections.map(([name]) => name).join(", ")}.`);
      }
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  async function loadNode(nodeId = selectedNodeId) {
    if (!selectedSubjectId || !nodeId) return;
    setDetail(null);
    setContent(null);
    setNoteDocument(null);
    setChatMessages([]);
    setTab("learn");
    try {
      const node = await api.node(selectedSubjectId, nodeId, session.token);
      setDetail(node);
      if (node.node_type === "subtopic") {
        const results = await Promise.allSettled([
          api.content(selectedSubjectId, nodeId, session.token),
          api.notes(selectedSubjectId, nodeId, session.token),
          api.noteDocument(selectedSubjectId, nodeId, session.token),
          isProfessional ? Promise.resolve([]) : api.practice(selectedSubjectId, nodeId, session.token),
        ]);
        let nextNoteDocument = results[2].status === "fulfilled" ? results[2].value : null;
        if (results[0].status === "fulfilled") {
          setContent(results[0].value);
        } else if (results[0].reason?.status === 404) {
          try {
            setContent(await api.generateContent(selectedSubjectId, nodeId, session.token));
            nextNoteDocument = await api.noteDocument(selectedSubjectId, nodeId, session.token);
          } catch (generationError) {
            setError(generationError.message || "Learning content could not be generated");
          }
        } else {
          setError(results[0].reason?.message || "Learning content could not be loaded");
        }
        setNotes(results[1].status === "fulfilled" ? results[1].value : []);
        setNoteDocument(nextNoteDocument);
        setPractice(results[3].status === "fulfilled" ? results[3].value : []);
      }
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { if (session) loadSemesters(); }, [session?.token, session?.user?.account_type]);
  useEffect(() => { if (session && selectedSemesterId) loadSubjects(selectedSemesterId); }, [session?.token, session?.user?.account_type, selectedSemesterId]);
  useEffect(() => { if (session && selectedSubjectId) loadSubject(selectedSubjectId); }, [session?.token, session?.user?.account_type, selectedSubjectId]);
  useEffect(() => { if (session && selectedNodeId) loadNode(selectedNodeId); }, [session?.token, session?.user?.account_type, selectedNodeId]);
  useEffect(() => {
    if (selectedNodeId) return;
    setDetail(null);
    setContent(null);
    setNotes([]);
    setNoteDocument(null);
    setPractice([]);
    setChatMessages([]);
  }, [selectedNodeId]);
  useEffect(() => {
    const openLinkedNode = () => {
      const pdfSource = pdfSourceFromHash();
      if (pdfSource) {
        const sourceDocument = documents.find((item) => item.id === pdfSource.documentId);
        if (sourceDocument) {
          setSelectedDocumentId(sourceDocument.id);
          setSelectedPdfPage(pdfSource.pageNumber);
          setView("pdf");
        }
        return;
      }
      const linkedId = studyNodeIdFromHash();
      if (!linkedId) {
        if (window.location.hash === "#study-map") {
          setSelectedNodeId(null);
          setView("map");
        }
        return;
      }
      const linkedNode = findNode(tree, linkedId);
      if (linkedNode) {
        setView("map");
        setSelectedNodeId(linkedId);
      }
    };
    if (pdfSourceFromHash() || studyNodeIdFromHash()) openLinkedNode();
    window.addEventListener("hashchange", openLinkedNode);
    window.addEventListener("popstate", openLinkedNode);
    return () => {
      window.removeEventListener("hashchange", openLinkedNode);
      window.removeEventListener("popstate", openLinkedNode);
    };
  }, [documents, tree]);

  function onAuthenticated(nextSession) {
    localStorage.setItem("study_token", nextSession.token);
    localStorage.setItem("study_user", JSON.stringify(nextSession.user));
    setSession(nextSession);
  }

  async function refreshAccount() {
    if (!session?.token) return;
    const user = await api.me(session.token);
    localStorage.setItem("study_user", JSON.stringify(user));
    setSession((current) => current ? { ...current, user } : current);
  }

  function chooseSemester(id) {
    setSelectedSemesterId(id);
    localStorage.setItem("study_semester", id);
    setSelectedSubjectId(null);
    setTree([]);
  }

  function chooseSubject(id) {
    setSelectedSubjectId(id);
    localStorage.setItem("study_subject", id);
    updateStudyHash(null, { replace: true });
    setSelectedNodeId(null);
    setSelectedDocumentId(null);
    setView("map");
  }

  function openDocument(documentItem) {
    setSelectedDocumentId(documentItem.id);
    setSelectedPdfPage(1);
    setView("pdf");
  }

  function closeDocument() {
    if (pdfSourceFromHash()) {
      const returnNode = findNode(tree, selectedNodeId);
      updateStudyHash(returnNode || null, { replace: true });
    }
    setSelectedDocumentId(null);
    setSelectedPdfPage(1);
    setView("map");
  }

  function navigateToNode(id) {
    const node = findNode(tree, id);
    if (!node && detail?.node_type === "subtopic") requestMindMapFullscreen();
    updateStudyHash(node || null);
    setView("map");
    setSelectedNodeId(node?.id || null);
  }

  function chooseLectures() {
    setView("lectures");
    if (!selectedLectureId && lectures[0]) setSelectedLectureId(lectures[0].id);
  }

  function chooseLecture(id) {
    setSelectedLectureId(id);
    setView("lectures");
  }

  async function createLecture() {
    if (!selectedSubjectId) return;
    try {
      const lecture = await api.createLecture(selectedSubjectId, {}, session.token);
      setLectures((items) => [...items, lecture]);
      setSelectedLectureId(lecture.id);
      setView("lectures");
      notify(`Lecture ${lecture.lecture_number} is ready.`);
    } catch (err) { setError(err.message); }
  }

  function updateLecture(updated) {
    setLectures((items) => items.map((item) => item.id === updated.id ? updated : item));
  }

  function lectureNotify(message, isError = false) {
    if (isError) setError(message);
    else notify(message);
  }

  async function refreshSubject() {
    await loadSubject(selectedSubjectId);
    if (selectedNodeId) await loadNode(selectedNodeId);
  }

  async function updateProgress(completed) {
    try {
      await api.updateProgress(selectedSubjectId, selectedNodeId, completed, session.token);
      await refreshSubject();
      notify(completed ? "Subtopic completed. Revision dates are set." : "Subtopic marked open again.");
    } catch (err) { setError(err.message); }
  }

  async function completeRevision(revision) {
    try {
      await api.completeRevision(selectedSubjectId, revision.id, session.token);
      await refreshSubject();
      notify("Revision checked off.");
    } catch (err) { setError(err.message); }
  }

  async function saveNote() {
    if (!noteText.trim()) return;
    try {
      const note = await api.createNote(selectedSubjectId, selectedNodeId, { content: noteText }, session.token);
      setNotes([note, ...notes]);
      setNoteText("");
      notify("Note saved to this subtopic.");
    } catch (err) { setError(err.message); }
  }

  async function refreshWorkspaceIndex() {
    const semesterId = await loadSemesters();
    if (semesterId) await loadSubjects(semesterId);
  }

  async function saveNoteDocument(notesValue) {
    try {
      const saved = await api.saveNoteDocument(selectedSubjectId, selectedNodeId, notesValue, session.token);
      setNoteDocument(saved);
      notify("Structured notes saved.");
      return saved;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  async function composeNotes(notesValue, instruction) {
    try {
      return await api.composeNotes(selectedSubjectId, selectedNodeId, notesValue, instruction, session.token);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  async function deleteNote(noteId) {
    if (!window.confirm("Delete this personal note?")) return;
    try {
      await api.deleteNote(selectedSubjectId, selectedNodeId, noteId, session.token);
      setNotes(notes.filter((note) => note.id !== noteId));
      notify("Note deleted.");
    } catch (err) { setError(err.message); }
  }

  async function updateNote(noteId, content) {
    try {
      const updated = await api.updateNote(selectedSubjectId, selectedNodeId, noteId, { content }, session.token);
      setNotes(notes.map((note) => note.id === noteId ? updated : note));
      notify("Note updated.");
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  async function deleteLecture(lecture) {
    if (!window.confirm(`Delete ${lecture.title}? Its transcript and notes will be removed.`)) return;
    try {
      await api.deleteLecture(selectedSubjectId, lecture.id, session.token);
      const remaining = lectures.filter((item) => item.id !== lecture.id);
      setLectures(remaining);
      setSelectedLectureId(remaining[0]?.id || null);
      notify("Lecture deleted.");
    } catch (err) { setError(err.message); }
  }

  async function deleteDocument(document) {
    if (!window.confirm(`Delete ${document.filename}? Its chunks, embeddings, and unsupported study-map branches will be removed.`)) return;
    try {
      await api.deleteDocument(selectedSubjectId, document.id, session.token);
      setSelectedNodeId(null);
      setDetail(null);
      setContent(null);
      await loadSubject(selectedSubjectId);
      notify("Study material deleted.");
    } catch (err) { setError(err.message); }
  }

  async function deleteSubject(subject) {
    if (!window.confirm(
      isProfessional
        ? `Delete ${subject.name}? This removes its PDFs, global map, learning pages, and notes.`
        : `Delete ${subject.name}? This removes its PDFs, study map, assignments, lectures, notes, and progress.`,
    )) return;
    try {
      await api.deleteSubject(subject.id, session.token);
      setSelectedNodeId(null);
      setDetail(null);
      setContent(null);
      setSelectedLectureId(null);
      setSelectedDocumentId(null);
      setView("map");
      if (selectedSubjectId === subject.id) {
        localStorage.removeItem("study_subject");
        setSelectedSubjectId(null);
      }
      await loadSubjects(selectedSemesterId);
      notify(isProfessional ? "Folder deleted." : "Subject deleted.");
    } catch (err) { setError(err.message); }
  }

  async function submitPractice(practiceId, answers) {
    try {
      const result = await api.submitPractice(selectedSubjectId, practiceId, answers, session.token);
      notify("Practice score saved.");
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  async function sendChat() {
    if (!chatText.trim()) return;
    const question = chatText.trim();
    setChatText("");
    setChatMessages((items) => [...items, { role: "user", content: question }]);
    setChatBusy(true);
    try {
      const response = await api.chat(selectedSubjectId, selectedNodeId, { question }, session.token);
      setChatMessages((items) => [...items, { role: "assistant", content: response.answer }]);
    } catch (err) { setError(err.message); }
    finally { setChatBusy(false); }
  }

  async function handleUploadDone(message) {
    setUploadOpen(false);
    notify(message);
    await refreshSubject();
  }

  if (!session) return <AuthScreen onAuthenticated={onAuthenticated} />;
  if (semesters.length === 0 || subjects.length === 0) {
    return (
      <>
        <header className="onboarding-bar">
          <div className="brand-mark"><span>◒</span> study / os</div>
          <button className="icon-button" onClick={logout}><Icon name="logout" size={16} /></button>
        </header>
        <EmptyWorkspace token={session.token} semesters={semesters} onCreated={refreshWorkspaceIndex} professionalMode={isProfessional} />
      </>
    );
  }
  if (view === "pdf" && selectedDocument) {
    return <PdfViewer subjectId={selectedSubjectId} documentItem={selectedDocument} token={session.token} initialPage={selectedPdfPage} onClose={closeDocument} />;
  }

  const selectedComplete = progressMap[selectedNodeId]?.status === "completed";
  return (
    <div className={`app-shell ${isProfessional ? "professional-app" : ""}`}>
      <Sidebar
        user={session.user}
        professionalMode={isProfessional}
        semesters={semesters}
        selectedSemester={selectedSemester}
        subjects={subjects}
        selectedSubjectId={selectedSubjectId}
        documents={documents}
        lectures={lectures}
        lectureView={view === "lectures"}
        selectedLectureId={selectedLectureId}
        onSemester={chooseSemester}
        onSubject={chooseSubject}
        onAddSemester={() => setWorkspaceModal("semester")}
        onAddSubject={() => setWorkspaceModal(isProfessional ? "folder" : "subject")}
        onDeleteSubject={deleteSubject}
        onDocument={openDocument}
        onDeleteDocument={deleteDocument}
        tree={tree}
        selectedNodeId={selectedNodeId}
        onNode={navigateToNode}
        progressMap={progressMap}
        onUpload={() => setUploadOpen(true)}
        onLectures={chooseLectures}
        onLecture={chooseLecture}
        onStartLecture={createLecture}
        onBilling={() => setBillingOpen(true)}
        onLogout={logout}
      />
      <main className="main-area">
        <header className="topbar">
          <div className="mobile-brand"><div className="brand-mark"><span>◒</span> study / os</div></div>
          <div className="topbar-context">
            <span className="mini-label">{isProfessional ? "Current folder" : "Currently studying"}</span>
            <strong>{selectedSubject?.name}</strong>
            <span className="context-dot" />
            {!isProfessional && view === "lectures"
              ? <span className="context-status">{lectures.length} lecture{lectures.length === 1 ? "" : "s"} captured</span>
              : documents.length
                ? <span className="context-status">{documents.length} PDF{documents.length > 1 ? "s" : ""} indexed</span>
                : <span className="context-status">Ready for your first PDF</span>}
          </div>
          <div className="topbar-actions">
            <button className="os-window-control" onClick={() => setDarkMode((enabled) => !enabled)} title={darkMode ? "Switch to light mode" : "Switch to dark mode"}><Icon name={darkMode ? "sun" : "moon"} size={16} /><span>{darkMode ? "Light" : "Dark"}</span></button>
            <button className={`os-window-control ${appFullscreen ? "active" : ""}`} onClick={toggleAppFullscreen} title={appFullscreen ? "Exit browser fullscreen" : "Enter browser fullscreen"}><Icon name="fullscreen" size={15} /><span>{appFullscreen ? "Exit" : "Fullscreen"}</span></button>
            <label className="model-switch"><span>AI</span><select value={llmProvider} onChange={changeLlmProvider} aria-label="Choose AI provider"><option value="openai">OpenAI</option><option value="deepseek">DeepSeek Flash</option></select></label>
            <button className="search-button" disabled={!tree.length} onClick={() => setSearchOpen(true)}><Icon name="search" size={17} /><span>Search map</span><kbd>⌘ K</kbd></button>
            <button className="top-upload" onClick={() => setUploadOpen(true)}><Icon name="upload" size={16} /><span>Upload PDF</span></button>
            <div className="avatar top-avatar">{initials(session.user?.full_name || session.user?.email)}</div>
          </div>
        </header>
        <div className={`content-grid ${isProfessional ? "professional-grid" : ""}`}>
          <section className="canvas">
            {!isProfessional && view === "lectures" ? (
              <LectureWorkspace subjectId={selectedSubjectId} token={session.token} lectures={lectures} selectedLectureId={selectedLectureId} onCreate={createLecture} onSelect={chooseLecture} onRefresh={updateLecture} onDelete={deleteLecture} onNotify={lectureNotify} />
            ) : (
              <>
                <div className="canvas-header">
                  <div>
                    <Breadcrumb detail={detail} onNode={navigateToNode} professionalMode={isProfessional} />
                    <h1>{detail?.title || selectedSubject?.name || (isProfessional ? "Your global map" : "Your study map")}</h1>
                  </div>
                  <div className="canvas-header-actions">
                    {detail?.node_type === "subtopic" && <a className="global-map-link" href="#study-map" onClick={(event) => { event.preventDefault(); navigateToNode(null); }}><Icon name="layers" size={15} />Global map</a>}
                    {!isProfessional && detail?.node_type === "subtopic" && <button className={`complete-button ${selectedComplete ? "done" : ""}`} onClick={() => updateProgress(!selectedComplete)}>{selectedComplete ? <><Icon name="check" size={16} />Completed</> : <>Mark complete <Icon name="arrow" size={15} /></>}</button>}
                  </div>
                </div>
                {loading && !detail ? (
                  <div className="loading-state"><span className="spinner" />Loading your map...</div>
                ) : detail?.node_type === "subtopic" ? (
                  <LearningPage detail={detail} content={content} tab={tab} setTab={setTab} notes={notes} noteDocument={noteDocument} noteText={noteText} setNoteText={setNoteText} onSaveNote={saveNote} onUpdateNote={updateNote} onDeleteNote={deleteNote} onSaveNoteDocument={saveNoteDocument} onComposeNotes={composeNotes} practice={practice} onSubmitPractice={submitPractice} chatMessages={chatMessages} chatText={chatText} setChatText={setChatText} onChat={sendChat} chatBusy={chatBusy} professionalMode={isProfessional} />
                ) : (
                  <Overview detail={detail} tree={tree} onNode={navigateToNode} rootTitle={selectedSubject?.name} selectedId={selectedNodeId} progressMap={progressMap} professionalMode={isProfessional} />
                )}
              </>
            )}
          </section>
          {!isProfessional && <TodayPanel subjectId={selectedSubjectId} plan={plan} progressRows={progressRows} tree={tree} onNode={navigateToNode} onRevision={completeRevision} onTest={setActiveTest} onSubmitPractice={submitPractice} />}
        </div>
      </main>
      {workspaceModal && <WorkspaceModal kind={workspaceModal} semesters={semesters} selectedSemesterId={selectedSemesterId} token={session.token} onClose={() => setWorkspaceModal(null)} onCreated={handleWorkspaceCreated} />}
      {searchOpen && <SearchMapModal tree={tree} selectedId={selectedNodeId} progressMap={progressMap} onClose={() => setSearchOpen(false)} onNode={navigateToNode} professionalMode={isProfessional} />}
      {uploadOpen && <UploadModal subject={selectedSubject} token={session.token} onClose={() => setUploadOpen(false)} onDone={handleUploadDone} professionalMode={isProfessional} />}
      {billingOpen && <BillingModal user={session.user} token={session.token} onClose={() => setBillingOpen(false)} onPlanChange={refreshAccount} />}
      {!isProfessional && activeTest && <TestModal test={activeTest} subjectId={selectedSubjectId} token={session.token} onClose={() => setActiveTest(null)} onSubmitted={() => { refreshSubject(); notify("Your analytics are saved."); }} />}
      {toast && <div className="toast"><Icon name="check" size={16} />{toast}</div>}
      {error && <button className="error-toast" onClick={() => setError("")}>{error}<Icon name="close" size={15} /></button>}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
