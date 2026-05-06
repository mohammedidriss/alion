"use client";

import { api } from "@/lib/api";

interface Props {
  name: string;
  photo_path: string | null;
  size?: number;
  className?: string;
}

/**
 * Profile avatar — shows the uploaded photo when present, otherwise an
 * initial-letter circle. Used by Fighter, Coach, Referee.
 */
export function ProfileAvatar({ name, photo_path, size = 64, className = "" }: Props) {
  const url = api.photoUrl(photo_path);
  const initial = name.charAt(0).toUpperCase() || "?";
  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={`${name} avatar`}
        style={{ width: size, height: size }}
        className={`shrink-0 rounded-full object-cover ${className}`}
      />
    );
  }
  return (
    <div
      style={{ width: size, height: size, fontSize: size / 2.4 }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-emerald-400 font-bold text-black ${className}`}
      aria-label={`${name} avatar`}
    >
      {initial}
    </div>
  );
}
