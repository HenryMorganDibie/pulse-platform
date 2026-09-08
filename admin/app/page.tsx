"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import type { TenantCreateResponse, TenantSummary } from "@/lib/types";

export default function DashboardPage() {
  const ready = useRequireAuth();
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<TenantCreateResponse | null>(null);

  async function loadTenants() {
    try {
      const data = await apiFetch<{ tenants: TenantSummary[] }>("/admin/tenants");
      setTenants(data.tenants);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load tenants.");
    }
  }

  useEffect(() => {
    if (ready) loadTenants();
  }, [ready]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const result = await apiFetch<TenantCreateResponse>("/admin/tenants", {
        method: "POST",
        body: JSON.stringify({ name: newName }),
      });
      setJustCreated(result);
      setNewName("");
      await loadTenants();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create tenant.");
    } finally {
      setCreating(false);
    }
  }

  if (!ready) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-xl font-semibold">Tenants</h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        Pulse Platform tenant management.
      </p>

      {justCreated && (
        <div className="mt-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950">
          <p className="font-medium text-amber-900 dark:text-amber-200">
            API key for &ldquo;{justCreated.name}&rdquo; — shown once, copy it now:
          </p>
          <code className="mt-2 block select-all break-all rounded bg-white px-2 py-1 text-xs dark:bg-neutral-900">
            {justCreated.api_key}
          </code>
          <button
            onClick={() => setJustCreated(null)}
            className="mt-2 text-xs text-amber-700 underline dark:text-amber-300"
          >
            Dismiss
          </button>
        </div>
      )}

      <form onSubmit={handleCreate} className="mt-6 flex gap-2">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New tenant name"
          className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
        <button
          type="submit"
          disabled={creating || !newName}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {creating ? "Creating…" : "Create tenant"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-8 divide-y divide-neutral-200 dark:divide-neutral-800">
        {tenants === null && <p className="py-4 text-sm text-neutral-500">Loading…</p>}
        {tenants?.length === 0 && (
          <p className="py-4 text-sm text-neutral-500">No tenants yet — create one above.</p>
        )}
        {tenants?.map((t) => (
          <Link
            key={t.tenant_id}
            href={`/tenants/${t.tenant_id}`}
            className="flex items-center justify-between py-3 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-900"
          >
            <div>
              <p className="font-medium">{t.name}</p>
              <p className="text-neutral-500 dark:text-neutral-400">
                {t.plan} · {t.active_key_count} active key{t.active_key_count === 1 ? "" : "s"}
              </p>
            </div>
            <span className="text-neutral-400">
              {new Date(t.created_at).toLocaleDateString()}
            </span>
          </Link>
        ))}
      </div>
    </main>
  );
}
