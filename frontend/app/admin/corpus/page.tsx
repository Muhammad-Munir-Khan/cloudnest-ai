"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Upload,
  Database,
  FileText,
  X,
  Search,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import {
  adminCorpusStats,
  adminUploadCorpusFile,
  adminListSources,
  adminDeleteSource,
  adminSearchCorpus,
} from "@/lib/api";
import type { CorpusSourceInfo, CorpusSearchHit } from "@/lib/types";

const ACCEPTED = ".pdf,.txt,.md,.docx";

export default function KnowledgeBasePage() {
  const [total, setTotal] = useState<number | null>(null);
  const [sources, setSources] = useState<CorpusSourceInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // upload form
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [contentType, setContentType] = useState("document");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // delete confirmation
  const [confirmDelete, setConfirmDelete] = useState<CorpusSourceInfo | null>(null);
  const [deleting, setDeleting] = useState(false);

  // search panel
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<CorpusSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  // sources filter
  const [sourceFilter, setSourceFilter] = useState("");

  const refresh = () => {
    adminCorpusStats()
      .then((s) => setTotal(s.total))
      .catch(() => setTotal(null));
    adminListSources()
      .then(setSources)
      .catch(() => setSources([]));
  };
  useEffect(refresh, []);

  const flash = (msg: string) => {
    setNotice(msg);
    setError(null);
    setTimeout(() => setNotice(null), 5000);
  };

  const filteredSources = useMemo(() => {
    const q = sourceFilter.trim().toLowerCase();
    if (!q) return sources;
    return sources.filter(
      (s) =>
        s.source_title.toLowerCase().includes(q) ||
        s.content_type.toLowerCase().includes(q),
    );
  }, [sources, sourceFilter]);

  const pickFile = (f: File | null) => {
    setError(null);
    setFile(f);
    if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await adminUploadCorpusFile(
        file,
        contentType.trim() || "document",
        title.trim() || undefined,
        author.trim() || undefined,
      );
      flash(res.message);
      setTotal(res.total_in_corpus);
      setFile(null);
      setTitle("");
      setAuthor("");
      if (inputRef.current) inputRef.current.value = "";
      // re-load sources to reflect the new addition
      adminListSources().then(setSources).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    setError(null);
    try {
      const res = await adminDeleteSource(confirmDelete.source_title);
      flash(`Deleted ${res.deleted} chunk(s) from "${confirmDelete.source_title}".`);
      setSources((p) =>
        p.filter((s) => s.source_title !== confirmDelete.source_title),
      );
      setTotal((t) => (t === null ? null : Math.max(0, t - res.deleted)));
      setConfirmDelete(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const doSearch = async () => {
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    try {
      const res = await adminSearchCorpus(q, 8);
      setSearchHits(res.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
      setSearchHits(null);
    } finally {
      setSearching(false);
    }
  };

  const sizeKb = file ? (file.size / 1024).toFixed(1) : null;

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--fg-primary)]">
            Knowledge Base
          </h1>
          <p className="text-sm text-[var(--fg-secondary)] mt-1">
            Manage the shared knowledge base. Available to all users.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[var(--fg-secondary)] shrink-0 mt-1">
          <Database size={16} />
          <span className="text-sm">
            <span className="font-semibold text-[var(--fg-primary)]">
              {total === null ? "—" : total.toLocaleString()}
            </span>{" "}
            objects · {sources.length} source{sources.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      {error && (
        <div className="mt-6 px-4 py-3 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-400">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-6 px-4 py-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-sm text-emerald-400">
          {notice}
        </div>
      )}

      {/* Upload section */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold text-[var(--fg-primary)] uppercase tracking-wider mb-3">
          Add a document
        </h2>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-xl border-2 border-dashed transition-colors ${
            dragOver
              ? "border-[var(--accent)] bg-[var(--accent)]/5"
              : "border-[var(--border-subtle)] bg-[var(--bg-card)] hover:border-[var(--accent)]/40"
          } px-6 py-10 text-center`}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            className="hidden"
          />
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileText size={20} className="text-[var(--accent)]" />
              <div className="text-left">
                <div className="text-sm font-medium text-[var(--fg-primary)]">
                  {file.name}
                </div>
                <div className="text-xs text-[var(--fg-tertiary)]">
                  {sizeKb} KB
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
                className="ml-2 p-1 rounded hover:bg-[var(--bg-base)] text-[var(--fg-tertiary)] hover:text-red-400 transition-colors"
                title="Remove"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <div>
              <Upload
                size={26}
                className="mx-auto text-[var(--fg-tertiary)] mb-2"
              />
              <div className="text-sm font-medium text-[var(--fg-primary)]">
                Drop a file here, or click to browse
              </div>
              <div className="text-xs text-[var(--fg-tertiary)] mt-1">
                Supports PDF, TXT, MD, DOCX
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <LabeledInput
            label="Title"
            value={title}
            onChange={setTitle}
            placeholder="(uses filename)"
          />
          <LabeledInput
            label="Author"
            value={author}
            onChange={setAuthor}
            placeholder="optional"
          />
          <LabeledInput
            label="Content type"
            value={contentType}
            onChange={setContentType}
            placeholder="document"
          />
        </div>

        <div className="mt-4">
          <button
            onClick={upload}
            disabled={!file || uploading}
            className="px-5 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {uploading ? "Uploading & indexing…" : "Add to knowledge base"}
          </button>
        </div>
      </section>

      {/* Search / preview panel */}
      <section className="mt-10">
        <button
          onClick={() => setSearchOpen((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] hover:border-[var(--accent)]/40 transition-colors"
        >
          <span className="text-sm font-semibold text-[var(--fg-primary)] flex items-center gap-2">
            <Search size={16} />
            Search / preview retrieval
          </span>
          {searchOpen ? (
            <ChevronUp size={16} className="text-[var(--fg-tertiary)]" />
          ) : (
            <ChevronDown size={16} className="text-[var(--fg-tertiary)]" />
          )}
        </button>

        {searchOpen && (
          <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4">
            <p className="text-xs text-[var(--fg-tertiary)]">
              Hybrid (BM25 + vector) search across the knowledge base. Useful for
              sanity-checking what your users would retrieve.
            </p>
            <div className="mt-3 flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") doSearch();
                }}
                placeholder="Type a query, hit Enter…"
                className="flex-1 px-3 py-2 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-md text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
              />
              <button
                onClick={doSearch}
                disabled={!searchQuery.trim() || searching}
                className="px-4 py-2 rounded-md bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>

            {searchHits !== null && (
              <div className="mt-4 space-y-2">
                {searchHits.length === 0 ? (
                  <p className="text-sm text-[var(--fg-tertiary)] italic">
                    No results.
                  </p>
                ) : (
                  searchHits.map((h, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-md bg-[var(--bg-base)] border border-[var(--border-subtle)]"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[0.7rem] font-mono text-[var(--fg-tertiary)]">
                          {h.source_title || "(untitled)"}
                          {h.content_type && ` · ${h.content_type}`}
                          {h.page && ` · p. ${h.page}`}
                        </span>
                        <span className="text-[0.65rem] font-mono text-[var(--accent)]">
                          score {h.score.toFixed(3)}
                        </span>
                      </div>
                      <p className="text-sm text-[var(--fg-secondary)] line-clamp-3">
                        {h.text}
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Sources list */}
      <section className="mt-10">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-[var(--fg-primary)] uppercase tracking-wider">
            Sources in knowledge base
          </h2>
          <button
            onClick={refresh}
            className="text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)] hover:text-[var(--accent)] transition-colors"
          >
            Refresh
          </button>
        </div>

        {sources.length > 0 && (
          <div className="mb-3 relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fg-tertiary)]"
            />
            <input
              type="text"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              placeholder="Filter sources…"
              className="w-full pl-9 pr-3 py-2 text-sm bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
            />
          </div>
        )}

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] overflow-hidden">
          {filteredSources.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-[var(--fg-tertiary)]">
              {sources.length === 0
                ? "No sources yet. Upload a document above to get started."
                : `No sources match "${sourceFilter}".`}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] text-left">
                  <th className="px-4 py-3 text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
                    Source
                  </th>
                  <th className="px-4 py-3 text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
                    Type
                  </th>
                  <th className="px-4 py-3 text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
                    Chunks
                  </th>
                  <th className="px-4 py-3 text-right text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredSources.map((s) => (
                  <tr
                    key={s.source_title}
                    className="border-b border-[var(--border-subtle)] last:border-0"
                  >
                    <td className="px-4 py-3 text-[var(--fg-primary)]">
                      {s.source_title}
                    </td>
                    <td className="px-4 py-3 text-[var(--fg-secondary)]">
                      <span className="px-2 py-0.5 rounded-md bg-[var(--bg-base)] text-xs font-mono">
                        {s.content_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[var(--fg-secondary)]">
                      {s.chunk_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setConfirmDelete(s)}
                        className="p-1.5 rounded-md text-[var(--fg-tertiary)] hover:bg-red-500/10 hover:text-red-400 transition-colors"
                        title="Delete this source"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => !deleting && setConfirmDelete(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="text-lg font-semibold text-[var(--fg-primary)]">
              Delete this source?
            </h2>
            <p className="text-sm text-[var(--fg-secondary)] mt-2">
              This permanently removes{" "}
              <span className="text-[var(--fg-primary)] font-medium">
                {confirmDelete.chunk_count.toLocaleString()}
              </span>{" "}
              chunk(s) from{" "}
              <span className="text-[var(--fg-primary)] font-medium">
                &ldquo;{confirmDelete.source_title}&rdquo;
              </span>
              . The knowledge base will no longer return results from this
              source.
            </p>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
                className="px-4 py-2 rounded-lg text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-base)] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={doDelete}
                disabled={deleting}
                className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1.5 w-full px-3 py-2 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-md text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
      />
    </label>
  );
}