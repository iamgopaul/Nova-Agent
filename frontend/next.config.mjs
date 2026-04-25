/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enables `node server.js` in the Docker standalone build
  output: process.env.DOCKER_BUILD ? "standalone" : undefined,
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["127.0.0.1"],
}

export default nextConfig
