"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Asks the server for the page again every few seconds, so numbers and the engine lamp stay true.
export default function Refresh({ every = 5000 }: { every?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, every);
    return () => clearInterval(id);
  }, [router, every]);
  return null;
}
