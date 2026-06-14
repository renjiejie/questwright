"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8765";

const SOURCE_OPTIONS = ["world_bible", "monster_manual", "phb", "dmg", "srd_misc"];
const CHUNK_TYPE_OPTIONS = [
  "lore_chunk",
  "monster_statblock",
  "spell_chunk",
  "rule_chunk",
  "class_race_feature",
  "misc",
];
const STAGE_OPTIONS = ["default", "world_audit"];

type RetrievedChunk = {
  chunk_id: string;
  score: number;
  source: string | null;
  source_title: string | null;
  chunk_type: string | null;
  title: string | null;
  section_path: string[] | null;
  tags: string[] | null;
  text: string;
  metadata: Record<string, unknown> | null;
  canon_level: string | null;
  source_ref: string | null;
};

export default function KnowledgePage() {
  const [projectId, setProjectId] = useState("p1");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(8);
  const [stage, setStage] = useState("default");
  const [sources, setSources] = useState<string[]>([]);
  const [chunkTypes, setChunkTypes] = useState<string[]>([]);
  const [crMin, setCrMin] = useState(0);
  const [crMax, setCrMax] = useState(30);
  const [useCr, setUseCr] = useState(false);

  const [results, setResults] = useState<RetrievedChunk[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- upload / ingest 控件状态 ---
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestSourceId, setIngestSourceId] = useState<string | null>(null);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  async function runIngest() {
    if (!uploadFile) return;
    setIngestBusy(true);
    setIngestError(null);
    setIngestStatus(null);
    setIngestSourceId(null);
    try {
      // 1. 上传
      const form = new FormData();
      form.append("file", uploadFile);
      const upResp = await fetch(`${API_BASE}/projects/${projectId}/sources`, {
        method: "POST",
        body: form,
      });
      if (!upResp.ok) {
        throw new Error(`上传失败 HTTP ${upResp.status}: ${await upResp.text()}`);
      }
      const source = await upResp.json();
      const sid: string = source.source_id;
      setIngestSourceId(sid);
      setIngestStatus(source.status ?? "uploaded");

      // 2. 触发 ingest
      const ingResp = await fetch(
        `${API_BASE}/projects/${projectId}/sources/${sid}/ingest`,
        { method: "POST" }
      );
      if (!ingResp.ok) {
        throw new Error(`ingest 触发失败 HTTP ${ingResp.status}: ${await ingResp.text()}`);
      }
      setIngestStatus("pending");

      // 3. 轮询状态直到 indexed / failed
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const pollResp = await fetch(
          `${API_BASE}/projects/${projectId}/sources/${sid}`
        );
        if (!pollResp.ok) continue;
        const cur = await pollResp.json();
        setIngestStatus(cur.status);
        if (cur.status === "indexed") break;
        if (cur.status === "failed") {
          throw new Error(`ingest 失败：${cur.last_error ?? "未知错误"}`);
        }
      }
    } catch (e) {
      setIngestError(e instanceof Error ? e.message : String(e));
    } finally {
      setIngestBusy(false);
    }
  }

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      const filters: Record<string, unknown> = {};
      if (sources.length) filters.source = sources;
      if (chunkTypes.length) filters.chunk_type = chunkTypes;
      if (useCr) filters.cr_range = [crMin, crMax];

      const resp = await fetch(`${API_BASE}/projects/${projectId}/retrieve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: topK,
          stage,
          filters: Object.keys(filters).length ? filters : undefined,
        }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${detail}`);
      }
      setResults(await resp.json());
      setExpanded({});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "0 auto" }}>
      <h1>Knowledge 检索调试</h1>
      <p style={{ color: "#666" }}>
        向量 + BM25 混合检索，支持来源 / 类型 / CR / stage 过滤。返回 chunk 含得分与
        metadata。
      </p>
      {/* PLACEHOLDER_CONTROLS */}
      <section style={{ display: "grid", gap: 12, marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ width: 90 }}>Project ID</label>
          <input
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            style={{ flex: "0 0 160px", padding: 6 }}
          />
        </div>

        <fieldset style={{ border: "1px solid #ddd", padding: 12 }}>
          <legend>上传世界观 → ingest（写入当前 Project ID）</legend>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="file"
              accept=".md,.markdown,text/markdown"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
            />
            <button
              onClick={runIngest}
              disabled={ingestBusy || !uploadFile}
            >
              {ingestBusy ? "处理中…" : "上传并 ingest"}
            </button>
            {ingestStatus && (
              <span style={{ fontSize: 13, color: ingestStatus === "indexed" ? "green" : "#555" }}>
                状态：{ingestStatus}
                {ingestSourceId && <>（{ingestSourceId}）</>}
              </span>
            )}
          </div>
          <p style={{ fontSize: 12, color: "#999", margin: "6px 0 0" }}>
            MVP 仅支持 Markdown（.md / text/markdown）。indexed 后即可在下方检索。
          </p>
          {ingestError && (
            <p style={{ color: "crimson", fontSize: 13, margin: "6px 0 0" }}>
              {ingestError}
            </p>
          )}
        </fieldset>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ width: 90 }}>Query</label>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="例如：red dragon、王国的守护者"
            style={{ flex: 1, padding: 6 }}
          />
        </div>

        <fieldset style={{ border: "1px solid #ddd", padding: 12 }}>
          <legend>source</legend>
          {SOURCE_OPTIONS.map((s) => (
            <label key={s} style={{ marginRight: 12 }}>
              <input
                type="checkbox"
                checked={sources.includes(s)}
                onChange={() => setSources(toggle(sources, s))}
              />{" "}
              {s}
            </label>
          ))}
        </fieldset>

        <fieldset style={{ border: "1px solid #ddd", padding: 12 }}>
          <legend>chunk_type</legend>
          {CHUNK_TYPE_OPTIONS.map((t) => (
            <label key={t} style={{ marginRight: 12 }}>
              <input
                type="checkbox"
                checked={chunkTypes.includes(t)}
                onChange={() => setChunkTypes(toggle(chunkTypes, t))}
              />{" "}
              {t}
            </label>
          ))}
        </fieldset>

        <fieldset style={{ border: "1px solid #ddd", padding: 12 }}>
          <legend>
            <label>
              <input
                type="checkbox"
                checked={useCr}
                onChange={() => setUseCr(!useCr)}
              />{" "}
              cr_range
            </label>
          </legend>
          <div style={{ display: "flex", gap: 16, opacity: useCr ? 1 : 0.5 }}>
            <span>
              min {crMin}
              <input
                type="range"
                min={0}
                max={30}
                value={crMin}
                disabled={!useCr}
                onChange={(e) => setCrMin(Number(e.target.value))}
              />
            </span>
            <span>
              max {crMax}
              <input
                type="range"
                min={0}
                max={30}
                value={crMax}
                disabled={!useCr}
                onChange={(e) => setCrMax(Number(e.target.value))}
              />
            </span>
          </div>
        </fieldset>

        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <label>
            stage{" "}
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              {STAGE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            top_k{" "}
            <input
              type="number"
              min={1}
              max={100}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              style={{ width: 60 }}
            />
          </label>
          <button onClick={runSearch} disabled={loading || !query.trim()}>
            {loading ? "检索中…" : "检索"}
          </button>
        </div>
      </section>

      {error && <p style={{ color: "crimson" }}>错误：{error}</p>}

      <section style={{ display: "grid", gap: 12 }}>
        {results.map((c) => (
          <article
            key={c.chunk_id}
            style={{ border: "1px solid #ccc", borderRadius: 6, padding: 12 }}
          >
            <header style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{c.title ?? c.chunk_id}</strong>
              <span style={{ color: "#888" }}>score {c.score.toFixed(4)}</span>
            </header>
            <div style={{ fontSize: 13, color: "#555", margin: "4px 0" }}>
              <span>source: {c.source}</span>
              {c.canon_level && <span> · canon: {c.canon_level}</span>}
              {c.section_path && c.section_path.length > 0 && (
                <span> · {c.section_path.join(" / ")}</span>
              )}
            </div>
            <button
              onClick={() =>
                setExpanded((prev) => ({ ...prev, [c.chunk_id]: !prev[c.chunk_id] }))
              }
              style={{ fontSize: 12 }}
            >
              {expanded[c.chunk_id] ? "收起" : "展开 text / metadata"}
            </button>
            {expanded[c.chunk_id] && (
              <div style={{ marginTop: 8 }}>
                <pre style={{ whiteSpace: "pre-wrap", background: "#f7f7f7", padding: 8 }}>
                  {c.text}
                </pre>
                <pre style={{ whiteSpace: "pre-wrap", background: "#f0f0f5", padding: 8 }}>
                  {JSON.stringify(c.metadata, null, 2)}
                </pre>
              </div>
            )}
          </article>
        ))}
        {!loading && !error && results.length === 0 && <p style={{ color: "#999" }}>暂无结果。</p>}
      </section>
    </main>
  );
}
