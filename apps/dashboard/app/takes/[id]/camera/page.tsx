"use client";

/**
 * Camera page for a dataset take (ADR-013) — the phone opens it from the take's
 * join QR (join token, no login). Same <CameraNode> as a session's camera page; the
 * clip and pose land in the take's folder, never in session storage.
 */

import { useParams, useSearchParams } from "next/navigation";
import { CameraNode } from "@/components/CameraNode";

export default function TakeCameraPage() {
  const params = useParams();
  const search = useSearchParams();
  return (
    <div className="mx-auto max-w-md p-4">
      <CameraNode takeId={String(params.id)} token={search.get("token") ?? ""} />
    </div>
  );
}
