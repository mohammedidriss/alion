"use client";

/**
 * Camera slave page — a phone opens this via the join QR/link (join token, no login)
 * and becomes a capture device. All the logic lives in <CameraNode> so the coach's
 * session page can reuse it for the laptop camera.
 */

import { useParams, useSearchParams } from "next/navigation";
import { CameraNode } from "@/components/CameraNode";

export default function CameraSlavePage() {
  const params = useParams();
  const search = useSearchParams();
  return (
    <div className="mx-auto max-w-md p-4">
      <CameraNode sessionId={String(params.id)} token={search.get("token") ?? ""} />
    </div>
  );
}
