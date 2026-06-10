import type { NextConfig } from "next";

const allowedDevOrigins = process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS
  ? process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS.split(",").map((s) => s.trim())
  : [];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(allowedDevOrigins.length > 0 && { allowedDevOrigins }),
};

export default nextConfig;
