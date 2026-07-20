const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}, token) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const llmProvider = localStorage.getItem("study_llm_provider");
  if (llmProvider) headers.set("X-LLM-Provider", llmProvider);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "object" ? payload.detail : payload;
    throw new ApiError(detail || "Something went wrong", response.status);
  }
  return payload;
}

async function requestBlob(path, token) {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { headers });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    const detail = typeof payload === "object" ? payload.detail : payload;
    throw new ApiError(detail || "The PDF could not be opened", response.status);
  }
  return response.blob();
}

const json = (method, path, body, token) => request(path, {
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
}, token);

export const api = {
  login: (body) => json("POST", "/login", body),
  register: (body) => json("POST", "/register", body),
  me: (token) => request("/me", {}, token),
  semesters: (token) => request("/semesters", {}, token),
  createSemester: (body, token) => json("POST", "/semesters", body, token),
  subjects: (semesterId, token) => request(`/semesters/${semesterId}/subjects`, {}, token),
  createSubject: (body, token) => json("POST", "/subjects", body, token),
  deleteSubject: (subjectId, token) => request(`/subjects/${subjectId}`, { method: "DELETE" }, token),
  tree: (subjectId, token) => request(`/subjects/${subjectId}/study-tree`, {}, token),
  documents: (subjectId, token) => request(`/subjects/${subjectId}/documents`, {}, token),
  documentPdf: (subjectId, documentId, token) => requestBlob(`/subjects/${subjectId}/documents/${documentId}/file`, token),
  deleteDocument: (subjectId, documentId, token) => request(`/subjects/${subjectId}/documents/${documentId}`, { method: "DELETE" }, token),
  node: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}`, {}, token),
  content: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/content`, {}, token),
  generateContent: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/content/generate`, { method: "POST" }, token),
  notes: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/notes`, {}, token),
  noteDocument: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/note-document`, {}, token),
  saveNoteDocument: (subjectId, nodeId, notes, token) => json("PUT", `/subjects/${subjectId}/study-nodes/${nodeId}/note-document`, { notes }, token),
  composeNotes: (subjectId, nodeId, notes, instruction, token) => json("POST", `/subjects/${subjectId}/study-nodes/${nodeId}/note-document/compose`, { notes, instruction }, token),
  createNote: (subjectId, nodeId, body, token) => json("POST", `/subjects/${subjectId}/study-nodes/${nodeId}/notes`, body, token),
  updateNote: (subjectId, nodeId, noteId, body, token) => json("PUT", `/subjects/${subjectId}/study-nodes/${nodeId}/notes/${noteId}`, body, token),
  deleteNote: (subjectId, nodeId, noteId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/notes/${noteId}`, { method: "DELETE" }, token),
  chat: (subjectId, nodeId, body, token) => json("POST", `/subjects/${subjectId}/study-nodes/${nodeId}/chat`, body, token),
  progress: (subjectId, token) => request(`/subjects/${subjectId}/progress`, {}, token),
  updateProgress: (subjectId, nodeId, completed, token) => json("PUT", `/subjects/${subjectId}/study-nodes/${nodeId}/progress`, { completed }, token),
  completeRevision: (subjectId, revisionId, token) => request(`/subjects/${subjectId}/revisions/${revisionId}/complete`, { method: "POST" }, token),
  practice: (subjectId, nodeId, token) => request(`/subjects/${subjectId}/study-nodes/${nodeId}/practice-sets`, {}, token),
  submitPractice: (subjectId, practiceId, answers, token) => json("POST", `/subjects/${subjectId}/practice-sets/${practiceId}/submit`, { answers }, token),
  dailyPlan: (subjectId, token) => request(`/subjects/${subjectId}/daily-plan`, {}, token),
  assignments: (subjectId, token) => request(`/subjects/${subjectId}/assignments`, {}, token),
  lectures: (subjectId, token) => request(`/subjects/${subjectId}/lectures`, {}, token),
  createLecture: (subjectId, body, token) => json("POST", `/subjects/${subjectId}/lectures`, body, token),
  lecture: (subjectId, lectureId, token) => request(`/subjects/${subjectId}/lectures/${lectureId}`, {}, token),
  updateLectureNotes: (subjectId, lectureId, notes, token) => json("PUT", `/subjects/${subjectId}/lectures/${lectureId}/notes`, notes, token),
  deleteLecture: (subjectId, lectureId, token) => request(`/subjects/${subjectId}/lectures/${lectureId}`, { method: "DELETE" }, token),
  transcribeLectureChunk: (subjectId, lectureId, blob, chunkIndex, offsetSeconds, token) => {
    const body = new FormData();
    body.append("file", blob, `lecture-${lectureId}-${chunkIndex}.webm`);
    return request(`/subjects/${subjectId}/lectures/${lectureId}/transcribe?chunk_index=${chunkIndex}&offset_seconds=${offsetSeconds}`, { method: "POST", body }, token);
  },
  finalizeLecture: (subjectId, lectureId, token) => request(`/subjects/${subjectId}/lectures/${lectureId}/finalize`, { method: "POST" }, token),
  topicTests: (subjectId, token) => request(`/subjects/${subjectId}/topic-tests`, {}, token),
  submitTest: (subjectId, testId, answers, token) => json("POST", `/subjects/${subjectId}/topic-tests/${testId}/submit`, { answers }, token),
  uploadStudy: (subjectId, file, token) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/subjects/${subjectId}/documents?document_type=textbook`, { method: "POST", body }, token);
  },
  uploadAssignment: (subjectId, file, token) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/subjects/${subjectId}/assignments`, { method: "POST", body }, token);
  },
};
