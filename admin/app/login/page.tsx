"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setAdminSecret, ApiError } from "@/lib/api";
import type { TenantSummary } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setChecking(true);

    setAdminSecret(secret);

    try {
      // Cheapest real call to confirm the secret actually works before
      // committing to it in sessionStorage past this request.
      await apiFetch<{ tenants: TenantSummary[] }>("/admin/tenants");
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Incorrect admin secret." : err.message);
      } else {
        setError("Could not reach the API.");
      }
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold">Pulse Admin</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Enter the admin secret to continue.
          </p>
        </div>

        <input
          type="password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="Admin secret"
          autoFocus
          className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
        />

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={checking || !secret}
          className="w-full rounded-md bg-neutral-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {checking ? "Checking…" : "Continue"}
        </button>
      </form>
    </main>
  );
}
