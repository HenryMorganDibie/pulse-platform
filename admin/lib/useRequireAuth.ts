"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getAdminSecret } from "@/lib/api";

/** Redirects to /login if no admin secret is set for this tab. Returns whether the check has finished. */
export function useRequireAuth(): boolean {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getAdminSecret()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  return ready;
}
