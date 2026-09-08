"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import type {
  CatalogUpsertResponse,
  KeySummary,
  MintKeyResponse,
  RecommendResponse,
  SimulateReviewResponse,
  TenantSummary,
} from "@/lib/types";

function parseAttributes(raw: string): Record<string, unknown> {
  if (!raw.trim()) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("Attributes must be valid JSON, e.g. {\"price_range\": \"$$\"}");
  }
}

export default function TenantDetailPage() {
  const ready = useRequireAuth();
  const params = useParams<{ id: string }>();
  const tenantId = params.id;

  const [tenant, setTenant] = useState<TenantSummary | null>(null);
  const [keys, setKeys] = useState<KeySummary[] | null>(null);
  const [mintedKey, setMintedKey] = useState<MintKeyResponse | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);

  async function loadTenant() {
    const data = await apiFetch<{ tenants: TenantSummary[] }>("/admin/tenants");
    setTenant(data.tenants.find((t) => t.tenant_id === tenantId) ?? null);
  }

  async function loadKeys() {
    try {
      const data = await apiFetch<{ keys: KeySummary[] }>(`/admin/tenants/${tenantId}/keys`);
      setKeys(data.keys);
    } catch (err) {
      setKeyError(err instanceof ApiError ? err.message : "Failed to load keys.");
    }
  }

  useEffect(() => {
    if (ready) {
      loadTenant();
      loadKeys();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  async function handleMintKey() {
    setKeyError(null);
    try {
      const result = await apiFetch<MintKeyResponse>(`/admin/tenants/${tenantId}/keys`, {
        method: "POST",
      });
      setMintedKey(result);
      await loadKeys();
    } catch (err) {
      setKeyError(err instanceof ApiError ? err.message : "Failed to mint key.");
    }
  }

  async function handleRevoke(prefix: string) {
    setKeyError(null);
    try {
      await apiFetch(`/admin/keys/${prefix}/revoke`, { method: "POST" });
      await loadKeys();
    } catch (err) {
      setKeyError(err instanceof ApiError ? err.message : "Failed to revoke key.");
    }
  }

  if (!ready) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <a href="/" className="text-sm text-neutral-500 hover:underline">
        ← Tenants
      </a>
      <h1 className="mt-2 text-xl font-semibold">{tenant?.name ?? tenantId}</h1>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">{tenantId}</p>

      <Section title="API keys">
        {mintedKey && (
          <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950">
            <p className="font-medium text-amber-900 dark:text-amber-200">
              New key — shown once, copy it now:
            </p>
            <code className="mt-2 block select-all break-all rounded bg-white px-2 py-1 text-xs dark:bg-neutral-900">
              {mintedKey.api_key}
            </code>
          </div>
        )}
        <button
          onClick={handleMintKey}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700"
        >
          Mint new key
        </button>
        {keyError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{keyError}</p>}
        <ul className="mt-4 space-y-2">
          {keys?.map((k) => (
            <li key={k.key_prefix} className="flex items-center justify-between text-sm">
              <code>{k.key_prefix}…</code>
              <span className="text-neutral-500">
                {k.revoked_at ? (
                  "revoked"
                ) : (
                  <button onClick={() => handleRevoke(k.key_prefix)} className="text-red-600 hover:underline dark:text-red-400">
                    revoke
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <CatalogSection tenantId={tenantId} />
      <SimulateSection tenantId={tenantId} />
      <RecommendSection tenantId={tenantId} />
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8 border-t border-neutral-200 pt-6 dark:border-neutral-800">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-500 dark:text-neutral-400">{label}</span>
      <input
        {...props}
        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
      />
    </label>
  );
}

function CatalogSection({ tenantId }: { tenantId: string }) {
  const [itemId, setItemId] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [attributes, setAttributes] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus(null);
    setSubmitting(true);
    try {
      const attrs = parseAttributes(attributes);
      const result = await apiFetch<CatalogUpsertResponse>(
        `/admin/tenants/${tenantId}/catalog/items`,
        {
          method: "POST",
          body: JSON.stringify({
            items: [{ item_id: itemId, name, category, attributes: attrs }],
          }),
        },
      );
      setStatus(`Upserted ${result.upserted} item.`);
      setItemId("");
      setName("");
      setCategory("");
      setAttributes("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upsert catalog item.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Section title="Add catalog item">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Item ID" value={itemId} onChange={(e) => setItemId(e.target.value)} required />
          <Field label="Category" value={category} onChange={(e) => setCategory(e.target.value)} required />
        </div>
        <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <label className="block text-sm">
          <span className="text-neutral-500 dark:text-neutral-400">Attributes (JSON, optional)</span>
          <textarea
            value={attributes}
            onChange={(e) => setAttributes(e.target.value)}
            placeholder='{"price_range": "$$"}'
            rows={2}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-xs outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {submitting ? "Saving…" : "Add item"}
        </button>
        {status && <p className="text-sm text-green-600 dark:text-green-400">{status}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </form>
    </Section>
  );
}

function SimulateSection({ tenantId }: { tenantId: string }) {
  const [subjectId, setSubjectId] = useState("");
  const [itemId, setItemId] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<SimulateReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      const response = await apiFetch<SimulateReviewResponse>(
        `/admin/tenants/${tenantId}/simulate-review`,
        {
          method: "POST",
          body: JSON.stringify({
            subject_external_id: subjectId,
            item: { item_id: itemId, name, category, description: description || undefined },
          }),
        },
      );
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulate request failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Section title="Test: Simulate">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field
          label="Subject external ID"
          value={subjectId}
          onChange={(e) => setSubjectId(e.target.value)}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Item ID" value={itemId} onChange={(e) => setItemId(e.target.value)} required />
          <Field label="Category" value={category} onChange={(e) => setCategory(e.target.value)} required />
        </div>
        <Field label="Item name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Field
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button
          type="submit"
          disabled={running}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {running ? "Running…" : "Run simulate"}
        </button>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </form>

      {result && (
        <div className="mt-4 rounded-md border border-neutral-200 p-4 text-sm dark:border-neutral-800">
          <p>
            <span className="font-medium">{result.simulated_rating}★</span>{" "}
            <span className="text-neutral-500">(confidence {result.confidence})</span>
          </p>
          <p className="mt-2 italic">&ldquo;{result.simulated_review}&rdquo;</p>
          <ul className="mt-3 list-disc pl-5 text-neutral-500 dark:text-neutral-400">
            {result.decision_factors.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}

function RecommendSection({ tenantId }: { tenantId: string }) {
  const [subjectId, setSubjectId] = useState("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      const response = await apiFetch<RecommendResponse>(`/admin/tenants/${tenantId}/recommend`, {
        method: "POST",
        body: JSON.stringify({ subject_external_id: subjectId, query: query || undefined }),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Recommend request failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Section title="Test: Recommend">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field
          label="Subject external ID"
          value={subjectId}
          onChange={(e) => setSubjectId(e.target.value)}
          required
        />
        <Field label="Query (optional)" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button
          type="submit"
          disabled={running}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {running ? "Running…" : "Run recommend"}
        </button>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </form>

      {result && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-neutral-500">
            Intent: {result.inferred_intent} {result.cold_start && "· cold start"}
          </p>
          {result.recommendations.map((r) => (
            <div key={r.item_id} className="rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800">
              <p>
                <span className="font-medium">
                  #{r.rank} {r.name}
                </span>{" "}
                <span className="text-neutral-500">
                  ({r.category}) — {r.predicted_rating}★
                  {r.ndcg_score !== null && ` · ndcg ${r.ndcg_score.toFixed(2)}`}
                </span>
              </p>
              <p className="mt-1 text-neutral-500">{r.explanation}</p>
            </div>
          ))}
          <ul className="list-disc pl-5 text-sm text-neutral-500 dark:text-neutral-400">
            {result.decision_factors.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
