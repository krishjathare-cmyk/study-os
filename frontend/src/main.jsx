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
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6",
  layers: "M12 3 3 8l9 5 9-5-9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5",
  logout: "M10 17l5-5-5-5m5 5H3m10-8V3a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v4m0 10v4a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-1",
  microphone: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm-7 9a7 7 0 0 0 14 0M12 18v4m-4 0h8",
  note: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6M8 13h8M8 17h6",
  plus: "M12 5v14M5 12h14",
  search: "m21 21-4.3-4.3m2.3-5.7a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  sparkle: "m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Zm7 13 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z",
  stop: "M6 6h12v12H6z",
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

function flattenNodes(nodes = []) {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);
}

function findNode(nodes, id) {
  return flattenNodes(nodes).find((node) => node.id === id);
}

function firstLeaf(nodes) {
  return flattenNodes(nodes).find((node) => node.node_type === "subtopic");
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

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("demo");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let user = null;
      if (mode === "register") {
        user = await api.register(form);
      }
      const result = await api.login({ email: form.email, password: form.password });
      onAuthenticated({ token: result.access_token, user: user || { full_name: form.email.split("@")[0], email: form.email } });
    } catch (err) {
      setError(err.message || "Unable to sign in");
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
          <p className="auth-intro">Your PDFs become a living map of chapters, ideas, practice and the next small thing worth remembering.</p>
          <div className="auth-stamp"><span>01</span><span>tree your thinking</span></div>
        </div>
      </section>
      <section className="auth-card-wrap">
        <div className="auth-card">
          <div className="auth-tabs">
            <button className={mode === "demo" ? "active" : ""} onClick={() => setMode("demo")}>Preview demo</button>
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Sign in</button>
            <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Create account</button>
          </div>
          {mode === "demo" ? (
            <DemoExperience />
          ) : (
            <>
              <div className="auth-heading">
                <p className="eyebrow">Welcome back</p>
                <h2>{mode === "login" ? "Pick up where you left off." : "Start your study space."}</h2>
                <p>{mode === "login" ? "Your map is waiting." : "Build a focused home for every subject."}</p>
              </div>
              <form onSubmit={submit} className="stack-form">
                {mode === "register" && <label>Full name<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Your name" /></label>}
                <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" /></label>
                <label>Password<input required minLength="6" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="At least 6 characters" /></label>
                {error && <div className="form-error">{error}</div>}
                <button className="primary-button full" disabled={busy}>{busy ? "Opening your space..." : mode === "login" ? "Enter study OS" : "Create my space"}<Icon name="arrow" size={17} /></button>
              </form>
              <p className="auth-footnote">Your study material stays scoped to your account.</p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

function EmptyWorkspace({ token, semesters, onCreated }) {
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
      if (!semester) semester = await api.createSemester({ name: semesterName || "My semester", description: "" }, token);
      await api.createSubject({ name: subjectName || "New subject", description: "", semester_id: semester.id }, token);
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
      <p className="eyebrow">First page</p>
      <h2>Give your learning a home.</h2>
      <p>Create a semester and subject, then upload the first chapter PDF. We’ll build the tree as you go.</p>
      <form onSubmit={createWorkspace} className="empty-form">
        {!semesters.length && <input value={semesterName} onChange={(e) => setSemesterName(e.target.value)} placeholder="Semester name" />}
        <input value={subjectName} onChange={(e) => setSubjectName(e.target.value)} placeholder="Subject name" />
        {error && <div className="form-error">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? "Creating..." : "Create study space"}<Icon name="arrow" size={17} /></button>
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
        <button className="tree-label" onClick={() => onSelect(node.id)}>
          <span className={`node-index level-${node.level}`}>{node.heading_number || (node.node_type === "chapter" ? "C" : "•")}</span>
          <span className="tree-title">{node.title}</span>
          {complete && <span className="tree-complete"><Icon name="check" size={13} /></span>}
        </button>
      </div>
      {hasChildren && open && <div className="tree-children">{node.children.map((child) => <TreeNode key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} progressMap={progressMap} depth={depth + 1} />)}</div>}
    </div>
  );
}

function Sidebar({ user, semesters, selectedSemester, subjects, selectedSubjectId, documents, lectures, lectureView, selectedLectureId, onSemester, onSubject, onAddSemester, onAddSubject, onDeleteSubject, onDeleteDocument, tree, selectedNodeId, onNode, progressMap, onUpload, onLectures, onLecture, onStartLecture, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="brand-mark"><span>◒</span> study / os</div>
        <button className="icon-button mobile-close"><Icon name="close" /></button>
      </div>
      <div className="semester-picker">
        <span className="mini-label">Workspace</span>
        <div className="semester-picker-row"><select value={selectedSemester?.id || ""} onChange={(e) => onSemester(Number(e.target.value))}>
          {semesters.map((semester) => <option value={semester.id} key={semester.id}>{semester.name}</option>)}
        </select><button className="tiny-action" onClick={onAddSemester} title="Add semester"><Icon name="plus" size={15} /></button></div>
        <Icon name="chevron" size={14} />
      </div>
      <div className="sidebar-section">
        <div className="section-heading"><span>Your subjects</span><button className="tiny-action" onClick={onAddSubject} title="Add subject"><Icon name="plus" size={15} /></button></div>
        <div className="subject-list">
          {subjects.map((subject) => <div key={subject.id} className={`subject-item-row ${selectedSubjectId === subject.id ? "active" : ""}`}><button className="subject-item" onClick={() => onSubject(subject.id)}><span className="subject-color" />{subject.name}<span className="subject-arrow">›</span></button><button className="subject-delete" onClick={() => onDeleteSubject(subject)} title={`Delete ${subject.name}`}><Icon name="trash" size={13} /></button></div>)}
          {!subjects.length && <p className="muted small">Create your first subject to begin.</p>}
        </div>
      </div>
      <div className={`sidebar-section lecture-section ${lectureView ? "active-section" : ""}`}>
        <div className="section-heading"><button className="section-link" onClick={onLectures}>Lectures</button><span className="tree-count">{lectures.length}</span><button className="tiny-action" onClick={onStartLecture} title="Start a lecture"><Icon name="plus" size={15} /></button></div>
        {lectures.length ? <div className="lecture-list">{lectures.map((lecture) => <button key={lecture.id} className={`lecture-row ${selectedLectureId === lecture.id ? "selected" : ""}`} onClick={() => onLecture(lecture.id)}><span className="lecture-number">{String(lecture.lecture_number).padStart(2, "0")}</span><span><strong>{lecture.title}</strong><small>{lecture.status === "ready" ? "Notes ready" : "Transcript in progress"}</small></span><span className={`lecture-status ${lecture.status}`} /></button>)}</div> : <button className="lecture-empty" onClick={onStartLecture}><Icon name="microphone" size={14} />Start your first lecture</button>}
      </div>
      {documents.length > 0 && <div className="sidebar-section document-section"><div className="section-heading"><span>Study material</span><span className="tree-count">{documents.length} PDFs</span></div><div className="document-list">{documents.map((document) => <div className="document-row" key={document.id}><span className="document-icon"><Icon name="file" size={13} /></span><span className="document-copy"><strong title={document.filename}>{document.filename}</strong><small title={document.description}>{document.description}</small></span><button className="document-delete" onClick={() => onDeleteDocument(document)} title={`Delete ${document.filename}`}><Icon name="trash" size={13} /></button></div>)}</div></div>}
      {tree.length > 0 && <div className="sidebar-section tree-section"><div className="section-heading"><span>Study map</span><span className="tree-count">{flattenNodes(tree).filter((node) => node.node_type === "subtopic").length} nodes</span></div><div className="tree-list">{tree.map((node) => <TreeNode key={node.id} node={node} selectedId={selectedNodeId} onSelect={onNode} progressMap={progressMap} />)}</div></div>}
      <div className="sidebar-bottom">
        <button className="upload-side-button" onClick={onUpload}><Icon name="upload" size={16} /><span>Upload material</span><kbd>U</kbd></button>
        <div className="profile-row"><div className="avatar">{initials(user?.full_name || user?.email)}</div><div className="profile-copy"><strong>{user?.full_name || "Student"}</strong><span>{user?.email || "Your account"}</span></div><button className="icon-button" onClick={onLogout} title="Log out"><Icon name="logout" size={16} /></button></div>
      </div>
    </aside>
  );
}

function TodayPanel({ subjectId, plan, progressRows, tree, onNode, onRevision, onTest }) {
  const leaves = flattenNodes(tree).filter((node) => node.node_type === "subtopic");
  const completed = progressRows.filter((row) => row.status === "completed").length;
  const percent = leaves.length ? Math.round((completed / leaves.length) * 100) : 0;
  return (
    <aside className="today-panel">
      <div className="today-heading"><div><p className="eyebrow">Your rhythm</p><h3>Today</h3></div><span className="date-stamp">{formatDate(new Date(), { weekday: "short", month: "short", day: "numeric" })}</span></div>
      <div className="progress-card"><div className="progress-card-top"><span>Subject progress</span><strong>{percent}%</strong></div><div className="progress-track"><span style={{ width: `${percent}%` }} /></div><p>{completed} of {leaves.length || "your"} subtopics completed</p></div>
      <div className="today-block"><div className="block-title"><span className="signal amber" />Revision queue <span>{plan?.revisions?.length || 0}</span></div>{plan?.revisions?.length ? plan.revisions.map((revision) => <button className="queue-item" key={revision.id} onClick={() => onNode(revision.node_id)}><span className="queue-icon"><Icon name="clock" size={15} /></span><span><strong>{revision.node_title}</strong><small>{revision.status === "overdue" ? formatOverdue(revision.days_overdue) : `review after ${revision.interval_days}d`}</small></span><span className="queue-check" title="Mark revision complete" onClick={(event) => { event.stopPropagation(); onRevision(revision); }}><Icon name="check" size={14} /></span></button>) : <div className="empty-queue"><span>Nothing due today.</span><small>Finish a node and we’ll schedule the next revisit.</small></div>}</div>
      <div className="today-block"><div className="block-title"><span className="signal coral" />Topic tests <span>{plan?.topic_tests?.length || 0}</span></div>{plan?.topic_tests?.length ? plan.topic_tests.map((test) => <button className="test-queue" key={test.id} onClick={() => onTest(test)}><span className="test-number">{test.questions.length}</span><span><strong>{test.node_title}</strong><small>{test.status === "overdue" ? formatOverdue(test.days_overdue) : `due ${formatDate(test.due_at)}`}</small></span><Icon name="arrow" size={15} /></button>) : <div className="empty-queue"><span>No active tests yet.</span><small>Complete every subtopic in a topic to unlock one.</small></div>}</div>
      <div className="today-quote"><span>“</span><p>Small, repeated returns beat one heroic cram session.</p><small>study / os principle 04</small></div>
    </aside>
  );
}

function Breadcrumb({ detail }) {
  return <div className="breadcrumb">{detail?.breadcrumb?.map((item, index) => <span key={item.id}><span className={index === detail.breadcrumb.length - 1 ? "current" : ""}>{item.title}</span>{index < detail.breadcrumb.length - 1 && <b> / </b>}</span>)}</div>;
}

function Overview({ detail, tree, onNode }) {
  const children = detail ? findNode(tree, detail.id)?.children || [] : tree;
  return <section className="overview-panel"><div className="overview-intro"><span className="kicker">{detail?.node_type === "chapter" ? "Chapter map" : "Topic map"}</span><h2>{detail?.title || "Your study map"}</h2><p>{detail?.node_type === "chapter" ? "Move through the branches below. Each leaf opens into notes, practice and a private AI tutor grounded in your material." : "Choose a subtopic to open its learning page."}</p></div><div className="child-grid">{children.map((child) => <button key={child.id} className="child-card" onClick={() => onNode(child.id)}><span className="child-card-index">{child.heading_number || "→"}</span><span><strong>{child.title}</strong><small>{child.node_type === "subtopic" ? "Open learning page" : `${child.children?.length || 0} subtopics`}</small></span><Icon name="arrow" size={16} /></button>)}</div>{!children.length && <div className="no-content"><Icon name="file" size={22} /><span>Upload a study PDF to draw the first branches.</span></div>}</section>;
}

function LearningPage({ detail, content, tab, setTab, notes, noteText, setNoteText, onSaveNote, onUpdateNote, onDeleteNote, practice, onSubmitPractice, chatMessages, chatText, setChatText, onChat, chatBusy }) {
  if (!detail) return <div className="loading-state"><span className="spinner" />Loading your study map...</div>;
  if (detail.node_type !== "subtopic") return <Overview detail={detail} tree={[]} onNode={() => {}} />;
  return <section className="learning-page"><div className="learning-tabs"><button className={tab === "learn" ? "active" : ""} onClick={() => setTab("learn")}><Icon name="sparkle" size={15} />Learn</button><button className={tab === "visualize" ? "active" : ""} onClick={() => setTab("visualize")}><Icon name="layers" size={15} />Visualize</button><button className={tab === "practice" ? "active" : ""} onClick={() => setTab("practice")}><Icon name="check" size={15} />Practice</button><button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}><Icon name="chat" size={15} />Ask tutor</button><button className={tab === "notes" ? "active" : ""} onClick={() => setTab("notes")}><Icon name="note" size={15} />My notes</button></div>{tab === "learn" && <LearnTab content={content} />}{tab === "visualize" && <VisualizationTab detail={detail} content={content} />}{tab === "practice" && <PracticeTab practice={practice} onSubmit={onSubmitPractice} />}{tab === "chat" && <ChatTab messages={chatMessages} text={chatText} setText={setChatText} onSend={onChat} busy={chatBusy} />}{tab === "notes" && <NotesTab notes={notes} text={noteText} setText={setNoteText} onSave={onSaveNote} onUpdate={onUpdateNote} onDelete={onDeleteNote} />}</section>;
}

function LearnTab({ content }) {
  if (!content) return <div className="no-content"><Icon name="sparkle" size={22} /><span>Learning content is still being prepared for this subtopic.</span></div>;
  return <div className="learn-grid"><article className="lesson-card hero-lesson"><div className="card-label"><span className="signal blue" />The idea</div><h3>{content.explanation}</h3><div className="lesson-footer"><span><Icon name="sparkle" size={14} />AI-generated from your material</span><span>v{content.version}</span></div></article><article className="lesson-card analogy-card"><div className="card-label"><span className="signal amber" />Make it stick</div><h3>Analogy</h3><p>{content.analogy}</p></article><article className="lesson-card example-card"><div className="card-label"><span className="signal coral" />Try the shape</div><h3>Worked example</h3><p>{content.worked_example}</p></article><article className="lesson-card real-life-card"><div className="card-label"><span className="signal green" />See it around you</div><h3>Real-life example</h3><p>{content.real_life_example || "Regenerate this learning page to add a real-life application."}</p></article>{content.formulas?.length > 0 && <article className="lesson-card formula-card"><div className="card-label"><span className="signal green" />Formula desk</div>{content.formulas.map((formula, index) => <div className="formula-row" key={`${formula.expression}-${index}`}><code>{formula.expression}</code><p>{formula.symbols || formula.use_case}</p></div>)}</article>}<article className="lesson-card key-card"><div className="card-label"><span className="signal ink" />Remember</div><ul>{content.key_points?.map((point, index) => <li key={index}>{point}</li>)}</ul></article><article className="lesson-card question-card"><div className="card-label"><span className="signal coral" />Check yourself</div>{content.conceptual_questions?.map((question, index) => <p key={index}><span>0{index + 1}</span>{question}</p>)}</article></div>;
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

function NotesTab({ notes, text, setText, onSave, onUpdate, onDelete }) {
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState("");
  const [savingId, setSavingId] = useState(null);

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
    <div className="notes-panel">
      <div className="notes-heading">
        <div>
          <span className="kicker">Private layer</span>
          <h3>Your notes</h3>
          <p>Keep your own thinking beside the generated lesson.</p>
        </div>
        <Icon name="note" size={22} />
      </div>
      <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Write a memory hook, question, or connection..." />
      <div className="notes-actions">
        <span>Only visible to you</span>
        <button className="secondary-button" disabled={!text.trim()} onClick={onSave}>
          <Icon name="check" size={15} />Save note
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
        {!notes.length && <p className="muted">Your first note will appear here.</p>}
      </div>
    </div>
  );
}

function UploadModal({ subject, token, onClose, onDone }) {
  const [kind, setKind] = useState("study");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("idle");
  const [error, setError] = useState("");
  const stageTimersRef = useRef([]);

  useEffect(() => () => {
    stageTimersRef.current.forEach((timer) => clearTimeout(timer));
  }, []);

  function clearStageTimers() {
    stageTimersRef.current.forEach((timer) => clearTimeout(timer));
    stageTimersRef.current = [];
  }

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setStage("uploading");
    setError("");
    clearStageTimers();
    stageTimersRef.current = [
      setTimeout(() => setStage("indexing"), 900),
      setTimeout(() => setStage(kind === "study" ? "preparing" : "mapping"), 3000),
    ];
    try {
      if (kind === "study") await api.uploadStudy(subject.id, file, token);
      else await api.uploadAssignment(subject.id, file, token);
      clearStageTimers();
      setStage("complete");
      setTimeout(() => onDone(kind === "study" ? "Study material processed" : "Assignment mapped to the study tree"), 900);
    } catch (err) {
      clearStageTimers();
      setStage("idle");
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  const statusText = {
    uploading: "Uploading PDF...",
    indexing: "Organizing and indexing chunks...",
    preparing: "Preparing the study map...",
    mapping: "Mapping assignment chunks...",
    complete: "Completed. Closing this window...",
  }[stage];
  const progressStage = stage === "complete" ? 3 : stage === "preparing" || stage === "mapping" ? 2 : stage === "indexing" ? 1 : 0;

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && stage !== "complete" && onClose()}><div className="modal-card upload-modal"><button className="modal-close" disabled={busy || stage === "complete"} onClick={onClose}><Icon name="close" size={18} /></button><div className={`modal-icon ${stage === "complete" ? "complete" : ""}`}><Icon name={stage === "complete" ? "check" : "upload"} size={24} /></div><p className="eyebrow">Add material</p><h2>{stage === "complete" ? "Material is ready." : "Feed the subject."}</h2><p className="modal-copy">{stage === "complete" ? "Your study space has been updated." : "Study PDFs grow the map. Assignment PDFs become scoped practice."}</p><div className="upload-switch"><button type="button" disabled={busy || stage === "complete"} className={kind === "study" ? "active" : ""} onClick={() => setKind("study")}><Icon name="book" size={16} />Study PDF</button><button type="button" disabled={busy || stage === "complete"} className={kind === "assignment" ? "active" : ""} onClick={() => setKind("assignment")}><Icon name="file" size={16} />Assignment PDF</button></div><form onSubmit={upload}><label className={`dropzone ${file ? "has-file" : ""}`}><input disabled={busy || stage === "complete"} type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0])} />{file ? <><Icon name="check" size={26} /><strong>{file.name}</strong><span>{stage === "idle" ? "Ready to process" : statusText}</span></> : <><Icon name="upload" size={26} /><strong>Drop a PDF here</strong><span>or click to browse</span></>}</label>{(busy || stage === "complete") && <div className={`upload-status ${stage}`}><div className="upload-status-heading"><span className="spinner upload-spinner" />{statusText}</div><div className="upload-steps"><span className={progressStage >= 1 ? "done" : ""}>Upload</span><span className={progressStage >= 2 ? "done" : ""}>Index</span><span className={progressStage >= 3 ? "done" : ""}>Ready</span></div><small>Please keep this window open until processing is complete.</small></div>}{error && <div className="form-error">{error}</div>}<button className="primary-button full" disabled={!file || busy || stage === "complete"}>{stage === "complete" ? "Completed" : busy ? statusText : "Process PDF"}{stage === "complete" ? <Icon name="check" size={17} /> : <Icon name="arrow" size={17} />}</button></form></div></div>;
}

function WorkspaceModal({ kind, semesters, selectedSemesterId, token, onClose, onCreated }) {
  const isSubject = kind === "subject";
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

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal-card workspace-modal"><button className="modal-close" onClick={onClose}><Icon name="close" size={18} /></button><div className="modal-icon"><Icon name={isSubject ? "book" : "layers"} size={24} /></div><p className="eyebrow">New {isSubject ? "subject" : "semester"}</p><h2>{isSubject ? "Open a new subject." : "Set a new term."}</h2><p className="modal-copy">{isSubject ? "Give the subject a home before uploading its study material." : "Keep subjects and revision plans grouped by semester."}</p><form className="stack-form" onSubmit={submit}><label>Name<input required autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder={isSubject ? "e.g. Physics" : "e.g. Semester 2"} /></label>{isSubject && <label>Semester<select value={semesterId} onChange={(event) => setSemesterId(event.target.value)}>{semesters.map((semester) => <option value={semester.id} key={semester.id}>{semester.name}</option>)}</select></label>}<label>Description <span className="optional-label">optional</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows="3" placeholder="A short description" /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button full" disabled={busy}>{busy ? "Creating..." : `Create ${isSubject ? "subject" : "semester"}`}<Icon name="arrow" size={17} /></button></form></div></div>;
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
  const [practice, setPractice] = useState([]);
  const [progressRows, setProgressRows] = useState([]);
  const [plan, setPlan] = useState({ revisions: [], topic_tests: [], practice_sets: [] });
  const [assignments, setAssignments] = useState([]);
  const [documents, setDocuments] = useState([]);
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
  const [workspaceModal, setWorkspaceModal] = useState(null);
  const [activeTest, setActiveTest] = useState(null);
  const [llmProvider, setLlmProvider] = useState(() => localStorage.getItem("study_llm_provider") || "openai");
  const [error, setError] = useState("");

  const selectedSemester = semesters.find((semester) => semester.id === selectedSemesterId);
  const selectedSubject = subjects.find((subject) => subject.id === selectedSubjectId);
  const progressMap = useMemo(() => Object.fromEntries(progressRows.map((row) => [row.node_id, row])), [progressRows]);

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
    notify("Subject created.");
  }

  async function loadSemesters() {
    try {
      const result = await api.semesters(session.token);
      setSemesters(result);
      const nextId = result.some((item) => item.id === selectedSemesterId) ? selectedSemesterId : result[0]?.id || null;
      setSelectedSemesterId(nextId);
      if (nextId) localStorage.setItem("study_semester", nextId);
    } catch (err) { setError(err.message); }
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
        const current = findNode(nextTree, selectedNodeId) || firstLeaf(nextTree) || nextTree[0];
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
    setChatMessages([]);
    setTab("learn");
    try {
      const node = await api.node(selectedSubjectId, nodeId, session.token);
      setDetail(node);
      if (node.node_type === "subtopic") {
        const results = await Promise.allSettled([
          api.content(selectedSubjectId, nodeId, session.token),
          api.notes(selectedSubjectId, nodeId, session.token),
          api.practice(selectedSubjectId, nodeId, session.token),
        ]);
        if (results[0].status === "fulfilled") {
          setContent(results[0].value);
        } else if (results[0].reason?.status === 404) {
          try {
            setContent(await api.generateContent(selectedSubjectId, nodeId, session.token));
          } catch (generationError) {
            setError(generationError.message || "Learning content could not be generated");
          }
        } else {
          setError(results[0].reason?.message || "Learning content could not be loaded");
        }
        setNotes(results[1].status === "fulfilled" ? results[1].value : []);
        setPractice(results[2].status === "fulfilled" ? results[2].value : []);
      }
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { if (session) loadSemesters(); }, [session?.token]);
  useEffect(() => { if (session && selectedSemesterId) loadSubjects(selectedSemesterId); }, [session?.token, selectedSemesterId]);
  useEffect(() => { if (session && selectedSubjectId) loadSubject(selectedSubjectId); }, [session?.token, selectedSubjectId]);
  useEffect(() => { if (session && selectedNodeId) loadNode(selectedNodeId); }, [session?.token, selectedNodeId]);

  function onAuthenticated(nextSession) {
    localStorage.setItem("study_token", nextSession.token);
    localStorage.setItem("study_user", JSON.stringify(nextSession.user));
    setSession(nextSession);
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
    setView("map");
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
    if (!window.confirm(`Delete ${subject.name}? This removes its PDFs, study map, assignments, lectures, notes, and progress.`)) return;
    try {
      await api.deleteSubject(subject.id, session.token);
      setSelectedNodeId(null);
      setDetail(null);
      setContent(null);
      setSelectedLectureId(null);
      setView("map");
      if (selectedSubjectId === subject.id) {
        localStorage.removeItem("study_subject");
        setSelectedSubjectId(null);
      }
      await loadSubjects(selectedSemesterId);
      notify("Subject deleted.");
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
  if (semesters.length === 0 || subjects.length === 0) return <><header className="onboarding-bar"><div className="brand-mark"><span>◒</span> study / os</div><button className="icon-button" onClick={logout}><Icon name="logout" size={16} /></button></header><EmptyWorkspace token={session.token} semesters={semesters} onCreated={loadSemesters} /></>;

  const selectedComplete = progressMap[selectedNodeId]?.status === "completed";
  return <div className="app-shell"><Sidebar user={session.user} semesters={semesters} selectedSemester={selectedSemester} subjects={subjects} selectedSubjectId={selectedSubjectId} documents={documents} lectures={lectures} lectureView={view === "lectures"} selectedLectureId={selectedLectureId} onSemester={chooseSemester} onSubject={chooseSubject} onAddSemester={() => setWorkspaceModal("semester")} onAddSubject={() => setWorkspaceModal("subject")} onDeleteSubject={deleteSubject} onDeleteDocument={deleteDocument} tree={tree} selectedNodeId={selectedNodeId} onNode={(id) => { setView("map"); setSelectedNodeId(id); }} progressMap={progressMap} onUpload={() => setUploadOpen(true)} onLectures={chooseLectures} onLecture={chooseLecture} onStartLecture={createLecture} onLogout={logout} /><main className="main-area"><header className="topbar"><div className="mobile-brand"><div className="brand-mark"><span>◒</span> study / os</div></div><div className="topbar-context"><span className="mini-label">Currently studying</span><strong>{selectedSubject?.name}</strong><span className="context-dot" />{view === "lectures" ? <span className="context-status">{lectures.length} lecture{lectures.length === 1 ? "" : "s"} captured</span> : documents.length ? <span className="context-status">{documents.length} study PDF{documents.length > 1 ? "s" : ""} indexed</span> : <span className="context-status">Ready for your first upload</span>}</div><div className="topbar-actions"><label className="model-switch"><span>AI</span><select value={llmProvider} onChange={changeLlmProvider} aria-label="Choose AI provider"><option value="openai">OpenAI</option><option value="deepseek">DeepSeek Flash</option></select></label><button className="search-button"><Icon name="search" size={17} /><span>Search map</span><kbd>⌘ K</kbd></button><button className="top-upload" onClick={() => setUploadOpen(true)}><Icon name="upload" size={16} /><span>Upload</span></button><div className="avatar top-avatar">{initials(session.user?.full_name || session.user?.email)}</div></div></header><div className="content-grid"><section className="canvas">{view === "lectures" ? <LectureWorkspace subjectId={selectedSubjectId} token={session.token} lectures={lectures} selectedLectureId={selectedLectureId} onCreate={createLecture} onSelect={chooseLecture} onRefresh={updateLecture} onDelete={deleteLecture} onNotify={lectureNotify} /> : <><div className="canvas-header"><div><Breadcrumb detail={detail} /><h1>{detail?.title || selectedSubject?.name || "Your study map"}</h1></div>{detail?.node_type === "subtopic" && <button className={`complete-button ${selectedComplete ? "done" : ""}`} onClick={() => updateProgress(!selectedComplete)}>{selectedComplete ? <><Icon name="check" size={16} />Completed</> : <>Mark complete <Icon name="arrow" size={15} /></>}</button>}</div>{loading && !detail ? <div className="loading-state"><span className="spinner" />Loading your map...</div> : detail?.node_type === "subtopic" ? <LearningPage detail={detail} content={content} tab={tab} setTab={setTab} notes={notes} noteText={noteText} setNoteText={setNoteText} onSaveNote={saveNote} onUpdateNote={updateNote} onDeleteNote={deleteNote} practice={practice} onSubmitPractice={submitPractice} chatMessages={chatMessages} chatText={chatText} setChatText={setChatText} onChat={sendChat} chatBusy={chatBusy} /> : <Overview detail={detail} tree={tree} onNode={setSelectedNodeId} />}</>}</section><TodayPanel subjectId={selectedSubjectId} plan={plan} progressRows={progressRows} tree={tree} onNode={setSelectedNodeId} onRevision={completeRevision} onTest={setActiveTest} /></div></main>{workspaceModal && <WorkspaceModal kind={workspaceModal} semesters={semesters} selectedSemesterId={selectedSemesterId} token={session.token} onClose={() => setWorkspaceModal(null)} onCreated={handleWorkspaceCreated} />}{uploadOpen && <UploadModal subject={selectedSubject} token={session.token} onClose={() => setUploadOpen(false)} onDone={handleUploadDone} />}{activeTest && <TestModal test={activeTest} subjectId={selectedSubjectId} token={session.token} onClose={() => setActiveTest(null)} onSubmitted={() => { refreshSubject(); notify("Your analytics are saved."); }} />}{toast && <div className="toast"><Icon name="check" size={16} />{toast}</div>}{error && <button className="error-toast" onClick={() => setError("")}>{error}<Icon name="close" size={15} /></button>}</div>;
}

createRoot(document.getElementById("root")).render(<App />);
