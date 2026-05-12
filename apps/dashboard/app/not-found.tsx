import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="text-6xl font-bold text-neutral-600">404</div>
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="max-w-md text-sm text-neutral-400">
        The page you are looking for does not exist or has been moved.
      </p>
      <Link
        href="/"
        className="mt-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-medium text-black hover:bg-emerald-400"
      >
        Go home
      </Link>
    </div>
  );
}
